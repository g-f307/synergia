from __future__ import annotations

import hashlib
import os
from copy import deepcopy

import psycopg
import pytest
from psycopg import sql

from app.imports import PostgresImportRepository
from app.persistence import PostgresProcessingRepository
from app.processing import process_normalized_records
from app.queries import PostgresQueryRepository

pytestmark = pytest.mark.integration
_CREATED_EXECUTION_IDS: set[str] = set()


@pytest.fixture(autouse=True)
def cleanup_created_executions():
    """Remove committed fixtures so integration tests remain order-independent."""
    _CREATED_EXECUTION_IDS.clear()
    yield
    if not _CREATED_EXECUTION_IDS:
        return
    execution_ids = sorted(_CREATED_EXECUTION_IDS)
    targets = (
        ("pending_items", "execution_id"),
        ("holds", "execution_id"),
        ("oqc_decisions", "execution_id"),
        ("classifications", "execution_id"),
        ("rule_evaluations", "execution_id"),
        ("consolidated_field_provenance", "execution_id"),
        ("audit_events", "execution_id"),
        ("execution_idempotency", "execution_id"),
        ("execution_state_transitions", "execution_id"),
        ("pipeline_issues", "execution_id"),
        ("pipeline_summaries", "execution_id"),
        ("normalized_records", "execution_id"),
        ("imported_records", "execution_id"),
        ("serials", "execution_id"),
        ("lots", "execution_id"),
        ("workorders", "execution_id"),
        ("organizations", "execution_id"),
        ("source_files", "execution_id"),
        ("executions", "id"),
    )
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for table, column in targets:
            connection.execute(
                sql.SQL("DELETE FROM synergia.{} WHERE {} = ANY(%s)").format(
                    sql.Identifier(table), sql.Identifier(column)
                ),
                (execution_ids,),
            )
    _CREATED_EXECUTION_IDS.clear()


def _seed_execution(
    execution_id: str, sources: list[str], *, status: str = "completed"
) -> list[int]:
    _CREATED_EXECUTION_IDS.add(execution_id)
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            "INSERT INTO synergia.executions (id, status, source) "
            "VALUES (%s, %s, %s)",
            (execution_id, status, sources[0]),
        )
        ids = []
        for index, source in enumerate(sources, 1):
            ids.append(
                connection.execute(
                    """
                    INSERT INTO synergia.source_files
                        (execution_id, source, file_name, content_hash)
                    VALUES (%s, %s, %s, %s) RETURNING id
                    """,
                    (
                        execution_id,
                        source,
                        f"{execution_id}-{index}.csv",
                        hashlib.sha256(f"{execution_id}:{index}".encode()).hexdigest(),
                    ),
                ).fetchone()[0]
            )
    return ids


def _record(execution_id: str, source: str, source_file_id: int, row: int, values):
    return {
        "execution_id": execution_id,
        "source": source,
        "source_file_id": source_file_id,
        "sheet": "CSV",
        "row": row,
        "values": values,
        "original_values": deepcopy(values),
        "transformations": [],
    }


