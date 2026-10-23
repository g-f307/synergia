from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from app.imports import PostgresImportRepository
from app.upload_security import InspectionDecision, InspectionResult

pytestmark = [pytest.mark.integration, pytest.mark.security]
EXECUTION_ID = "upload-security-persistence"
RETRY_EXECUTION_ID = "upload-security-persistence-retry"


@pytest.fixture(autouse=True)
def cleanup_upload_security_data():
    yield
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for execution_id in (EXECUTION_ID, RETRY_EXECUTION_ID):
            for table in (
                "audit_events",
                "source_files",
                "file_inspections",
                "execution_idempotency",
                "execution_state_transitions",
            ):
                connection.execute(
                    f"DELETE FROM synergia.{table} WHERE execution_id = %s",
                    (execution_id,),
                )
            connection.execute(
                "DELETE FROM synergia.executions WHERE id = %s", (execution_id,)
            )


def _result(
    decision: InspectionDecision, internal_character: str = "a"
) -> InspectionResult:
    analyzed_at = datetime.now(UTC)
    accepted = decision is InspectionDecision.ACCEPTED
    return InspectionResult(
        original_name="customer-report.csv",
        internal_name=f"{internal_character * 48}.csv",
        extension=".csv",
        declared_media_type="text/csv",
        detected_media_type="text/csv",
        size_bytes=12,
        sha256="b" * 64,
        decision=decision,
        reason_code="accepted" if accepted else "dangerous_formula",
        analyzed_at=analyzed_at,
        retained_until=None if accepted else analyzed_at + timedelta(hours=24),
        discarded_at=None,
        quarantine_path=Path("ignored-by-persistence"),
    )


def test_persists_inspection_source_link_and_safe_audit_payload() -> None:
    repository = PostgresImportRepository(os.environ["DATABASE_URL"])
    repository.start(EXECUTION_ID, "N-FP", "technical", "integration-test")
    inspection = _result(InspectionDecision.ACCEPTED)

    inspection_id = repository.record_inspection(EXECUTION_ID, "N-FP", inspection)
    rejected_id = repository.record_inspection(
        EXECUTION_ID,
        "N-FP",
        _result(InspectionDecision.REJECTED, "c"),
    )
    source_file_id, duplicate = repository.claim_file(
        EXECUTION_ID,
        file_name=inspection.original_name,
        extension="csv",
        size_bytes=inspection.size_bytes,
        digest=inspection.sha256,
        media_type=inspection.declared_media_type,
        detected_media_type=inspection.detected_media_type or "",
        storage_key=f"accepted/n_fp/{EXECUTION_ID}/{inspection.internal_name}",
        inspection_id=inspection_id,
        source="N-FP",
    )

    assert source_file_id is not None
    assert duplicate is None
    records = repository.list_inspections(EXECUTION_ID)
    assert [record["decision"] for record in records] == ["accepted", "rejected"]
    assert records[0]["sha256"] == "b" * 64
    assert "internal_name" not in records[0]

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        source = connection.execute(
            """
            SELECT inspection_id, detected_media_type
            FROM synergia.source_files WHERE id = %s
            """,
            (source_file_id,),
        ).fetchone()
        events = connection.execute(
            """
                SELECT event_type, payload
                FROM synergia.audit_events
                WHERE execution_id = %s AND entity_type = 'file_inspection'
                ORDER BY id
                """,
            (EXECUTION_ID,),
        ).fetchall()

    assert source == (inspection_id, "text/csv")
    assert rejected_id != inspection_id
    assert [event[0] for event in events] == ["file_accepted", "file_rejected"]
    assert events[0][1]["reason_code"] == "accepted"
    assert events[1][1]["reason_code"] == "dangerous_formula"
    assert all("path" not in event[1] for event in events)
    assert all("internal_name" not in event[1] for event in events)

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            """
            UPDATE synergia.file_inspections
            SET retained_until = now() - interval '1 minute'
            WHERE id = %s
            """,
            (rejected_id,),
        )
    assert repository.list_expired_inspection_stems() == ["c" * 48]
    repository.mark_inspections_discarded(["c" * 48])
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        discarded_at = connection.execute(
            "SELECT discarded_at FROM synergia.file_inspections WHERE id = %s",
            (rejected_id,),
        ).fetchone()[0]
    assert discarded_at is not None


def test_aborted_claim_releases_hash_and_reservation_for_a_new_attempt() -> None:
    repository = PostgresImportRepository(os.environ["DATABASE_URL"])
    digest = "d" * 64

    def attempt(execution_id: str, internal_character: str):
        repository.start(execution_id, "N-FP", "technical", "integration-test")
        inspection = _result(InspectionDecision.ACCEPTED, internal_character)
        inspection_id = repository.record_inspection(execution_id, "N-FP", inspection)
        claimed = repository.claim_file(
            execution_id,
            file_name=inspection.original_name,
            extension="csv",
            size_bytes=inspection.size_bytes,
            digest=digest,
            media_type=inspection.declared_media_type,
            detected_media_type=inspection.detected_media_type or "",
            storage_key=f"accepted/n_fp/{execution_id}/{inspection.internal_name}",
            inspection_id=inspection_id,
            source="N-FP",
        )
        return claimed, repository.claim_processing(execution_id, [digest])

    (first_file, first_duplicate), first_processing = attempt(EXECUTION_ID, "a")
    assert first_file is not None and first_duplicate is None
    assert first_processing is None

    repository.abort_claim(EXECUTION_ID, "ingestion_issue_limit")

    (second_file, second_duplicate), second_processing = attempt(
        RETRY_EXECUTION_ID, "e"
    )
    assert second_file is not None
    assert second_duplicate is None
    assert second_processing is None
    assert repository.get(EXECUTION_ID)["status"] == "failed"
    assert repository.get(EXECUTION_ID)["failure_reason"] == "ingestion_issue_limit"
