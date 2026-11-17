"""Read-only import result projection, independent of filesystem artifacts."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from app.execution import TERMINAL_STATES, ExecutionState
from app.execution_summary import start_execution_snapshot
from app.ingestion_budget import LIMIT_GUIDANCE


class ImportSummaryStatus(StrEnum):
    READY = "ready"
    PROCESSING = "processing"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class ImportSummaryReason(StrEnum):
    PERSISTED = "summary_persisted"
    PROCESSING = "execution_processing"
    DUPLICATE = "duplicate"
    REJECTED = "security_rejected"
    PREPARATION = "preparation_error"
    UNAVAILABLE = "summary_unavailable"
    UNKNOWN_STATE = "unknown_execution_state"


class ImportResultCounts(BaseModel):
    rows_read: int = Field(ge=0)
    valid_records: int = Field(ge=0)
    rejected_records: int = Field(ge=0)
    normalized_records: int = Field(ge=0)
    errors: int = Field(ge=0)
    warnings: int = Field(ge=0)


class ImportResultSummary(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "execution_id": "synthetic-import-194",
                    "execution_status": "completed_with_errors",
                    "summary_status": "ready",
                    "summary": {
                        "rows_read": 3,
                        "valid_records": 2,
                        "rejected_records": 1,
                        "normalized_records": 2,
                        "errors": 1,
                        "warnings": 0,
                    },
                    "issues_total": 1,
                    "reason_code": "summary_persisted",
                    "generated_at": "2026-11-17T12:00:00Z",
                }
            ]
        }
    )

    execution_id: str
    execution_status: str
    summary_status: ImportSummaryStatus
    summary: ImportResultCounts | None = None
    issues_total: int = Field(ge=0)
    generated_at: datetime
    reason_code: ImportSummaryReason
    inspection_reason_code: str | None = None
    duplicate_of_execution_id: str | None = Field(
        default=None, description="Referência somente se autorizada por import.read."
    )


# Only public machine codes, never free-form inspection text or reason_details.
_INSPECTION_CODES = frozenset(
    {
        "unsupported_extension",
        "empty_file",
        "file_too_large",
        "declared_mime_mismatch",
        "content_signature_mismatch",
        "binary_content_mismatch",
        "content_type_mismatch",
        "disguised_active_content",
        "invalid_text_encoding",
        "corrupted_file",
        "macro_or_active_content",
        "embedded_object",
        "external_link",
        "dangerous_formula",
        "path_traversal",
        "archive_too_many_entries",
        "archive_uncompressed_limit",
        "archive_compression_ratio",
        "archive_path_traversal",
        "encrypted_archive",
        *LIMIT_GUIDANCE,
    }
)
_ACTIVE_STATES = frozenset(ExecutionState) - TERMINAL_STATES


def project_import_result(row: dict) -> ImportResultSummary:
    """Project a scoped snapshot. A missing summary is never a zero summary."""
    counts = None
    inspection_reason = None
    status = row["status"]
    if row["summary_execution_id"] is not None:
        counts = ImportResultCounts(
            rows_read=row["rows_read"],
            valid_records=row["valid_records"],
            rejected_records=row["rejected_records"],
            normalized_records=row["normalized_records"],
            errors=row["error_count"],
            warnings=row["warning_count"],
        )
        availability, reason = ImportSummaryStatus.READY, ImportSummaryReason.PERSISTED
    elif status == ExecutionState.DUPLICATE:
        availability = ImportSummaryStatus.NOT_APPLICABLE
        reason = ImportSummaryReason.DUPLICATE
    elif row["rejected_inspection_id"] is not None:
        availability = ImportSummaryStatus.NOT_APPLICABLE
        reason = ImportSummaryReason.REJECTED
        code = row["inspection_reason_code"]
        inspection_reason = code if code in _INSPECTION_CODES else "security_rejected"
    elif status in _ACTIVE_STATES:
        availability = ImportSummaryStatus.PROCESSING
        reason = ImportSummaryReason.PROCESSING
    else:
        availability = ImportSummaryStatus.UNAVAILABLE
        reason = (
            ImportSummaryReason.UNKNOWN_STATE
            if status not in TERMINAL_STATES
            else ImportSummaryReason.PREPARATION
            if row["failure_reason"] == "preparation_error"
            else ImportSummaryReason.UNAVAILABLE
        )
    return ImportResultSummary(
        execution_id=row["execution_id"],
        execution_status=status,
        summary_status=availability,
        summary=counts,
        issues_total=row["issues_total"],
        generated_at=row["generated_at"].astimezone(UTC),
        reason_code=reason,
        inspection_reason_code=inspection_reason,
        duplicate_of_execution_id=(
            row["authorized_duplicate_id"]
            if reason == ImportSummaryReason.DUPLICATE
            else None
        ),
    )


def read_import_result_summary(
    connection: psycopg.Connection,
    execution_id: str,
    *,
    organization_scopes: frozenset[UUID] | None,
) -> ImportResultSummary | None:
    """One snapshot for state, persisted counts, issues and authorized reference."""
    start_execution_snapshot(connection)
    scopes = (
        None if organization_scopes is None else sorted(organization_scopes, key=str)
    )
    with connection.cursor(row_factory=dict_row) as cursor:
        row = cursor.execute(
            """SELECT e.id AS execution_id,e.status,e.failure_reason,
                      ps.execution_id AS summary_execution_id,
                      ps.rows_read,ps.valid_records,ps.rejected_records,
                      ps.normalized_records,ps.error_count,ps.warning_count,
                      (SELECT count(*) FROM synergia.pipeline_issues pi
                       WHERE pi.execution_id=e.id) AS issues_total,
                      rejection.id AS rejected_inspection_id,
                      rejection.reason_code AS inspection_reason_code,
                      previous.id AS authorized_duplicate_id,
                      transaction_timestamp() AS generated_at
               FROM synergia.executions e
               CROSS JOIN (SELECT %s::uuid[] AS organization_ids) allowed
               LEFT JOIN synergia.pipeline_summaries ps ON ps.execution_id=e.id
               LEFT JOIN LATERAL (
                   SELECT fi.id,fi.reason_code FROM synergia.file_inspections fi
                   WHERE fi.execution_id=e.id AND fi.decision='rejected'
                   ORDER BY fi.analyzed_at,fi.id LIMIT 1
               ) rejection ON TRUE
               LEFT JOIN synergia.executions previous
                 ON previous.id=e.duplicate_of_execution_id
                AND previous.organization_id IS NOT NULL
                AND (allowed.organization_ids IS NULL
                     OR previous.organization_id=ANY(allowed.organization_ids))
               WHERE e.id=%s AND e.organization_id IS NOT NULL
                 AND (allowed.organization_ids IS NULL
                      OR e.organization_id=ANY(allowed.organization_ids))""",
            (scopes, execution_id),
        ).fetchone()
    return project_import_result(row) if row is not None else None
