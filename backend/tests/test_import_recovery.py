from __future__ import annotations

import hashlib
import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.import_recovery import ImportRecoveryError, recover_import
from app.imports import PostgresImportRepository
from app.persistence import PostgresProcessingRepository
from app.pipeline import read_source, run_pipeline_batch
from app.queries import PostgresQueryRepository

pytestmark = pytest.mark.integration


class _CaptureRepository:
    def transition_execution(self, execution_id, target, reason):
        pass

    def commit_pipeline(self, execution_id, result):
        pass


def _crash_during_commit(database_url: str, execution_id: str, result: dict):
    original = PostgresProcessingRepository._persist_workorder

    def exit_after_writes(self, *args, **kwargs):
        original(self, *args, **kwargs)
        os._exit(74)

    PostgresProcessingRepository._persist_workorder = exit_after_writes
    PostgresImportRepository(database_url).commit_pipeline(execution_id, result)


def _crash_after_commit(database_url: str, execution_id: str, result: dict):
    PostgresImportRepository(database_url).commit_pipeline(execution_id, result)
    os._exit(75)


def _crash_during_validation(database_url: str, execution_id: str, result: dict):
    import app.pipeline as pipeline

    def exit_during_validation(*args, **kwargs):
        os._exit(76)

    pipeline.validate_tables = exit_during_validation
    path = Path(result["test_accepted_path"])
    tables, issues = read_source(path, ".csv", "N-FP")
    run_pipeline_batch(
        execution_id=execution_id,
        inputs=[
            {
                "file_name": "plan.csv",
                "source": "N-FP",
                "source_file_id": result["test_source_file_id"],
                "tables": tables,
                "read_issues": issues,
            }
        ],
        repository=PostgresImportRepository(database_url),
        classified_at=result["test_classified_at"],
        resume=True,
    )


def _seed_accepted_import(
    database_url: str,
    root: Path,
    suffix: str,
    *,
    target_state: str = "applying_rules",
    claim: bool = True,
):
    execution_id = f"exec-recovery-{suffix}"
    organization_id = uuid4()
    code = f"rec-{suffix}"
    number = f"WO-REC-{suffix.upper()}"
    accepted = root / "accepted" / execution_id
    accepted.mkdir(parents=True)
    path = accepted / "plan.csv"
    path.write_text(
        "workorder_number,organization_code,lot_number,serial_number,"
        "planned_quantity\n"
        f"{number},{code},LOT-{suffix},SER-{suffix},1\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO synergia.iam_organizations "
            "(id, organization_code, display_name) VALUES (%s, %s, 'Recovery Test')",
            (organization_id, code),
        )
        connection.execute(
            "INSERT INTO synergia.executions "
            "(id, status, source, organization_id, actor_type, actor_identifier) "
            "VALUES (%s, 'pending', 'N-FP', %s, 'technical', 'recovery-test')",
            (execution_id, organization_id),
        )
        source_file_id = connection.execute(
            "INSERT INTO synergia.source_files "
            "(execution_id, source, file_name, extension, content_hash, "
            "size_bytes, storage_key) "
            "VALUES (%s, 'N-FP', 'plan.csv', 'csv', %s, %s, %s) RETURNING id",
            (execution_id, digest, path.stat().st_size, str(path.relative_to(root))),
        ).fetchone()[0]
    repository = PostgresImportRepository(database_url)
    if claim:
        assert repository.claim_processing(execution_id, [digest]) is None
    for state in ("validating", "normalizing", "consolidating", "applying_rules"):
        if state == target_state or target_state != "pending":
            repository.transition_execution(execution_id, state, "recovery_test_setup")
        if state == target_state or target_state == "pending":
            break
    tables, issues = read_source(path, ".csv", "N-FP")
    result = run_pipeline_batch(
        execution_id=execution_id,
        inputs=[
            {
                "file_name": "plan.csv",
                "source": "N-FP",
                "source_file_id": source_file_id,
                "tables": tables,
                "read_issues": issues,
            }
        ],
        repository=_CaptureRepository(),
        classified_at=repository.get(execution_id)["started_at"].isoformat(),
        known_organizations={code},
        resume=True,
    )
    assert result["status"] == "completed"
    result["test_accepted_path"] = str(path)
    result["test_source_file_id"] = source_file_id
    result["test_classified_at"] = repository.get(execution_id)[
        "started_at"
    ].isoformat()
    return execution_id, organization_id, number, result, path