@pytest.mark.parametrize("defer_rule_details", [False, True])
def test_persists_complete_processing_and_survives_repository_restart(
    defer_rule_details: bool,
) -> None:
    execution_id = f"exec-persistence-complete-{int(defer_rule_details)}"
    plan_file, receipt_file, quality_file = _seed_execution(
        execution_id, ["N-FP", "OWM", "GMES/OQC"]
    )
    processing = process_normalized_records(
        [
            _record(
                execution_id,
                "N-FP",
                plan_file,
                2,
                {
                    "workorder_number": "WO-PERSIST-1",
                    "lot_number": "LOT-PERSIST-1",
                    "serial_number": "SER-PERSIST-1",
                    "organization_code": "ORG-PERSIST-1",
                    "planned_quantity": 10,
                },
            ),
            _record(
                execution_id,
                "OWM",
                receipt_file,
                2,
                {
                    "workorder_number": "WO-PERSIST-1",
                    "received_quantity": 10,
                    "released_quantity": 6,
                },
            ),
            _record(
                execution_id,
                "GMES/OQC",
                quality_file,
                2,
                {
                    "workorder_number": "WO-PERSIST-1",
                    "lot_number": "LOT-PERSIST-1",
                    "serial_number": "SER-PERSIST-1",
                    "status": "hold",
                    "reason": "Aguardando inspeção",
                },
            ),
        ],
        execution_id=execution_id,
        classified_at="2026-08-30T12:00:00+00:00",
        defer_rule_details=defer_rule_details,
    )

    persisted = PostgresProcessingRepository(os.environ["DATABASE_URL"]).persist(
        execution_id, processing
    )

    assert persisted == {
        "confirmed_workorders": ["WO-PERSIST-1"],
        "failed_workorders": [],
    }
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM synergia.workorders WHERE execution_id = %s),
              (SELECT count(*) FROM synergia.classifications WHERE execution_id = %s),
              (SELECT count(*) FROM synergia.pending_items WHERE execution_id = %s),
              (SELECT count(*) FROM synergia.consolidated_field_provenance
               WHERE execution_id = %s),
              (SELECT count(*) FROM synergia.rule_evaluations WHERE execution_id = %s)
            """,
            (execution_id,) * 5,
        ).fetchone()
    assert counts[0] == 1
    assert counts[1] >= 1
    assert counts[2] >= 1
    assert counts[3] >= 1
    assert counts[4] >= 1

    restarted_repository = PostgresQueryRepository(os.environ["DATABASE_URL"])
    result = restarted_repository.get_consolidated("WO-PERSIST-1")
    assert result is not None
    assert result["workorder"]["planned_quantity"] == 10
    assert result["workorder"]["released_quantity"] == 6
    assert result["workorder"]["partially_released"] is True
    assert result["pending_items"]
    assert result["holds"]
    assert result["holds"][0]["post_release"] is True
    assert result["oqc_decisions"][0]["decision_state"] == "rejected"
    assert result["pending_items"][0]["priority_score"] is not None
    assert result["classifications"]
    assert result["rule_evaluations"]
    assert result["provenance"]


def test_reuses_organization_within_execution() -> None:
    execution_id = "exec-persistence-shared-org"
    (source_file_id,) = _seed_execution(execution_id, ["N-FP"])
    processing = process_normalized_records(
        [
            _record(
                execution_id,
                "N-FP",
                source_file_id,
                row,
                {
                    "workorder_number": workorder,
                    "organization_code": "ORG-SHARED",
                    "planned_quantity": row,
                },
            )
            for row, workorder in ((2, "WO-SHARED-A"), (3, "WO-SHARED-B"))
        ],
        execution_id=execution_id,
        classified_at="2026-08-30T12:00:00+00:00",
    )

    persisted = PostgresProcessingRepository(os.environ["DATABASE_URL"]).persist(
        execution_id, processing
    )

    assert persisted["confirmed_workorders"] == ["WO-SHARED-A", "WO-SHARED-B"]
    assert persisted["failed_workorders"] == []


def test_rolls_back_failed_workorder_and_confirms_independent_unit() -> None:
    execution_id = "exec-persistence-partial"
    (source_file_id,) = _seed_execution(execution_id, ["N-FP"])
    processing = process_normalized_records(
        [
            _record(
                execution_id,
                "N-FP",
                source_file_id,
                2,
                {"workorder_number": "WO-BAD-PERSIST", "planned_quantity": 1},
            ),
            _record(
                execution_id,
                "N-FP",
                source_file_id,
                3,
                {"workorder_number": "WO-GOOD-PERSIST", "planned_quantity": 2},
            ),
        ],
        execution_id=execution_id,
        classified_at="2026-08-30T12:00:00+00:00",
    )
    bad = next(
        item
        for item in processing["consolidation"]["workorders"]
        if item["workorder_number"] == "WO-BAD-PERSIST"
    )
    for origins in bad["provenance"].values():
        for origin in origins:
            origin["source_file_id"] = 9_999_999

    persisted = PostgresProcessingRepository(os.environ["DATABASE_URL"]).persist(
        execution_id, processing
    )

    assert persisted["confirmed_workorders"] == ["WO-GOOD-PERSIST"]
    assert persisted["failed_workorders"][0]["workorder_number"] == ("WO-BAD-PERSIST")
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        workorders = connection.execute(
            "SELECT workorder_number FROM synergia.workorders "
            "WHERE execution_id = %s ORDER BY workorder_number",
            (execution_id,),
        ).fetchall()
        failures = connection.execute(
            "SELECT count(*) FROM synergia.audit_events "
            "WHERE execution_id = %s "
            "AND event_type = 'processing_persistence_failed'",
            (execution_id,),
        ).fetchone()[0]
    assert workorders == [("WO-GOOD-PERSIST",)]
    assert failures == 1


def test_f03_interruption_after_workorder_writes_rolls_back_entire_unit(
    monkeypatch,
) -> None:
    execution_id = "exec-persistence-f03-interrupted"
    source_file_id = _seed_execution(execution_id, ["N-FP"])[0]
    processing = process_normalized_records(
        [
            _record(
                execution_id,
                "N-FP",
                source_file_id,
                2,
                {
                    "workorder_number": "WO-F03-INTERRUPTED",
                    "organization_code": "ORG-F03",
                    "lot_number": "LOT-F03",
                    "serial_number": "SER-F03",
                    "planned_quantity": 1,
                },
            )
        ],
        execution_id=execution_id,
        classified_at="2026-08-30T12:00:00+00:00",
    )
    repository = PostgresProcessingRepository(os.environ["DATABASE_URL"])
    original = repository._persist_workorder

    def interrupt_after_writes(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic F03 interruption before unit commit")

    monkeypatch.setattr(repository, "_persist_workorder", interrupt_after_writes)
    persisted = repository.persist(execution_id, processing)

    assert persisted["confirmed_workorders"] == []
    assert len(persisted["failed_workorders"]) == 1
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for table in (
            "organizations",
            "workorders",
            "lots",
            "serials",
            "consolidated_field_provenance",
            "classifications",
        ):
            count = connection.execute(
                sql.SQL(
                    "SELECT count(*) FROM synergia.{} WHERE execution_id = %s"
                ).format(sql.Identifier(table)),
                (execution_id,),
            ).fetchone()[0]
            assert count == 0, table
        audit = connection.execute(
            "SELECT count(*) FROM synergia.audit_events "
            "WHERE execution_id = %s AND event_type = 'processing_persistence_failed'",
            (execution_id,),
        ).fetchone()[0]
        assert audit == 1


def test_f04_committed_unit_is_hidden_until_execution_finishes() -> None:
    """Keep committed units private during the inter-transaction crash window."""
    execution_id = "exec-persistence-f04-crash-window"
    source_file_id = _seed_execution(
        execution_id, ["N-FP"], status="applying_rules"
    )[0]
    query_repository = PostgresQueryRepository(os.environ["DATABASE_URL"])
    baseline_workorders = query_repository.indicators()["workorders"]["total"]
    processing = process_normalized_records(
        [
            _record(
                execution_id,
                "N-FP",
                source_file_id,
                2,
                {
                    "workorder_number": "WO-F04-CRASH-WINDOW",
                    "organization_code": "ORG-F04",
                    "lot_number": "LOT-F04-CRASH-WINDOW",
                    "serial_number": "SER-F04-CRASH-WINDOW",
                    "planned_quantity": 1,
                },
            )
        ],
        execution_id=execution_id,
        classified_at="2026-08-30T12:00:00+00:00",
    )
    persisted = PostgresProcessingRepository(os.environ["DATABASE_URL"]).persist(
        execution_id, processing
    )
    assert persisted["confirmed_workorders"] == ["WO-F04-CRASH-WINDOW"]
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        state = connection.execute(
            "SELECT status FROM synergia.executions WHERE id = %s", (execution_id,)
        ).fetchone()[0]
        workorder_id = connection.execute(
            "SELECT id FROM synergia.workorders WHERE execution_id = %s",
            (execution_id,),
        ).fetchone()[0]
        pending_id = connection.execute(
            "INSERT INTO synergia.pending_items "
            "(workorder_id, execution_id, source_file_id, category, reason) "
            "VALUES (%s, %s, %s, 'synthetic_fault', 'F04 test') RETURNING id",
            (workorder_id, execution_id, source_file_id),
        ).fetchone()[0]
    observed = query_repository.get_workorder(
        "WO-F04-CRASH-WINDOW", execution_id=execution_id
    )

    assert state == "applying_rules"
    assert observed is None
    assert query_repository.get_lot(
        "LOT-F04-CRASH-WINDOW", execution_id=execution_id
    ) is None
    assert query_repository.get_serial(
        "SER-F04-CRASH-WINDOW", execution_id=execution_id
    ) is None
    results, total = query_repository.search_operational(
        entity_type="workorder",
        query="WO-F04-CRASH-WINDOW",
        page=1,
        page_size=25,
        sort="newest",
    )
    assert results == []
    assert total == 0
    pending_rows, pending_total = query_repository.list_pending(
        status_filter=None,
        category=None,
        workorder_number=None,
        execution_id=execution_id,
        page=1,
        page_size=25,
        sort="newest",
    )
    assert pending_rows == []
    assert pending_total == 0
    assert query_repository.get_pending(pending_id) is None
    assert query_repository.indicators()["workorders"]["total"] == baseline_workorders
    assert query_repository.get_execution(execution_id)["counts"]["workorders"] == 1

    PostgresImportRepository(os.environ["DATABASE_URL"]).transition_execution(
        execution_id, "completed", "f04_test_publication"
    )
    assert query_repository.get_workorder(
        "WO-F04-CRASH-WINDOW", execution_id=execution_id
    ) is not None
    assert query_repository.get_pending(pending_id) is not None
    assert query_repository.indicators()["workorders"]["total"] == (
        baseline_workorders + 1
    )


def test_database_rejects_cross_execution_workorder_relationship() -> None:
    first_file = _seed_execution("exec-integrity-a", ["N-FP"])[0]
    second_file = _seed_execution("exec-integrity-b", ["N-FP"])[0]
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        workorder_id = connection.execute(
            """
            INSERT INTO synergia.workorders
                (workorder_number, execution_id, source_file_id,
                 processing_status)
            VALUES ('WO-INTEGRITY-A', 'exec-integrity-a', %s, 'consolidated')
            RETURNING id
            """,
            (first_file,),
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            connection.execute(
                """
                INSERT INTO synergia.lots
                    (lot_number, workorder_id, execution_id, source_file_id)
                VALUES ('LOT-CROSS', %s, 'exec-integrity-b', %s)
                """,
                (workorder_id, second_file),
            )


def test_critical_query_indexes_exist() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'synergia'"
            ).fetchall()
        }
    assert {
        "idx_classifications_execution_rule",
        "idx_classifications_workorder",
        "idx_rule_evaluations_execution_rule",
        "idx_provenance_workorder_field",
        "idx_pending_items_priority",
    } <= indexes
