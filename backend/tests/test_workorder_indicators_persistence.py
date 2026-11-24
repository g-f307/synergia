"""Coverage aggregates on real PostgreSQL, using only private synthetic data."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from app.execution_filters import ExecutionQueryFilters
from app.execution_summary import start_execution_snapshot
from app.workorder_indicators import read_current_workorder_indicators
from app.workorder_snapshots import workorder_snapshot_query
from tests.test_workorder_snapshots_persistence import INSTANT

pytest_plugins = ("tests.test_workorder_snapshots_persistence",)
pytestmark = [pytest.mark.integration, pytest.mark.security]

QUANTITIES = ("planned", "produced", "received", "released")


@dataclass(frozen=True)
class CoverageDataset:
    url: str
    org_a: UUID
    org_b: UUID
    executions: dict[str, str]


def add_version(
    connection,
    *,
    organization,
    number="WO-001",
    day=1,
    updated_day=None,
    quantities=(4, 0, None, 0),
    partial=None,
    state="completed",
    source="OWM",
    extension="json",
):
    execution = "synthetic-196-" + uuid4().hex
    connection.execute(
        "INSERT INTO synergia.executions "
        "(id,organization_id,status,source,started_at) VALUES (%s,%s,%s,%s,%s)",
        (execution, organization, state, source, INSTANT + timedelta(days=day)),
    )
    file_id = connection.execute(
        "INSERT INTO synergia.source_files "
        "(execution_id,file_name,content_hash,source,extension) "
        "VALUES (%s,'synthetic.json',%s,%s,%s) RETURNING id",
        (execution, uuid4().hex * 2, source, extension),
    ).fetchone()[0]
    business = connection.execute(
        "INSERT INTO synergia.organizations "
        "(organization_code,execution_id,source_file_id) "
        "VALUES ('SAME-WORKBOOK-CODE',%s,%s) RETURNING id",
        (execution, file_id),
    ).fetchone()[0]
    snapshot = connection.execute(
        "INSERT INTO synergia.workorders "
        "(workorder_number,organization_id,execution_id,source_file_id,"
        "processing_status,updated_at,planned_quantity,produced_quantity,"
        "received_quantity,released_quantity,partially_released) "
        "VALUES (%s,%s,%s,%s,'consolidated',%s,%s,%s,%s,%s,%s) RETURNING id",
        (
            number,
            business,
            execution,
            file_id,
            INSTANT + timedelta(days=day if updated_day is None else updated_day),
            *quantities,
            partial,
        ),
    ).fetchone()[0]
    return snapshot, execution


@pytest.fixture
def coverage_dataset(isolated_database):
    a, b = uuid4(), uuid4()
    executions = {}
    with psycopg.connect(isolated_database) as connection:
        for organization in (a, b):
            connection.execute(
                "INSERT INTO synergia.iam_organizations "
                "(id,organization_code,display_name) "
                "VALUES (%s,%s,'Synthetic coverage')",
                (organization, "syn196-" + organization.hex),
            )
        for index, value in enumerate((4, None, 0), 1):
            _, executions[str(index)] = add_version(
                connection,
                organization=a,
                number=f"WO-{index:03d}",
                quantities=(value, 0, None, 0 if index != 2 else None),
                partial=False if index == 3 else None,
            )
        _, executions["old"] = add_version(
            connection,
            organization=a,
            day=0,
            quantities=(400, 500, 600, 400),
            partial=True,
        )
        _, executions["outside"] = add_version(
            connection,
            organization=b,
            quantities=(999, 666, 55, 44),
            partial=True,
        )
        add_version(
            connection,
            organization=None,
            day=9,
            quantities=(10000, 10000, 10000, 10000),
        )
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
            add_version(
                connection,
                organization=a,
                day=9,
                state=state,
                quantities=(99999, 99999, 99999, 99999),
            )
    return CoverageDataset(isolated_database, a, b, executions)


def read(dataset, *, scopes=None, filters=None):
    with psycopg.connect(dataset.url) as connection:
        start_execution_snapshot(connection)
        return read_current_workorder_indicators(
            connection,
            organization_scopes=scopes,
            filters=filters,
        )


def test_four_null_zero_is_known_subtotal_and_zero_is_informed(coverage_dataset):
    ds = coverage_dataset
    result = read(ds, scopes=frozenset([ds.org_a]))
    assert result.total == 3
    assert result.partially_released == 0
    planned = result.quantities_coverage["planned"]
    assert (planned.known_sum, planned.known_count, planned.total_count) == (4, 2, 3)
    assert planned.state == "partial"
    assert planned.coverage_percent == 100 * 2 / 3
    assert planned.coverage_percent != round(planned.coverage_percent, 2)
    assert set(result.quantities_coverage) == set(QUANTITIES)


def test_complete_zero_missing_and_partial_zero_are_distinct(coverage_dataset):
    ds = coverage_dataset
    coverage = read(ds, scopes=frozenset([ds.org_a])).quantities_coverage
    complete = coverage["produced"]
    assert (complete.state, complete.known_sum, complete.known_count) == (
        "complete",
        0,
        3,
    )
    assert complete.coverage_percent == 100
    missing = coverage["received"]
    assert (missing.state, missing.known_sum, missing.known_count) == (
        "missing",
        None,
        0,
    )
    assert missing.total_count == 3 and missing.coverage_percent == 0
    partial = coverage["released"]
    assert (partial.state, partial.known_sum, partial.known_count) == ("partial", 0, 2)


@pytest.mark.parametrize(
    "restriction", ["empty_scope", "outside_period", "outside_org"]
)
def test_empty_never_invents_zero_or_a_coverage_percentage(
    coverage_dataset, restriction
):
    ds = coverage_dataset
    scopes = frozenset() if restriction == "empty_scope" else frozenset([ds.org_a])
    filters = None
    if restriction == "outside_period":
        filters = ExecutionQueryFilters(date_from=INSTANT + timedelta(days=20))
    elif restriction == "outside_org":
        filters = ExecutionQueryFilters(organization_id=ds.org_b)
    result = read(ds, scopes=scopes, filters=filters)
    assert result.total == result.partially_released == 0
    for item in result.quantities_coverage.values():
        assert (item.state, item.known_sum, item.coverage_percent) == (
            "empty",
            None,
            None,
        )
        assert item.known_count == item.total_count == 0


def test_all_null_quantities_remain_missing_without_inventing_subtotals(
    coverage_dataset,
):
    ds = coverage_dataset
    with psycopg.connect(ds.url) as connection:
        for number in ("WO-001", "WO-002", "WO-003"):
            add_version(
                connection,
                organization=ds.org_a,
                day=2,
                number=number,
                quantities=(None, None, None, None),
            )
    result = read(ds, scopes=frozenset([ds.org_a]))
    assert result.total == 3
    for item in result.quantities_coverage.values():
        assert item.known_sum is None
        assert item.known_count == 0
        assert item.total_count == 3
        assert item.coverage_percent == 0
        assert item.state == "missing"


def test_new_version_replaces_value_without_increasing_denominator(coverage_dataset):
    ds = coverage_dataset
    with psycopg.connect(ds.url) as connection:
        add_version(
            connection, organization=ds.org_a, day=2, quantities=(7, 0, None, 0)
        )
    result = read(ds, scopes=frozenset([ds.org_a]))
    planned = result.quantities_coverage["planned"]
    assert result.total == planned.total_count == 3
    assert planned.known_sum == 7  # neither 4+7 nor old 400
    assert planned.known_count == 2


def test_newer_partial_version_never_uses_older_complete_values(coverage_dataset):
    ds = coverage_dataset
    with psycopg.connect(ds.url) as connection:
        add_version(
            connection,
            organization=ds.org_a,
            day=2,
            quantities=(None, None, None, None),
            partial=None,
            state="completed_with_errors",
        )
    result = read(ds, scopes=frozenset([ds.org_a]))
    planned = result.quantities_coverage["planned"]
    assert result.total == 3
    assert (planned.known_sum, planned.known_count, planned.state) == (0, 1, "partial")
    assert result.quantities_coverage["produced"].known_count == 2
    assert result.partially_released == 0


def test_update_tie_is_broken_by_snapshot_id(coverage_dataset):
    ds = coverage_dataset
    with psycopg.connect(ds.url) as connection:
        add_version(
            connection,
            organization=ds.org_a,
            day=2,
            updated_day=1,
            quantities=(8, 0, None, 0),
        )
        add_version(
            connection,
            organization=ds.org_a,
            day=3,
            updated_day=1,
            quantities=(None, 0, None, 0),
        )
    planned = read(ds, scopes=frozenset([ds.org_a])).quantities_coverage["planned"]
    assert (planned.known_sum, planned.known_count, planned.total_count) == (0, 1, 3)


def test_iam_organizations_stay_separate_even_with_same_workbook_code(coverage_dataset):
    ds = coverage_dataset
    a = read(ds, scopes=frozenset([ds.org_a]))
    b = read(ds, scopes=frozenset([ds.org_b]))
    global_result = read(ds)
    both = read(ds, scopes=frozenset([ds.org_a, ds.org_b]))
    assert global_result == both
    assert (a.total, b.total, both.total) == (3, 1, 4)
    assert both.quantities_coverage["planned"].known_sum == 1003
    assert both.quantities_coverage["planned"].known_count == 3
    assert both.partially_released == 1
    assert b.quantities_coverage["planned"].state == "complete"
    selected = read(ds, filters=ExecutionQueryFilters(organization_id=ds.org_a))
    assert selected == a


def test_period_filters_execution_start_before_current_selection(coverage_dataset):
    ds = coverage_dataset
    before = read(
        ds,
        scopes=frozenset([ds.org_a]),
        filters=ExecutionQueryFilters(
            date_from=INSTANT,
            date_to=INSTANT,
        ),
    )
    assert before.total == before.partially_released == 1
    assert before.quantities_coverage["planned"].known_sum == 400
    assert before.quantities_coverage["planned"].state == "complete"
    with psycopg.connect(ds.url) as connection:
        add_version(
            connection,
            organization=ds.org_a,
            day=2,
            updated_day=30,
            quantities=(8, 0, None, 0),
        )
    included = read(
        ds,
        scopes=frozenset([ds.org_a]),
        filters=ExecutionQueryFilters(
            date_from=INSTANT + timedelta(days=1),
            date_to=INSTANT + timedelta(days=2),
        ),
    )
    assert included.total == 3
    assert included.quantities_coverage["planned"].known_sum == 8


def test_execution_filter_pins_old_snapshot_and_cannot_expand_scope(coverage_dataset):
    ds = coverage_dataset
    old = read(
        ds,
        scopes=frozenset([ds.org_a]),
        filters=ExecutionQueryFilters(
            execution_id=ds.executions["old"],
        ),
    )
    assert old.total == 1
    assert old.quantities_coverage["planned"].known_sum == 400
    assert old.partially_released == 1
    excluded = read(
        ds,
        scopes=frozenset([ds.org_a]),
        filters=ExecutionQueryFilters(
            execution_id=ds.executions["outside"],
        ),
    )
    assert excluded.total == 0


def test_all_dashboard_filters_apply_before_selection(coverage_dataset):
    ds = coverage_dataset
    with psycopg.connect(ds.url) as connection:
        add_version(
            connection,
            organization=ds.org_a,
            day=2,
            quantities=(8, 0, None, 0),
            source="N-FP",
            extension="csv",
            state="completed_with_errors",
        )
    filters = [
        ExecutionQueryFilters(source="OWM"),
        ExecutionQueryFilters(file_type="json"),
        ExecutionQueryFilters(status="completed"),
        ExecutionQueryFilters(outcome="completed"),
    ]
    for value in filters:
        result = read(ds, scopes=frozenset([ds.org_a]), filters=value)
        assert result.total == 3
        assert result.quantities_coverage["planned"].known_sum == 4
    error_result = read(
        ds,
        scopes=frozenset([ds.org_a]),
        filters=ExecutionQueryFilters(
            outcome="partial",
        ),
    )
    assert error_result.total == 1
    assert error_result.quantities_coverage["planned"].known_sum == 8


def test_denominator_matches_entire_current_list_not_just_one_page(coverage_dataset):
    ds = coverage_dataset
    result = read(ds)
    selected = workorder_snapshot_query(organization_scopes=None, view="current")
    ids = set()
    for page in range(1, 5):
        with psycopg.connect(ds.url, row_factory=dict_row) as connection:
            rows, total = selected.page(
                connection, page=page, page_size=1, sort="updated_desc"
            )
        assert total == result.total == 4
        assert len(rows) == 1
        ids.add(rows[0]["snapshot_id"])
    assert len(ids) == result.total
    assert all(
        item.total_count == result.total for item in result.quantities_coverage.values()
    )


def test_sum_is_an_integer_even_above_postgres_integer_range(coverage_dataset):
    ds = coverage_dataset
    with psycopg.connect(ds.url) as connection:
        for number in ("WO-001", "WO-002", "WO-003"):
            add_version(
                connection,
                organization=ds.org_a,
                day=2,
                number=number,
                quantities=(2147483647, 0, None, 0),
            )
    planned = read(ds, scopes=frozenset([ds.org_a])).quantities_coverage["planned"]
    assert type(planned.known_sum) is int
    assert planned.known_sum == 6442450941
    assert planned.state == "complete"
    assert planned.coverage_percent == 100


def test_reader_preserves_callers_snapshot_and_historical_rows(coverage_dataset):
    ds = coverage_dataset
    scopes = frozenset([ds.org_a])
    with psycopg.connect(ds.url) as connection:
        start_execution_snapshot(connection)
        history_before = connection.execute(
            "SELECT id,execution_id,planned_quantity,updated_at "
            "FROM synergia.workorders ORDER BY id"
        ).fetchall()
        first = read_current_workorder_indicators(
            connection, organization_scopes=scopes
        )
        with psycopg.connect(ds.url) as writer:
            add_version(
                writer, organization=ds.org_a, day=2, quantities=(8, 0, None, 0)
            )
        second = read_current_workorder_indicators(
            connection, organization_scopes=scopes
        )
        assert first == second
        assert connection.execute("SHOW transaction_read_only").fetchone()[0] == "on"
        assert (
            connection.execute("SHOW transaction_isolation").fetchone()[0]
            == "repeatable read"
        )
        assert (
            connection.execute(
                "SELECT id,execution_id,planned_quantity,updated_at "
                "FROM synergia.workorders ORDER BY id"
            ).fetchall()
            == history_before
        )
    fresh = read(ds, scopes=scopes)
    assert first.quantities_coverage["planned"].known_sum == 4
    assert fresh.quantities_coverage["planned"].known_sum == 8