def _cleanup(database_url: str, execution_id: str, organization_id):
    with psycopg.connect(database_url) as connection:
        for table in (
            "pending_items",
            "holds",
            "oqc_decisions",
            "classifications",
            "rule_evaluations",
            "consolidated_field_provenance",
            "audit_events",
            "pipeline_issues",
            "pipeline_summaries",
            "normalized_records",
            "imported_records",
            "serials",
            "lots",
            "workorders",
            "organizations",
            "execution_idempotency",
            "source_files",
            "execution_state_transitions",
        ):
            connection.execute(
                f"DELETE FROM synergia.{table} WHERE execution_id = %s",
                (execution_id,),
            )
        connection.execute(
            "DELETE FROM synergia.executions WHERE id = %s", (execution_id,)
        )
        connection.execute(
            "UPDATE synergia.iam_organizations "
            "SET is_active = false, deactivated_at = now() WHERE id = %s",
            (organization_id,),
        )


def test_actual_process_crash_before_commit_rolls_back_and_resumes(tmp_path):
    database_url = os.environ["DATABASE_URL"]
    execution_id, organization_id, number, result, _ = _seed_accepted_import(
        database_url, tmp_path, uuid4().hex[:10]
    )
    try:
        process = multiprocessing.get_context("spawn").Process(
            target=_crash_during_commit,
            args=(database_url, execution_id, result),
        )
        process.start()
        process.join(timeout=30)
        assert process.exitcode == 74
        with psycopg.connect(database_url) as connection:
            for table in (
                "imported_records",
                "normalized_records",
                "pipeline_summaries",
                "workorders",
                "lots",
                "serials",
            ):
                assert (
                    connection.execute(
                        f"SELECT count(*) FROM synergia.{table} "
                        "WHERE execution_id = %s",
                        (execution_id,),
                    ).fetchone()[0]
                    == 0
                ), table
            assert (
                connection.execute(
                    "SELECT status FROM synergia.executions WHERE id = %s",
                    (execution_id,),
                ).fetchone()[0]
                == "applying_rules"
            )
        query = PostgresQueryRepository(database_url)
        assert query.get_workorder(number) is None
        assert recover_import(database_url, tmp_path, execution_id)["action"] == (
            "resume_pipeline"
        )
        resumed = recover_import(database_url, tmp_path, execution_id, apply=True)
        assert resumed["status_after"] == "completed"
        assert query.get_workorder(
            number, organization_ids=frozenset({organization_id})
        )
        assert (
            query.get_workorder(number, organization_ids=frozenset({uuid4()})) is None
        )
        with psycopg.connect(database_url) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM synergia.workorders WHERE execution_id = %s",
                    (execution_id,),
                ).fetchone()[0]
                == 1
            )
            for event_type in ("pipeline_finished", "processing_unit_persisted"):
                assert (
                    connection.execute(
                        "SELECT count(*) FROM synergia.audit_events "
                        "WHERE execution_id = %s AND event_type = %s",
                        (execution_id, event_type),
                    ).fetchone()[0]
                    == 1
                )
        assert (
            recover_import(database_url, tmp_path, execution_id, apply=True)["action"]
            == "already_terminal"
        )
    finally:
        _cleanup(database_url, execution_id, organization_id)


def test_actual_process_crash_after_commit_is_idempotent(tmp_path):
    database_url = os.environ["DATABASE_URL"]
    execution_id, organization_id, number, result, _ = _seed_accepted_import(
        database_url, tmp_path, uuid4().hex[:10]
    )
    try:
        process = multiprocessing.get_context("spawn").Process(
            target=_crash_after_commit, args=(database_url, execution_id, result)
        )
        process.start()
        process.join(timeout=30)
        assert process.exitcode == 75
        assert (
            recover_import(database_url, tmp_path, execution_id, apply=True)["action"]
            == "already_terminal"
        )
        assert PostgresQueryRepository(database_url).get_workorder(number)
    finally:
        _cleanup(database_url, execution_id, organization_id)


