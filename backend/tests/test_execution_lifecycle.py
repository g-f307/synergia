from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from app.execution import InvalidExecutionTransition
from app.imports import PostgresImportRepository
from app.pipeline import run_pipeline
from app.queries import PostgresQueryRepository, ReprocessingConflict

pytestmark = pytest.mark.integration
EXECUTION_PREFIX = "exec-lifecycle-"


@pytest.fixture(autouse=True)
def cleanup_lifecycle_data():
    yield
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for table, column in (
            ("pending_items", "execution_id"),
            ("holds", "execution_id"),
            ("oqc_decisions", "execution_id"),
            ("classifications", "execution_id"),
            ("rule_evaluations", "execution_id"),
            ("consolidated_field_provenance", "execution_id"),
            ("audit_events", "execution_id"),
            ("pipeline_issues", "execution_id"),
            ("pipeline_summaries", "execution_id"),
            ("normalized_records", "execution_id"),
            ("imported_records", "execution_id"),
            ("serials", "execution_id"),
            ("lots", "execution_id"),
            ("workorders", "execution_id"),
            ("organizations", "execution_id"),
            ("source_files", "execution_id"),
            ("execution_idempotency", "execution_id"),
            ("execution_state_transitions", "execution_id"),
        ):
            connection.execute(
                f"DELETE FROM synergia.{table} WHERE {column} LIKE %s",
                (f"{EXECUTION_PREFIX}%",),
            )
        connection.execute(
            "DELETE FROM synergia.executions WHERE id LIKE %s",
            (f"{EXECUTION_PREFIX}%",),
        )


def _seed_completed(execution_id: str) -> int:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            """
            INSERT INTO synergia.executions (
                id, status, source, actor_type, actor_identifier,
                state_changed_by_type, state_changed_by, state_change_reason
            ) VALUES (%s, 'completed', 'N-FP', 'technical', 'integration-test',
                      'technical', 'integration-test', 'seed_completed')
            """,
            (execution_id,),
        )
        source_file_id = connection.execute(
            """
            INSERT INTO synergia.source_files (
                execution_id, source, file_name, content_hash
            ) VALUES (%s, 'N-FP', 'original.csv', %s) RETURNING id
            """,
            (execution_id, (execution_id.encode().hex() + "0" * 64)[:64]),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO synergia.workorders (
                workorder_number, execution_id, source_file_id,
                processing_status, planned_quantity
            ) VALUES (%s, %s, %s, 'consolidated', 10)
            """,
            (f"WO-{execution_id}", execution_id, source_file_id),
        )
    return source_file_id


def test_records_complete_state_flow_with_actor_reason_and_versions() -> None:
    execution_id = f"{EXECUTION_PREFIX}flow"
    repository = PostgresImportRepository(os.environ["DATABASE_URL"])
    repository.start(execution_id, "N-FP", "technical", "state-test")

    for target, reason in (
        ("validating", "pipeline_started"),
        ("normalizing", "validation_completed"),
        ("consolidating", "normalization_completed"),
        ("applying_rules", "consolidation_completed"),
        ("completed", "pipeline_completed"),
    ):
        repository.transition_execution(execution_id, target, reason)

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        transitions = connection.execute(
            """
            SELECT from_state, to_state, actor_identifier, reason, state_version
            FROM synergia.execution_state_transitions
            WHERE execution_id = %s ORDER BY id
            """,
            (execution_id,),
        ).fetchall()
        execution = connection.execute(
            """
            SELECT status, pipeline_version, rule_catalog_version, state_version
            FROM synergia.executions WHERE id = %s
            """,
            (execution_id,),
        ).fetchone()

    assert [item[1] for item in transitions] == [
        "pending",
        "validating",
        "normalizing",
        "consolidating",
        "applying_rules",
        "completed",
    ]
    assert all(item[2] for item in transitions)
    assert all(item[3] for item in transitions)
    assert execution == ("completed", "1.0.0", "1.0.0", 5)


def test_real_pipeline_advances_and_persists_complete_execution() -> None:
    execution_id = f"{EXECUTION_PREFIX}pipeline"
    repository = PostgresImportRepository(os.environ["DATABASE_URL"])
    repository.start(execution_id, "N-FP", "technical", "pipeline-test")
    source_file_id, duplicate = repository.claim_file(
        execution_id,
        source="N-FP",
        file_name="pipeline.csv",
        extension="csv",
        size_bytes=20,
        digest="f" * 64,
        media_type="text/csv",
        storage_key=f"n_fp/{execution_id}/original.csv",
    )
    assert duplicate is None
    assert repository.claim_processing(execution_id, ["f" * 64]) is None

    result = run_pipeline(
        execution_id=execution_id,
        file_name="pipeline.csv",
        source="N-FP",
        repository=repository,
        tables=[("CSV", ["workorder", "planned_quantity"], [["WO-LIFE", 10]])],
        read_issues=[],
        source_file_id=source_file_id,
        classified_at="2026-08-30T12:00:00+00:00",
    )

    assert result["status"] == "completed"
    assert repository.get(execution_id)["status"] == "completed"
    assert (
        PostgresQueryRepository(os.environ["DATABASE_URL"]).get_consolidated("WO-LIFE")[
            "workorder"
        ]["planned_quantity"]
        == 10
    )


def test_domain_and_database_reject_invalid_transition() -> None:
    execution_id = f"{EXECUTION_PREFIX}invalid"
    repository = PostgresImportRepository(os.environ["DATABASE_URL"])
    repository.start(execution_id, "N-FP", "technical", "state-test")

    with pytest.raises(InvalidExecutionTransition):
        repository.transition_execution(execution_id, "completed", "skip_stages")

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                UPDATE synergia.executions
                SET status = 'completed', state_changed_by = 'sql-test',
                    state_change_reason = 'skip_stages'
                WHERE id = %s
                """,
                (execution_id,),
            )


