"""Current/history semantics on synthetic snapshots in a private PostgreSQL DB."""

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from app.execution_filters import ExecutionQueryFilters
from app.workorder_snapshots import workorder_snapshot_query

pytestmark = [pytest.mark.integration, pytest.mark.security]
INSTANT = datetime(2026, 10, 1, 12, tzinfo=UTC)
NUMBER = "WO-001"


@dataclass(frozen=True)
class Dataset:
    url: str
    org_a: UUID
    org_b: UUID
    snapshots: dict[str, int]
    executions: dict[str, str]


@pytest.fixture(scope="module")
def private_database():
    parent = os.environ["DATABASE_URL"]
    name = "synergia_issue_195_" + uuid4().hex
    url = make_conninfo(parent, dbname=name)
    with psycopg.connect(parent, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[2] / "scripts/apply_migrations.py"
                ),
            ],
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
            check=True,
        )
        yield url
    finally:
        with psycopg.connect(parent, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture
def isolated_database(private_database):
    """Clone the migrated template; never delete immutable audit history."""
    parent = os.environ["DATABASE_URL"]
    template = conninfo_to_dict(private_database)["dbname"]
    name = "synergia_issue_195_case_" + uuid4().hex
    with psycopg.connect(parent, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                sql.Identifier(name), sql.Identifier(template)
            )
        )
    try:
        yield make_conninfo(parent, dbname=name)
    finally:
        with psycopg.connect(parent, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def insert_snapshot(
    connection,
    *,
    organization,
    label,
    started,
    updated,
    status="completed",
    number=NUMBER,
    partial=False,
):
    execution = f"{label}-{uuid4().hex}"
    connection.execute(
        """INSERT INTO synergia.executions
        (id, organization_id, status, source, started_at)
        VALUES (%s, %s, %s, 'OWM', %s)""",
        (execution, organization, status, started),
    )
    source = connection.execute(
        """INSERT INTO synergia.source_files
        (execution_id, file_name, content_hash, source)
        VALUES (%s, 'synthetic.json', %s, 'OWM') RETURNING id""",
        (execution, uuid4().hex * 2),
    ).fetchone()[0]
    # Every execution deliberately has the SAME workbook organization code.
    business_org = connection.execute(
        """INSERT INTO synergia.organizations
        (organization_code, execution_id, source_file_id)
        VALUES ('SAME-WORKBOOK-CODE', %s, %s) RETURNING id""",
        (execution, source),
    ).fetchone()[0]
    snapshot = connection.execute(
        """INSERT INTO synergia.workorders
        (workorder_number, organization_id, execution_id, source_file_id,
         processing_status, updated_at, planned_quantity, produced_quantity,
         received_quantity, released_quantity, pending_quantity, retained_quantity)
        VALUES (%s, %s, %s, %s, 'consolidated', %s, %s, %s, 9, 0, %s, %s)
        RETURNING id""",
        (
            number,
            business_org,
            execution,
            source,
            updated,
            None if partial else 40,
            0 if partial else 20,
            None if partial else 9,
            None if partial else 1,
        ),
    ).fetchone()[0]
    return snapshot, execution


@pytest.fixture
def dataset(isolated_database):
    org_a, org_b = uuid4(), uuid4()
    snapshots, executions = {}, {}
    with psycopg.connect(isolated_database) as connection:
        for organization in (org_a, org_b):
            connection.execute(
                """INSERT INTO synergia.iam_organizations
                (id, organization_code, display_name) VALUES (%s, %s, %s)""",
                (
                    organization,
                    f"syn195-{organization.hex}",
                    "Synthetic A" if organization == org_a else "Synthetic B",
                ),
            )
        specs = [
            ("old", org_a, 0, 0, "completed", NUMBER, False),
            ("z-tie-earlier", org_a, 1, 4, "completed", NUMBER, False),
            ("a-tie-later", org_a, 2, 4, "completed_with_errors", NUMBER, True),
            ("b-current", org_b, 3, 4, "completed", NUMBER, False),
            ("other-number", org_a, 2, 6, "completed", "WO-002", False),
            ("unknown-iam", None, 8, 8, "completed", NUMBER, False),
        ]
        for state in (
            "pending",
            "validating",
            "normalizing",
            "consolidating",
            "applying_rules",
            "reprocessing",
            "duplicate",
            "failed",
            "validation_failed",
            "cancelled",
        ):
            specs.append((state, org_a, 9, 9, state, NUMBER, False))
        for (
            label,
            organization,
            start_days,
            update_days,
            state,
            number,
            partial,
        ) in specs:
            snapshots[label], executions[label] = insert_snapshot(
                connection,
                organization=organization,
                label="0-b-current" if label == "b-current" else label,
                started=INSTANT + timedelta(days=start_days),
                updated=INSTANT + timedelta(days=update_days),
                status=state,
                number=number,
                partial=partial,
            )
    return Dataset(isolated_database, org_a, org_b, snapshots, executions)


def read(
    dataset,
    *,
    scopes,
    view="current",
    filters=None,
    number=NUMBER,
    page=1,
    page_size=25,
    sort="updated_desc",
):
    query = workorder_snapshot_query(
        organization_scopes=scopes,
        filters=filters,
        view=view,
        workorder_number=number,
    )
    with psycopg.connect(dataset.url, row_factory=dict_row) as connection:
        return query.page(connection, page=page, page_size=page_size, sort=sort)


def test_default_history_preserves_three_versions_in_one_iam_organization(dataset):
    query = workorder_snapshot_query(
        organization_scopes=frozenset({dataset.org_a}), workorder_number=NUMBER
    )
    with psycopg.connect(dataset.url, row_factory=dict_row) as connection:
        rows, total = query.page(connection, page=1, page_size=25, sort="updated_desc")
    assert total == 3
    assert {row["snapshot_id"] for row in rows} == {
        dataset.snapshots[label] for label in ("old", "z-tie-earlier", "a-tie-later")
    }
    assert {row["organization_id"] for row in rows} == {dataset.org_a}
    # Backwards-compatible list ordering is independent of current selection.
    assert [row["execution_id"] for row in rows[:2]] == [
        dataset.executions["z-tie-earlier"],
        dataset.executions["a-tie-later"],
    ]


def test_current_breaks_update_tie_by_id_and_keeps_partial_snapshot_intact(dataset):
    rows, total = read(dataset, scopes=frozenset({dataset.org_a}))
    assert total == 1
    chosen = rows[0]
    assert chosen["snapshot_id"] == dataset.snapshots["a-tie-later"]
    assert chosen["execution_id"] == dataset.executions["a-tie-later"]
    assert chosen["organization_id"] == dataset.org_a
    assert chosen["organization_id"] != chosen["business_organization_id"]
    assert chosen["planned_quantity"] is None
    assert chosen["produced_quantity"] == 0
    assert chosen["received_quantity"] == 9
    assert chosen["pending_quantity"] is None
    assert chosen["retained_quantity"] is None


def test_current_list_order_breaks_ties_by_snapshot_id_across_organizations(dataset):
    rows, total = read(dataset, scopes=None)
    assert total == 2
    assert [row["snapshot_id"] for row in rows] == [
        dataset.snapshots["b-current"],
        dataset.snapshots["a-tie-later"],
    ]


@pytest.mark.parametrize("view,expected", [("current", 2), ("history", 4)])
def test_global_scope_keeps_organizations_separate_and_excludes_unknown_iam(
    dataset, view, expected
):
    rows, total = read(dataset, scopes=None, view=view)
    assert total == expected
    assert {row["organization_id"] for row in rows} == {dataset.org_a, dataset.org_b}
    assert dataset.snapshots["unknown-iam"] not in {row["snapshot_id"] for row in rows}


@pytest.mark.parametrize("view,expected", [("current", 1), ("history", 3)])
def test_scoped_read_excludes_other_organizations_and_unpublished_executions(
    dataset, view, expected
):
    rows, total = read(dataset, scopes=frozenset({dataset.org_a}), view=view)
    assert total == expected
    assert {row["execution_id"] for row in rows} <= {
        dataset.executions[label] for label in ("old", "z-tie-earlier", "a-tie-later")
    }


def test_scope_intersects_requested_organization_before_counting(dataset):
    for scopes in (frozenset(), frozenset({dataset.org_a})):
        rows, total = read(
            dataset,
            scopes=scopes,
            filters=ExecutionQueryFilters(organization_id=dataset.org_b),
        )
        assert (rows, total) == ([], 0)


def test_period_filters_execution_start_before_selecting_the_latest_version(dataset):
    rows, total = read(
        dataset,
        scopes=frozenset({dataset.org_a}),
        filters=ExecutionQueryFilters(
            date_from=INSTANT, date_to=INSTANT + timedelta(days=1)
        ),
    )
    assert total == 1
    assert rows[0]["snapshot_id"] == dataset.snapshots["z-tie-earlier"]
    assert rows[0]["updated_at"] > INSTANT + timedelta(days=1)


def test_period_bounds_are_inclusive_and_do_not_use_workorder_update_time(dataset):
    rows, total = read(
        dataset,
        scopes=frozenset({dataset.org_a}),
        filters=ExecutionQueryFilters(date_from=INSTANT, date_to=INSTANT),
    )
    assert total == 1
    assert rows[0]["snapshot_id"] == dataset.snapshots["old"]


def test_explicit_execution_pins_history_even_in_current_view(dataset):
    rows, total = read(
        dataset,
        scopes=frozenset({dataset.org_a}),
        filters=ExecutionQueryFilters(execution_id=dataset.executions["old"]),
    )
    assert total == 1
    assert rows[0]["snapshot_id"] == dataset.snapshots["old"]
    hidden, hidden_total = read(
        dataset,
        scopes=frozenset({dataset.org_a}),
        filters=ExecutionQueryFilters(execution_id=dataset.executions["b-current"]),
    )
    assert (hidden, hidden_total) == ([], 0)


@pytest.mark.parametrize("sort", ["updated_desc", "identifier_asc"])
def test_pagination_follows_current_selection_and_remains_stable(dataset, sort):
    chosen = []
    for page in (1, 2, 3):
        rows, total = read(
            dataset, scopes=None, number=None, page=page, page_size=1, sort=sort
        )
        again, again_total = read(
            dataset, scopes=None, number=None, page=page, page_size=1, sort=sort
        )
        assert total == again_total == 3
        assert rows == again
        chosen.extend(row["snapshot_id"] for row in rows)
    assert set(chosen) == {
        dataset.snapshots[label]
        for label in ("a-tie-later", "b-current", "other-number")
    }
    beyond, total = read(dataset, scopes=None, number=None, page=4, page_size=1)
    assert (beyond, total) == ([], 3)


@pytest.mark.parametrize("number", ["WO-01", "WO-001' OR TRUE --"])
def test_identifiers_preserve_leading_zeros_and_are_literal_sql_parameters(
    dataset, number
):
    assert read(dataset, scopes=frozenset({dataset.org_a}), number=number) == ([], 0)


def test_same_selected_relation_can_supply_future_aggregates(dataset):
    query = workorder_snapshot_query(
        organization_scopes=frozenset({dataset.org_a}), view="current"
    )
    with psycopg.connect(dataset.url) as connection:
        total = connection.execute(
            query.cte + " SELECT count(*) FROM workorder_snapshots", query.parameters
        ).fetchone()[0]
    assert total == 2


def test_page_count_and_items_share_a_read_only_snapshot_during_concurrent_import(
    dataset,
):
    class ConcurrentImport:
        def __init__(self, connection):
            self.connection = connection
            self.inserted = False

        def execute(self, statement, parameters=None):
            result = self.connection.execute(statement, parameters)
            if not self.inserted and "count(*)" in statement:
                with psycopg.connect(dataset.url) as writer:
                    insert_snapshot(
                        writer,
                        organization=dataset.org_a,
                        label="concurrent",
                        started=INSTANT,
                        updated=INSTANT,
                        number="WO-003",
                    )
                self.inserted = True
            return result

    query = workorder_snapshot_query(
        organization_scopes=frozenset({dataset.org_a}), view="current"
    )
    with psycopg.connect(dataset.url, row_factory=dict_row) as connection:
        concurrent = ConcurrentImport(connection)
        rows, total = query.page(concurrent, page=1, page_size=25, sort="updated_desc")
        assert concurrent.inserted
        assert (
            connection.execute("SHOW transaction_read_only").fetchone()[
                "transaction_read_only"
            ]
            == "on"
        )
    assert total == len(rows) == 2
    assert {row["workorder_number"] for row in rows} == {NUMBER, "WO-002"}
    # The concurrent import was committed, but could not change the page midway.
    assert read(dataset, scopes=frozenset({dataset.org_a}), number=None)[1] == 3