def test_recovery_rejects_tampered_accepted_file(tmp_path):
    database_url = os.environ["DATABASE_URL"]
    execution_id, organization_id, _, _, path = _seed_accepted_import(
        database_url, tmp_path, uuid4().hex[:10]
    )
    try:
        path.write_text("tampered\n", encoding="utf-8")
        with pytest.raises(ImportRecoveryError, match="Hash ou tamanho"):
            recover_import(database_url, tmp_path, execution_id, apply=True)
        assert PostgresImportRepository(database_url).get(execution_id)["status"] == (
            "applying_rules"
        )
    finally:
        _cleanup(database_url, execution_id, organization_id)


def test_actual_process_crash_during_validation_resumes_from_sources(tmp_path):
    database_url = os.environ["DATABASE_URL"]
    execution_id, organization_id, number, result, _ = _seed_accepted_import(
        database_url, tmp_path, uuid4().hex[:10], target_state="validating"
    )
    try:
        process = multiprocessing.get_context("spawn").Process(
            target=_crash_during_validation,
            args=(database_url, execution_id, result),
        )
        process.start()
        process.join(timeout=30)
        assert process.exitcode == 76
        assert PostgresImportRepository(database_url).get(execution_id)["status"] == (
            "validating"
        )
        assert PostgresQueryRepository(database_url).get_workorder(number) is None
        resumed = recover_import(database_url, tmp_path, execution_id, apply=True)
        assert resumed["status_after"] == "completed"
        assert PostgresQueryRepository(database_url).get_workorder(number)
    finally:
        _cleanup(database_url, execution_id, organization_id)


def test_incomplete_reservation_is_failed_and_new_attempt_can_claim(tmp_path):
    database_url = os.environ["DATABASE_URL"]
    execution_id, organization_id, _, _, path = _seed_accepted_import(
        database_url,
        tmp_path,
        uuid4().hex[:10],
        target_state="pending",
        claim=False,
    )
    new_execution_id = f"{execution_id}-retry"
    try:
        preview = recover_import(database_url, tmp_path, execution_id)
        assert preview["action"] == "fail_incomplete_reservation"
        result = recover_import(database_url, tmp_path, execution_id, apply=True)
        assert result["applied"] is True
        assert PostgresImportRepository(database_url).get(execution_id)["status"] == (
            "failed"
        )
        with psycopg.connect(database_url) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM synergia.execution_idempotency "
                    "WHERE execution_id = %s",
                    (execution_id,),
                ).fetchone()[0]
                == 0
            )
            connection.execute(
                "INSERT INTO synergia.executions "
                "(id, status, source, organization_id) "
                "VALUES (%s, 'pending', 'N-FP', %s)",
                (new_execution_id, organization_id),
            )
            connection.execute(
                "INSERT INTO synergia.source_files "
                "(execution_id, source, file_name, content_hash) "
                "VALUES (%s, 'N-FP', 'retry.csv', %s)",
                (new_execution_id, hashlib.sha256(path.read_bytes()).hexdigest()),
            )
        assert (
            PostgresImportRepository(database_url).claim_processing(
                new_execution_id, [hashlib.sha256(path.read_bytes()).hexdigest()]
            )
            is None
        )
    finally:
        _cleanup(database_url, new_execution_id, organization_id)
        _cleanup(database_url, execution_id, organization_id)


def test_concurrent_recovery_calls_confirm_pipeline_only_once(tmp_path):
    database_url = os.environ["DATABASE_URL"]
    execution_id, organization_id, number, _, _ = _seed_accepted_import(
        database_url, tmp_path, uuid4().hex[:10]
    )
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    recover_import,
                    database_url,
                    tmp_path,
                    execution_id,
                    apply=True,
                )
                for _ in range(2)
            ]
            results = [future.result(timeout=30) for future in futures]
        assert {result["action"] for result in results} == {
            "resume_pipeline",
            "already_terminal",
        }
        assert PostgresQueryRepository(database_url).get_workorder(number)
        with psycopg.connect(database_url) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM synergia.workorders WHERE execution_id = %s",
                    (execution_id,),
                ).fetchone()[0]
                == 1
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM synergia.audit_events "
                    "WHERE execution_id = %s AND event_type = 'pipeline_finished'",
                    (execution_id,),
                ).fetchone()[0]
                == 1
            )
    finally:
        _cleanup(database_url, execution_id, organization_id)