def test_identical_import_claims_are_idempotent_sequentially_and_concurrently() -> None:
    repository = PostgresImportRepository(os.environ["DATABASE_URL"])
    file_hash = "a" * 64
    first = f"{EXECUTION_PREFIX}import-first"
    second = f"{EXECUTION_PREFIX}import-second"
    repository.start(first, "N-FP", "technical", "idempotency-test")
    repository.start(second, "N-FP", "technical", "idempotency-test")
    for execution_id in (first, second):
        source_file_id, duplicate = repository.claim_file(
            execution_id,
            source="N-FP",
            file_name="same.csv",
            extension="csv",
            size_bytes=10,
            digest=file_hash,
            media_type="text/csv",
            storage_key=f"n_fp/{execution_id}/original.csv",
        )
        assert source_file_id is not None
        assert duplicate is None

    assert repository.claim_processing(first, [file_hash]) is None
    assert repository.claim_processing(second, [file_hash]) == first

    concurrent_ids = [
        f"{EXECUTION_PREFIX}concurrent-a",
        f"{EXECUTION_PREFIX}concurrent-b",
    ]
    for execution_id in concurrent_ids:
        repository.start(
            execution_id,
            "N-FP",
            "technical",
            "idempotency-test",
            rule_catalog_version="2.0.0",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda item: repository.claim_processing(item, [file_hash]),
                concurrent_ids,
            )
        )

    assert results.count(None) == 1
    assert sum(result in concurrent_ids for result in results if result) == 1


def test_concurrent_state_confirmation_accepts_only_one_transition() -> None:
    execution_id = f"{EXECUTION_PREFIX}concurrent-state"
    repository = PostgresImportRepository(os.environ["DATABASE_URL"])
    repository.start(execution_id, "N-FP", "technical", "concurrency-test")

    def start_validation(_index: int) -> str:
        try:
            repository.transition_execution(
                execution_id, "validating", "concurrent_start"
            )
        except InvalidExecutionTransition:
            return "rejected"
        return "confirmed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(start_validation, (1, 2)))

    assert sorted(results) == ["confirmed", "rejected"]


def test_reprocessing_is_idempotent_versioned_and_preserves_original() -> None:
    original_id = f"{EXECUTION_PREFIX}original"
    _seed_completed(original_id)
    repository = PostgresQueryRepository(os.environ["DATABASE_URL"])

    first = repository.request_reprocessing(
        original_id,
        f"{EXECUTION_PREFIX}reprocess-a",
        "integration-test",
        "request-1",
        "1.0.0",
        "1.0.0",
    )
    replay = repository.request_reprocessing(
        original_id,
        f"{EXECUTION_PREFIX}reprocess-b",
        "integration-test",
        "request-1",
        "1.0.0",
        "1.0.0",
    )
    new_rules = repository.request_reprocessing(
        original_id,
        f"{EXECUTION_PREFIX}reprocess-rules-v2",
        "integration-test",
        "request-1",
        "1.0.0",
        "2.0.0",
    )

    assert replay["execution_id"] == first["execution_id"]
    assert replay["idempotent_replay"] is True
    assert new_rules["execution_id"] != first["execution_id"]
    assert new_rules["attempt"] == 3
    assert repository.get_execution(original_id)["status"] == "completed"
    assert repository.get_consolidated(f"WO-{original_id}") is not None


def test_concurrent_reprocessing_returns_one_execution() -> None:
    original_id = f"{EXECUTION_PREFIX}concurrent-original"
    _seed_completed(original_id)
    repository = PostgresQueryRepository(os.environ["DATABASE_URL"])

    def request(index: int):
        return repository.request_reprocessing(
            original_id,
            f"{EXECUTION_PREFIX}concurrent-reprocess-{index}",
            "integration-test",
            "same-request",
            "1.0.0",
            "1.0.0",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(request, (1, 2)))

    assert len({result["execution_id"] for result in results}) == 1
    assert {result["idempotent_replay"] for result in results} == {False, True}


def test_active_execution_cannot_be_reprocessed() -> None:
    execution_id = f"{EXECUTION_PREFIX}active"
    repository = PostgresImportRepository(os.environ["DATABASE_URL"])
    repository.start(execution_id, "N-FP", "technical", "active-test")

    with pytest.raises(ReprocessingConflict):
        PostgresQueryRepository(os.environ["DATABASE_URL"]).request_reprocessing(
            execution_id,
            f"{EXECUTION_PREFIX}should-not-exist",
            "integration-test",
            "request-active",
            "1.0.0",
            "1.0.0",
        )


def test_reprocessing_failure_rolls_back_new_execution(monkeypatch) -> None:
    original_id = f"{EXECUTION_PREFIX}rollback-original"
    _seed_completed(original_id)
    repository = PostgresQueryRepository(os.environ["DATABASE_URL"])
    new_execution_id = f"{EXECUTION_PREFIX}rollback-new"

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(repository, "_record_reprocessing_event", fail_audit)
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        repository.request_reprocessing(
            original_id,
            new_execution_id,
            "integration-test",
            "rollback-request",
            "1.0.0",
            "1.0.0",
        )

    assert repository.get_execution(new_execution_id) is None
    assert repository.get_execution(original_id)["status"] == "completed"
    assert repository.get_consolidated(f"WO-{original_id}") is not None
