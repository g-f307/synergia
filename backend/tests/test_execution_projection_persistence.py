"""Exercise the shared projections and predicates in real PostgreSQL."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from app.execution import ExecutionState
from app.execution_filters import ExecutionQueryFilters, build_execution_predicate
from app.execution_projection import (
    ExecutionOutcome,
    execution_outcome,
    legacy_lifecycle,
    legacy_lifecycle_sql,
    outcome_sql,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def connection():
    # All fixture writes are rolled back; no shared outbox or business row is deleted.
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        try:
            yield conn
        finally:
            conn.rollback()


def test_postgres_projection_matches_python_for_all_states_and_unknown(connection):
    states = [state.value for state in ExecutionState] + ["future_state", None]
    values = ",".join("(%s::text)" for _ in states)
    rows = connection.execute(
        f"""SELECT e.status, {outcome_sql("e", "status")},
            {legacy_lifecycle_sql("e", "status")}
            FROM (VALUES {values}) AS e(status)""",
        states,
    ).fetchall()
    for state, outcome, legacy in rows:
        assert outcome == execution_outcome(state)
        assert legacy == legacy_lifecycle(state)


def test_postgres_reconciles_the_required_three_two_nine_scenario(connection):
    states = ["completed"] * 3 + ["completed_with_errors"] * 2 + ["duplicate"] * 9
    values = ",".join("(%s::text)" for _ in states)
    counts = dict(
        connection.execute(
            f"SELECT {outcome_sql('e', 'status')} AS outcome, count(*) "
            f"FROM (VALUES {values}) AS e(status) GROUP BY outcome",
            states,
        ).fetchall()
    )
    assert counts == {"completed": 3, "partial": 2, "skipped_duplicate": 9}
    assert sum(counts.values()) == 14


def test_predicates_combine_scope_file_type_states_and_closed_period(connection):
    org_a, org_b = uuid4(), uuid4()
    for organization in (org_a, org_b):
        connection.execute(
            "INSERT INTO synergia.iam_organizations "
            "(id, organization_code, display_name) VALUES (%s,%s,%s)",
            (organization, f"syn193-{organization.hex}", "Synthetic projection test"),
        )
    start = datetime(2026, 11, 1, 12, tzinfo=UTC)
    end = start + timedelta(minutes=1)
    fixtures = [
        ("start", org_a, "completed", "OWM", start, ["csv", "xlsx"]),
        ("end", org_a, "completed", "OWM", end, ["csv"]),
        ("duplicate", org_a, "duplicate", "OWM", start, ["csv"]),
        ("other_source", org_a, "completed", "N-FP", start, ["csv"]),
        ("other_org", org_b, "completed", "OWM", start, ["csv"]),
        ("unknown_iam", None, "completed", "OWM", start, ["csv"]),
        ("before", org_a, "completed", "OWM", start - timedelta(microseconds=1), []),
        ("after", org_a, "completed", "OWM", end + timedelta(microseconds=1), []),
        ("no_files", org_a, "completed", "OWM", start, []),
        ("json_only", org_a, "completed", "OWM", start, ["json"]),
    ]
    ids = {name: f"syn193-{uuid4().hex}" for name, *_ in fixtures}
    for name, organization, status, source, instant, extensions in fixtures:
        connection.execute(
            "INSERT INTO synergia.executions "
            "(id, organization_id, status, source, started_at) VALUES (%s,%s,%s,%s,%s)",
            (ids[name], organization, status, source, instant),
        )
        for extension in extensions:
            connection.execute(
                "INSERT INTO synergia.source_files "
                "(execution_id, file_name, content_hash, extension) "
                "VALUES (%s,%s,%s,%s)",
                (ids[name], f"synthetic.{extension}", uuid4().hex * 2, extension),
            )

    def select(filters, scopes):
        predicate = build_execution_predicate(filters, organization_scopes=scopes)
        parameters = (list(ids.values()), *predicate.parameters)
        where = f"e.id = ANY(%s) AND ({predicate.where})"
        selected = connection.execute(
            f"SELECT e.id FROM synergia.executions e WHERE {where}", parameters
        ).fetchall()
        count = connection.execute(
            f"SELECT count(*) FROM synergia.executions e WHERE {where}", parameters
        ).fetchone()[0]
        assert count == len(selected)
        return {identifier for (identifier,) in selected}

    filters = dict(source="OWM", file_type=".CSV", date_from=start, date_to=end)
    scope_a = frozenset({org_a})
    assert select(ExecutionQueryFilters(**filters), scope_a) == {
        ids["start"],
        ids["end"],
        ids["duplicate"],
    }
    assert select(ExecutionQueryFilters(**filters), None) == {
        ids["start"],
        ids["end"],
        ids["duplicate"],
        ids["other_org"],
    }
    assert select(ExecutionQueryFilters(**filters), frozenset()) == set()
    assert select(ExecutionQueryFilters(organization_id=org_b), scope_a) == set()
    assert select(ExecutionQueryFilters(), None) == {
        identifier for name, identifier in ids.items() if name != "unknown_iam"
    }
    assert select(ExecutionQueryFilters(**filters, lifecycle="completed"), scope_a) == {
        ids["start"],
        ids["end"],
        ids["duplicate"],
    }
    assert select(
        ExecutionQueryFilters(**filters, outcome=ExecutionOutcome.COMPLETED), scope_a
    ) == {ids["start"], ids["end"]}
    assert select(ExecutionQueryFilters(**filters, status="duplicate"), scope_a) == {
        ids["duplicate"]
    }
    assert select(
        ExecutionQueryFilters(**filters, execution_id=ids["end"]), scope_a
    ) == {ids["end"]}
    assert (
        select(
            ExecutionQueryFilters(**filters, outcome=ExecutionOutcome.FAILED), scope_a
        )
        == set()
    )
