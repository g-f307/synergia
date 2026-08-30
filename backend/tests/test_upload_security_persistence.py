from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from app.imports import PostgresImportRepository
from app.upload_security import InspectionDecision, InspectionResult

pytestmark = pytest.mark.integration
EXECUTION_ID = "upload-security-persistence"


@pytest.fixture(autouse=True)
def cleanup_upload_security_data():
    yield
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for table in (
            "audit_events",
            "source_files",
            "file_inspections",
            "execution_idempotency",
            "execution_state_transitions",
        ):
            connection.execute(
                f"DELETE FROM synergia.{table} WHERE execution_id = %s",
                (EXECUTION_ID,),
            )
        connection.execute(
            "DELETE FROM synergia.executions WHERE id = %s", (EXECUTION_ID,)
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
