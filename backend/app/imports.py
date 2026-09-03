from __future__ import annotations

import json
import logging
import os
from collections.abc import Generator
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Protocol
from uuid import UUID, uuid4

import psycopg
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from app.authorization import (
    ActorContext,
    AuthorizationRepo,
    require_execution_permission,
    require_permission,
)
from app.business_rules import RULE_CATALOG
from app.errors import ErrorResponse
from app.execution import (
    PIPELINE_VERSION,
    ExecutionState,
    import_fingerprint,
    validate_transition,
)
from app.persistence import PostgresProcessingRepository
from app.pipeline import read_source, run_pipeline_batch
from app.upload_security import (
    InspectionResult,
    policy_for,
    purge_quarantined,
    receive_and_inspect,
    release_to_accepted,
)

logger = logging.getLogger("synergia.imports")
router = APIRouter(prefix="/imports", tags=["imports"])


class ImportSource(str, Enum):
    n_fp = "N-FP"
    owm = "OWM"
    gmes_oqc = "GMES/OQC"
    tms = "TMS"


class ImportStatus(BaseModel):
    execution_id: str
    status: str
    source: ImportSource
    file_name: str | None = None
    extension: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    actor_type: str
    actor_identifier: str
    started_at: datetime
    finished_at: datetime | None
    failure_reason: str | None = None
    duplicate_of_execution_id: str | None = None
    pipeline_version: str
    rule_catalog_version: str
    state_version: int


class ValidationReport(BaseModel):
    execution_id: str
    source: ImportSource
    file_name: str
    valid: bool
    blocking: bool
    row_count: int
    error_count: int
    warning_count: int
    issues: list[dict]


class NormalizationResult(BaseModel):
    execution_id: str
    source: ImportSource
    file_name: str
    record_count: int
    warning_count: int
    issues: list[dict]
    records: list[dict]
    processing: dict | None = None


class PipelineSummary(BaseModel):
    rows_read: int
    valid_records: int
    rejected_records: int
    normalized_records: int
    errors: int
    warnings: int


class FileInspectionRecord(BaseModel):
    inspection_id: int
    source: ImportSource
    original_file_name: str
    extension: str | None
    declared_media_type: str | None
    detected_media_type: str | None
    size_bytes: int
    sha256: str
    decision: str
    reason_code: str
    analyzed_at: datetime
    retained_until: datetime | None
    discarded_at: datetime | None


class UploadPolicyResponse(BaseModel):
    source: ImportSource
    allowed_extensions: list[str]
    max_bytes: int


class ImportRepository(Protocol):
    def start(
        self,
        execution_id: str,
        source: str,
        actor_type: str,
        actor: str,
        organization_id: UUID | None = None,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        pipeline_version: str = PIPELINE_VERSION,
        rule_catalog_version: str = RULE_CATALOG["version"],
    ) -> None: ...

    def organization_code(self, organization_id: UUID) -> str | None: ...

    def claim_file(
        self,
        execution_id: str,
        *,
        file_name: str,
        extension: str,
        size_bytes: int,
        digest: str,
        media_type: str | None,
        detected_media_type: str = "",
        storage_key: str,
        inspection_id: int | None = None,
        source: str,
    ) -> tuple[int | None, str | None]: ...

    def record_inspection(
        self, execution_id: str, source: str, result: InspectionResult
    ) -> int: ...

    def list_inspections(self, execution_id: str) -> list[dict]: ...

    def mark_inspections_discarded(self, internal_stems: list[str]) -> None: ...

    def list_expired_inspection_stems(self) -> list[str]: ...

    def claim_processing(
        self, execution_id: str, file_hashes: list[str]
    ) -> str | None: ...

    def release_claim(self, execution_id: str) -> None: ...

    def transition_execution(
        self, execution_id: str, target: str, reason: str
    ) -> None: ...

    def mark_completed(self, execution_id: str) -> None: ...

    def mark_validation_failed(self, execution_id: str) -> None: ...

    def save_normalized_records(
        self, execution_id: str, records: list[dict]
    ) -> None: ...

    def commit_pipeline(self, execution_id: str, result: dict) -> None: ...

    def abort_claim(self, execution_id: str, reason: str) -> None: ...

    def finish(
        self,
        execution_id: str,
        state: str,
        reason: str,
        duplicate_of: str | None = None,
    ) -> None: ...

    def get(self, execution_id: str) -> dict | None: ...


class PostgresImportRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def start(
        self,
        execution_id: str,
        source: str,
        actor_type: str,
        actor: str,
        organization_id: UUID | None = None,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        pipeline_version: str = PIPELINE_VERSION,
        rule_catalog_version: str = RULE_CATALOG["version"],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO synergia.executions
                    (id, status, source, actor_type, actor_identifier,
                     pipeline_version, rule_catalog_version,
                     state_changed_by_type, state_changed_by,
                     state_change_reason, organization_id,
                     initiated_by_user_id, initiated_by_session_id)
                VALUES (%s, 'pending', %s, %s, %s, %s, %s, %s, %s,
                        'execution_created', %s, %s, %s)
                """,
                (
                    execution_id,
                    source,
                    actor_type,
                    actor,
                    pipeline_version,
                    rule_catalog_version,
                    actor_type,
                    actor,
                    organization_id,
                    user_id,
                    session_id,
                ),
            )

    def organization_code(self, organization_id: UUID) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT organization_code
                FROM synergia.iam_organizations
                WHERE id = %s AND is_active
                """,
                (organization_id,),
            ).fetchone()
            return row["organization_code"] if row else None

    def claim_file(
        self,
        execution_id: str,
        *,
        file_name: str,
        extension: str,
        size_bytes: int,
        digest: str,
        media_type: str | None,
        detected_media_type: str = "",
        storage_key: str,
        inspection_id: int | None = None,
        source: str,
    ) -> tuple[int | None, str | None]:
        with self._connect() as connection:
            inserted = connection.execute(
                """
                INSERT INTO synergia.source_files
                    (execution_id, source, file_name, extension, content_hash,
                     media_type, detected_media_type, size_bytes, storage_key,
                     inspection_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (execution_id, content_hash) DO NOTHING
                RETURNING id
                """,
                (
                    execution_id,
                    source,
                    file_name,
                    extension,
                    digest,
                    media_type,
                    detected_media_type,
                    size_bytes,
                    storage_key,
                    inspection_id,
                ),
            ).fetchone()
            if inserted:
                return inserted["id"], None

            duplicate = connection.execute(
                """
                SELECT execution_id
                FROM synergia.source_files
                WHERE execution_id = %s AND content_hash = %s
                """,
                (execution_id, digest),
            ).fetchone()
            if duplicate is None:
                raise RuntimeError("Conflito de hash sem execução original")
            return None, duplicate["execution_id"]

    def record_inspection(
        self, execution_id: str, source: str, result: InspectionResult
    ) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO synergia.file_inspections (
                    execution_id, source, original_file_name, internal_name,
                    extension, declared_media_type, detected_media_type,
                    size_bytes, content_hash, decision, reason_code,
                    analyzed_at, retained_until, discarded_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s
                )
                RETURNING id
                """,
                (
                    execution_id,
                    source,
                    result.original_name,
                    result.internal_name,
                    result.extension.lstrip(".") or None,
                    result.declared_media_type or None,
                    result.detected_media_type,
                    result.size_bytes,
                    result.sha256,
                    result.decision.value,
                    result.reason_code,
                    result.analyzed_at,
                    result.retained_until,
                    result.discarded_at,
                ),
            ).fetchone()
            return row["id"]

    def list_inspections(self, execution_id: str) -> list[dict]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT id AS inspection_id, source, original_file_name,
                       extension, declared_media_type, detected_media_type,
                       size_bytes, content_hash AS sha256, decision,
                       reason_code, analyzed_at, retained_until, discarded_at
                FROM synergia.file_inspections
                WHERE execution_id = %s
                ORDER BY id
                """,
                (execution_id,),
            ).fetchall()

    def mark_inspections_discarded(self, internal_stems: list[str]) -> None:
        if not internal_stems:
            return
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE synergia.file_inspections
                SET discarded_at = now()
                WHERE decision = 'rejected' AND discarded_at IS NULL
                  AND split_part(internal_name, '.', 1) = ANY(%s)
                """,
                (internal_stems,),
            )

    def list_expired_inspection_stems(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT split_part(internal_name, '.', 1) AS internal_stem
                FROM synergia.file_inspections
                WHERE decision = 'rejected' AND discarded_at IS NULL
                  AND retained_until <= now()
                ORDER BY id
                """
            ).fetchall()
            return [row["internal_stem"] for row in rows]

    def claim_processing(self, execution_id: str, file_hashes: list[str]) -> str | None:
        with self._connect() as connection:
            execution = connection.execute(
                """
                SELECT pipeline_version, rule_catalog_version
                FROM synergia.executions WHERE id = %s FOR UPDATE
                """,
                (execution_id,),
            ).fetchone()
            if execution is None:
                raise RuntimeError("Execução não encontrada")
            request_fingerprint = import_fingerprint(
                file_hashes,
                execution["pipeline_version"],
                execution["rule_catalog_version"],
            )
            inserted = connection.execute(
                """
                INSERT INTO synergia.execution_idempotency (
                    request_fingerprint, request_type, execution_id,
                    pipeline_version, rule_catalog_version
                ) VALUES (%s, 'import', %s, %s, %s)
                ON CONFLICT (request_fingerprint) DO NOTHING
                RETURNING execution_id
                """,
                (
                    request_fingerprint,
                    execution_id,
                    execution["pipeline_version"],
                    execution["rule_catalog_version"],
                ),
            ).fetchone()
            if inserted is not None:
                return None
            return connection.execute(
                """
                SELECT execution_id FROM synergia.execution_idempotency
                WHERE request_fingerprint = %s
                """,
                (request_fingerprint,),
            ).fetchone()["execution_id"]

    def release_claim(self, execution_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM synergia.source_files WHERE execution_id = %s",
                (execution_id,),
            )

    def transition_execution(self, execution_id: str, target: str, reason: str) -> None:
        with self._connect() as connection:
            current = connection.execute(
                "SELECT status FROM synergia.executions WHERE id = %s FOR UPDATE",
                (execution_id,),
            ).fetchone()
            if current is None:
                raise RuntimeError("Execução não encontrada")
            validate_transition(current["status"], target)
            terminal = target in {
                state.value
                for state in (
                    ExecutionState.VALIDATION_FAILED,
                    ExecutionState.COMPLETED,
                    ExecutionState.COMPLETED_WITH_ERRORS,
                    ExecutionState.FAILED,
                    ExecutionState.DUPLICATE,
                    ExecutionState.CANCELLED,
                )
            }
            connection.execute(
                """
                UPDATE synergia.executions
                SET status = %s, state_changed_by_type = 'system',
                    state_changed_by = 'synergia-api',
                    state_change_reason = %s,
                    failure_reason = CASE
                        WHEN %s IN ('failed', 'validation_failed') THEN %s
                        ELSE failure_reason
                    END,
                    finished_at = CASE WHEN %s THEN now() ELSE NULL END
                WHERE id = %s
                """,
                (target, reason, target, reason, terminal, execution_id),
            )

    def mark_completed(self, execution_id: str) -> None:
        self.transition_execution(execution_id, "completed", "pipeline_completed")

    def mark_validation_failed(self, execution_id: str) -> None:
        self.transition_execution(
            execution_id, "validation_failed", "validation_failed"
        )

    def save_normalized_records(self, execution_id: str, records: list[dict]) -> None:
        with self._connect() as connection:
            source_file = connection.execute(
                """
                SELECT id FROM synergia.source_files WHERE execution_id = %s
                """,
                (execution_id,),
            ).fetchone()
            if source_file is None:
                raise RuntimeError("Arquivo da execução não encontrado")
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO synergia.normalized_records
                        (execution_id, source_file_id, sheet_name, row_number,
                         normalized_values, original_values, transformations)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            execution_id,
                            source_file["id"],
                            record["sheet"],
                            record["row"],
                            Jsonb(record["values"]),
                            Jsonb(record["original_values"]),
                            Jsonb(record["transformations"]),
                        )
                        for record in records
                    ],
                )

    def commit_pipeline(self, execution_id: str, result: dict) -> None:
        """Persist every pipeline output in one database transaction."""
        with self._connect() as connection:
            source_files = connection.execute(
                """
                SELECT id FROM synergia.source_files
                WHERE execution_id = %s FOR UPDATE
                """,
                (execution_id,),
            ).fetchall()
            if not source_files:
                raise RuntimeError("Arquivo da execução não encontrado")
            source_file_ids = {row["id"] for row in source_files}
            primary_source_file_id = min(source_file_ids)
            rejected = {
                (
                    issue.get("source_file_id"),
                    issue.get("sheet"),
                    issue.get("row"),
                )
                for issue in result["issues"]
                if issue["severity"] == "error" and issue["scope"] == "record"
            }
            imported_ids: dict[tuple[int, str, int], int] = {}
            for record in result["imported_records"]:
                source_file_id = record["source_file_id"]
                if source_file_id not in source_file_ids:
                    raise RuntimeError("Arquivo não pertence à execução")
                key = (source_file_id, record["sheet"], record["row"])
                row = connection.execute(
                    """
                    INSERT INTO synergia.imported_records
                        (execution_id, source_file_id, sheet_name, row_number,
                         original_values, processing_status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        execution_id,
                        source_file_id,
                        record["sheet"],
                        record["row"],
                        Jsonb(record["original_values"]),
                        (
                            "rejected"
                            if result["blocking"] or key in rejected
                            else "valid"
                        ),
                    ),
                ).fetchone()
                imported_ids[key] = row["id"]
            for issue in result["issues"]:
                source_file_id = issue["source_file_id"]
                key = (source_file_id, issue.get("sheet"), issue.get("row"))
                connection.execute(
                    """
                    INSERT INTO synergia.pipeline_issues
                        (execution_id, source_file_id, imported_record_id, scope,
                         severity, code, sheet_name, row_number, column_name,
                         reason, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        execution_id,
                        source_file_id,
                        imported_ids.get(key),
                        issue["scope"],
                        issue["severity"],
                        issue["code"],
                        issue.get("sheet"),
                        issue.get("row"),
                        issue.get("column"),
                        issue["reason"],
                        Jsonb(
                            {
                                key: value
                                for key, value in issue.items()
                                if key
                                not in {
                                    "severity",
                                    "code",
                                    "sheet",
                                    "row",
                                    "column",
                                    "reason",
                                    "scope",
                                }
                            }
                        ),
                    ),
                )
            for record in result["normalized_records"]:
                source_file_id = record["source_file_id"]
                connection.execute(
                    """
                    INSERT INTO synergia.normalized_records
                        (execution_id, source_file_id, imported_record_id,
                         sheet_name, row_number, normalized_values,
                         original_values, transformations)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        execution_id,
                        source_file_id,
                        imported_ids[(source_file_id, record["sheet"], record["row"])],
                        record["sheet"],
                        record["row"],
                        Jsonb(record["values"]),
                        Jsonb(record["original_values"]),
                        Jsonb(record["transformations"]),
                    ),
                )
            summary = result["summary"]
            connection.execute(
                """
                INSERT INTO synergia.pipeline_summaries
                    (execution_id, source_file_id, rows_read, valid_records,
                     rejected_records, normalized_records, error_count, warning_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    execution_id,
                    primary_source_file_id,
                    summary["rows_read"],
                    summary["valid_records"],
                    summary["rejected_records"],
                    summary["normalized_records"],
                    summary["errors"],
                    summary["warnings"],
                ),
            )
            connection.execute(
                """
                INSERT INTO synergia.audit_events
                    (execution_id, source_file_id, entity_type, entity_id,
                     event_type, payload)
                VALUES (%s, %s, 'execution', %s, 'pipeline_finished', %s)
                """,
                (
                    execution_id,
                    primary_source_file_id,
                    execution_id,
                    Jsonb(summary),
                ),
            )
        persistence = PostgresProcessingRepository(self.database_url).persist(
            execution_id, result["processing"]
        )
        final_state = result["status"]
        if persistence["failed_workorders"] and final_state == "completed":
            final_state = "completed_with_errors"
        self.transition_execution(
            execution_id,
            final_state,
            (
                "processing_completed_with_errors"
                if final_state == "completed_with_errors"
                else "validation_failed"
                if final_state == "validation_failed"
                else "pipeline_completed"
            ),
        )
        logger.info(
            "processing_persisted execution_id=%s confirmed=%d failed=%d",
            execution_id,
            len(persistence["confirmed_workorders"]),
            len(persistence["failed_workorders"]),
        )

    def abort_claim(self, execution_id: str, reason: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM synergia.source_files WHERE execution_id = %s",
                (execution_id,),
            )
        self.transition_execution(execution_id, "failed", reason)

    def finish(
        self,
        execution_id: str,
        state: str,
        reason: str,
        duplicate_of: str | None = None,
    ) -> None:
        if duplicate_of is not None:
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE synergia.executions
                    SET duplicate_of_execution_id = %s
                    WHERE id = %s
                    """,
                    (duplicate_of, execution_id),
                )
        self.transition_execution(execution_id, state, reason)

    def get(self, execution_id: str) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT e.id AS execution_id, e.status, e.source,
                       sf.file_name, sf.extension, sf.size_bytes,
                       sf.content_hash AS sha256, e.actor_type,
                       e.actor_identifier, e.started_at, e.finished_at,
                       e.failure_reason, e.duplicate_of_execution_id,
                       e.pipeline_version, e.rule_catalog_version,
                       e.state_version
                FROM synergia.executions e
                LEFT JOIN synergia.source_files sf ON sf.execution_id = e.id
                WHERE e.id = %s
                ORDER BY sf.id
                LIMIT 1
                """,
                (execution_id,),
            ).fetchone()


def get_repository() -> Generator[ImportRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL não configurada")
    yield PostgresImportRepository(database_url)


def storage_root() -> Path:
    configured = os.getenv("IMPORT_STORAGE_DIR")
    root = (
        Path(configured)
        if configured
        else Path(__file__).resolve().parents[2] / "data" / "imports"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def configured_organizations() -> set[str] | None:
    configured = os.getenv("VALID_ORGANIZATION_CODES")
    if configured is None:
        return None
    values = {value.strip().upper() for value in configured.split(",") if value.strip()}
    return values or None


def _write_pipeline_artifacts(directory: Path, pipeline: dict) -> None:
    summary = pipeline["summary"]
    report = {
        "execution_id": pipeline["execution_id"],
        "source": pipeline["source"],
        "file_name": pipeline["file_name"],
        "valid": summary["errors"] == 0,
        "blocking": pipeline["blocking"],
        "row_count": summary["rows_read"],
        "error_count": summary["errors"],
        "warning_count": summary["warnings"],
        "issues": pipeline["issues"],
    }
    normalized = {
        "execution_id": pipeline["execution_id"],
        "source": pipeline["source"],
        "file_name": pipeline["file_name"],
        "record_count": summary["normalized_records"],
        "warning_count": summary["warnings"],
        "issues": [
            issue for issue in pipeline["issues"] if issue["severity"] == "warning"
        ],
        "records": pipeline["normalized_records"],
        "processing": pipeline["processing"],
    }
    artifacts = {
        "validation-report.json": json.dumps(
            report, ensure_ascii=False, indent=2, default=str
        )
        + "\n",
        "pipeline-summary.json": json.dumps(summary, ensure_ascii=False, indent=2)
        + "\n",
    }
    if normalized["record_count"] or not pipeline["blocking"]:
        artifacts["normalized-data.json"] = (
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
        )

    temporary: list[tuple[Path, Path]] = []
    targets = [directory / name for name in artifacts]
    try:
        for name, content in artifacts.items():
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=directory, delete=False
            ) as stream:
                stream.write(content)
                temporary.append((Path(stream.name), directory / name))
        for temp_path, target in temporary:
            temp_path.replace(target)
    except Exception:
        for temp_path, _ in temporary:
            temp_path.unlink(missing_ok=True)
        for target in targets:
            target.unlink(missing_ok=True)
        raise


def _remove_pipeline_artifacts(directory: Path) -> None:
    for name in (
        "validation-report.json",
        "pipeline-summary.json",
        "normalized-data.json",
    ):
        (directory / name).unlink(missing_ok=True)


def _error(
    repository: ImportRepository,
    execution_id: str,
    http_status: int,
    code: str,
    message: str,
) -> None:
    current = repository.get(execution_id)
    if current is not None and current["status"] != "failed":
        repository.finish(execution_id, "failed", code)
    logger.warning("import_failed execution_id=%s reason=%s", execution_id, code)
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message, "execution_id": execution_id},
    )


INSPECTION_MESSAGES = {
    "unsupported_extension": "Formato de arquivo não permitido para a fonte",
    "empty_file": "Arquivo vazio",
    "file_too_large": "Arquivo acima do limite permitido",
    "path_traversal": "Nome de arquivo inválido",
    "declared_mime_mismatch": "MIME declarado incompatível com o arquivo",
    "content_signature_mismatch": "Conteúdo incompatível com a extensão",
    "binary_content_mismatch": "Conteúdo binário incompatível com a extensão",
    "content_type_mismatch": "Tipo real incompatível com a extensão",
    "disguised_active_content": "Conteúdo ativo disfarçado de planilha",
    "invalid_text_encoding": "Codificação de texto não permitida",
    "corrupted_file": "Arquivo truncado ou corrompido",
    "macro_or_active_content": "Macro ou conteúdo ativo não permitido",
    "embedded_object": "Objeto incorporado não permitido",
    "external_link": "Vínculo externo não permitido",
    "dangerous_formula": "Fórmula potencialmente perigosa",
    "archive_too_many_entries": "Arquivo compactado com entradas em excesso",
    "archive_uncompressed_limit": "Conteúdo descompactado acima do limite",
    "archive_compression_ratio": "Razão de compressão abusiva",
    "archive_path_traversal": "Caminho inseguro dentro do arquivo compactado",
    "encrypted_archive": "Arquivo compactado criptografado não permitido",
}


def _inspection_http_status(reason_code: str) -> int:
    if reason_code == "file_too_large":
        return status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    if reason_code in {
        "unsupported_extension",
        "declared_mime_mismatch",
        "content_signature_mismatch",
        "binary_content_mismatch",
        "content_type_mismatch",
        "disguised_active_content",
    }:
        return status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    return status.HTTP_422_UNPROCESSABLE_ENTITY


@router.post(
    "",
    response_model=ImportStatus,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar e registrar um arquivo de entrada",
    responses={
        413: {"model": ErrorResponse, "description": "Arquivo acima do limite"},
        409: {"model": ErrorResponse, "description": "Arquivo duplicado por SHA-256"},
        415: {"model": ErrorResponse, "description": "Extensão não suportada"},
        422: {
            "model": ErrorResponse,
            "description": "Arquivo vazio, inválido ou requisição inválida",
        },
        500: {
            "model": ErrorResponse,
            "description": "Falha ao preservar o arquivo no storage",
        },
    },
)
async def upload_import(
    source: Annotated[
        list[ImportSource], Form(description="Sistema de origem de cada arquivo")
    ],
    file: Annotated[list[UploadFile], File(description="Arquivos XLSX, CSV ou JSON")],
    request: Request,
    actor: Annotated[ActorContext, Depends(require_permission("import.create"))],
    authorization_repository: AuthorizationRepo,
    organization_id: Annotated[
        UUID | None, Form(description="Organização IAM autorizada para a execução")
    ] = None,
    repository: ImportRepository = Depends(get_repository),
) -> ImportStatus:
    execution_id = str(uuid4())
    if not source or len(source) != len(file):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "source_file_mismatch",
                "message": "Informe uma fonte para cada arquivo",
            },
        )
    file_names = [Path(item.filename or "").name for item in file]
    if len(file_names) != len(set(file_names)):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "duplicate_file_name",
                "message": "Os nomes dos arquivos devem ser únicos na execução",
            },
        )
    if organization_id is None:
        available = actor.organization_ids("import.create")
        if len(available) == 1:
            organization_id = next(iter(available))
    if organization_id is None or not actor.allows("import.create", organization_id):
        authorization_repository.audit_denial(
            actor,
            "import.create",
            request,
            organization_id=organization_id,
        )
        raise HTTPException(
            status_code=403,
            detail={"code": "access_denied", "message": "Acao nao autorizada"},
        )
    organization_code = repository.organization_code(organization_id)
    if organization_code is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "organization_not_found",
                "message": "Organizacao nao encontrada",
            },
        )
    actor_identifier = str(actor.user_id)
    repository.start(
        execution_id,
        source[0].value,
        "user",
        actor_identifier,
        organization_id,
        actor.user_id,
        actor.session_id,
    )
    logger.info(
        "import_started execution_id=%s sources=%s",
        execution_id,
        ",".join(item.value for item in source),
    )

    destinations: list[Path] = []
    pipeline_inputs: list[dict] = []
    file_hashes: list[str] = []
    try:
        removed_inspections = purge_quarantined(
            storage_root(), repository.list_expired_inspection_stems()
        )
        repository.mark_inspections_discarded(removed_inspections)
        for item_source, item_file in zip(source, file, strict=True):
            inspection = await receive_and_inspect(
                item_file,
                source=item_source.value,
                execution_id=execution_id,
                root=storage_root(),
            )
            try:
                inspection_id = repository.record_inspection(
                    execution_id, item_source.value, inspection
                )
            except Exception:
                if inspection.quarantine_path is not None:
                    inspection.quarantine_path.unlink(missing_ok=True)
                raise
            if not inspection.accepted:
                for stored in destinations:
                    stored.unlink(missing_ok=True)
                if pipeline_inputs:
                    repository.abort_claim(execution_id, inspection.reason_code)
                _error(
                    repository,
                    execution_id,
                    _inspection_http_status(inspection.reason_code),
                    inspection.reason_code,
                    INSPECTION_MESSAGES.get(
                        inspection.reason_code, "Arquivo rejeitado pela inspeção"
                    ),
                )
            try:
                destination = release_to_accepted(
                    inspection,
                    source_key=item_source.name,
                    execution_id=execution_id,
                    root=storage_root(),
                )
            except OSError as exc:
                if inspection.quarantine_path is not None:
                    inspection.quarantine_path.unlink(missing_ok=True)
                for stored in destinations:
                    stored.unlink(missing_ok=True)
                repository.abort_claim(execution_id, "storage_error")
                logger.exception("import_storage_failed execution_id=%s", execution_id)
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "storage_error",
                        "message": "Não foi possível preservar o arquivo",
                        "execution_id": execution_id,
                    },
                ) from exc
            destinations.append(destination)
            storage_key = str(destination.relative_to(storage_root()))
            tables, read_issues = read_source(
                destination, inspection.extension, item_source.value
            )
            source_file_id, duplicate_of = repository.claim_file(
                execution_id,
                source=item_source.value,
                file_name=inspection.original_name,
                extension=inspection.extension[1:],
                size_bytes=inspection.size_bytes,
                digest=inspection.sha256,
                media_type=inspection.declared_media_type,
                detected_media_type=inspection.detected_media_type or "",
                storage_key=storage_key,
                inspection_id=inspection_id,
            )
            if duplicate_of:
                for stored in destinations:
                    stored.unlink(missing_ok=True)
                repository.abort_claim(execution_id, "duplicate_file")
                if duplicate_of != execution_id:
                    repository.finish(
                        execution_id, "duplicate", "duplicate_file", duplicate_of
                    )
                logger.info(
                    "import_duplicate execution_id=%s duplicate_of=%s",
                    execution_id,
                    duplicate_of,
                )
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "duplicate_file",
                        "message": "Arquivo já importado",
                        "execution_id": execution_id,
                        "duplicate_of_execution_id": duplicate_of,
                    },
                )
            if source_file_id is None:
                raise RuntimeError("Arquivo reservado sem identificador")
            file_hashes.append(inspection.sha256)
            pipeline_inputs.append(
                {
                    "file_name": inspection.original_name,
                    "source": item_source.value,
                    "source_file_id": source_file_id,
                    "tables": tables,
                    "read_issues": read_issues,
                }
            )
        duplicate_of = repository.claim_processing(execution_id, file_hashes)
        if duplicate_of:
            for stored in destinations:
                stored.unlink(missing_ok=True)
            for directory in {stored.parent for stored in destinations}:
                directory.rmdir()
            repository.release_claim(execution_id)
            repository.finish(
                execution_id, "duplicate", "duplicate_processing_request", duplicate_of
            )
            logger.info(
                "import_duplicate execution_id=%s duplicate_of=%s",
                execution_id,
                duplicate_of,
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate_file",
                    "message": "Arquivos já processados nestas versões",
                    "execution_id": execution_id,
                    "duplicate_of_execution_id": duplicate_of,
                },
            )
        try:
            artifact_directory = destinations[0].parent
            run_pipeline_batch(
                execution_id=execution_id,
                inputs=pipeline_inputs,
                repository=repository,
                classified_at=datetime.now(UTC).isoformat(),
                known_organizations={organization_code.upper()},
                prepare_commit=lambda result: _write_pipeline_artifacts(
                    artifact_directory, result
                ),
            )
        except Exception as exc:
            _remove_pipeline_artifacts(destinations[0].parent)
            repository.finish(execution_id, "failed", "pipeline_error")
            logger.exception("import_pipeline_failed execution_id=%s", execution_id)
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "pipeline_error",
                    "message": "Não foi possível processar o arquivo",
                    "execution_id": execution_id,
                },
            ) from exc
        logger.info(
            "import_processed execution_id=%s file_count=%d", execution_id, len(file)
        )
    except HTTPException:
        raise
    except ValueError as exc:
        for destination in destinations:
            destination.unlink(missing_ok=True)
        if pipeline_inputs:
            repository.abort_claim(execution_id, "invalid_file")
        _error(repository, execution_id, 422, "invalid_file", str(exc))
    except Exception as exc:
        for destination in destinations:
            destination.unlink(missing_ok=True)
        repository.abort_claim(execution_id, "preparation_error")
        logger.exception("import_preparation_failed execution_id=%s", execution_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "preparation_error",
                "message": "Não foi possível preparar os arquivos",
                "execution_id": execution_id,
            },
        ) from exc
    finally:
        for item_file in file:
            await item_file.close()

    result = repository.get(execution_id)
    if result is None:
        raise RuntimeError("Execução recém-criada não encontrada")
    return ImportStatus.model_validate(result)


@router.get(
    "/policy",
    response_model=list[UploadPolicyResponse],
    summary="Consultar a política ativa de upload por fonte",
    dependencies=[Depends(require_permission("import.create"))],
)
async def get_upload_policy() -> list[UploadPolicyResponse]:
    result = []
    for source in ImportSource:
        policy = policy_for(source.value)
        result.append(
            UploadPolicyResponse(
                source=source,
                allowed_extensions=sorted(
                    extension.lstrip(".") for extension in policy.allowed_extensions
                ),
                max_bytes=policy.max_bytes,
            )
        )
    return result


@router.get(
    "/{execution_id}",
    response_model=ImportStatus,
    summary="Consultar o estado de uma importação",
    responses={404: {"model": ErrorResponse, "description": "Execução não encontrada"}},
    dependencies=[Depends(require_execution_permission("import.read"))],
)
def get_import(
    execution_id: str,
    repository: ImportRepository = Depends(get_repository),
) -> ImportStatus:
    result = repository.get(execution_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail="Execução de importação não encontrada"
        )
    return ImportStatus.model_validate(result)


@router.get(
    "/{execution_id}/inspections",
    response_model=list[FileInspectionRecord],
    summary="Consultar as decisões de segurança dos arquivos",
    responses={404: {"model": ErrorResponse, "description": "Execução não encontrada"}},
    dependencies=[Depends(require_execution_permission("import.read"))],
)
def get_file_inspections(
    execution_id: str,
    repository: ImportRepository = Depends(get_repository),
) -> list[FileInspectionRecord]:
    if repository.get(execution_id) is None:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    return [
        FileInspectionRecord.model_validate(item)
        for item in repository.list_inspections(execution_id)
    ]


@router.get(
    "/{execution_id}/validation-report",
    response_model=ValidationReport,
    summary="Visualizar o relatório de validação da execução",
    responses={
        404: {"model": ErrorResponse, "description": "Relatório não encontrado"}
    },
    dependencies=[Depends(require_execution_permission("artifact.read"))],
)
def get_validation_report(
    execution_id: str,
    repository: ImportRepository = Depends(get_repository),
) -> ValidationReport:
    execution = repository.get(execution_id)
    if execution is None:
        raise HTTPException(
            status_code=404, detail="Execução de importação não encontrada"
        )
    source = ImportSource(execution["source"])
    report_path = (
        storage_root()
        / "accepted"
        / source.name
        / execution_id
        / "validation-report.json"
    )
    if not report_path.is_file():
        raise HTTPException(
            status_code=404, detail="Relatório de validação não disponível"
        )
    with report_path.open(encoding="utf-8") as stream:
        return ValidationReport.model_validate(json.load(stream))


@router.get(
    "/{execution_id}/normalized-data",
    response_model=NormalizationResult,
    summary="Visualizar os dados normalizados da execução",
    responses={404: {"model": ErrorResponse, "description": "Dados não encontrados"}},
    dependencies=[Depends(require_execution_permission("artifact.read"))],
)
def get_normalized_data(
    execution_id: str,
    repository: ImportRepository = Depends(get_repository),
) -> NormalizationResult:
    execution = repository.get(execution_id)
    if execution is None:
        raise HTTPException(
            status_code=404, detail="Execução de importação não encontrada"
        )
    source = ImportSource(execution["source"])
    normalized_path = (
        storage_root()
        / "accepted"
        / source.name
        / execution_id
        / "normalized-data.json"
    )
    if not normalized_path.is_file():
        raise HTTPException(
            status_code=404, detail="Dados normalizados não disponíveis"
        )
    with normalized_path.open(encoding="utf-8") as stream:
        return NormalizationResult.model_validate(json.load(stream))


@router.get(
    "/{execution_id}/pipeline-summary",
    response_model=PipelineSummary,
    summary="Visualizar as contagens do pipeline integrado",
    responses={404: {"model": ErrorResponse, "description": "Resumo não encontrado"}},
    dependencies=[Depends(require_execution_permission("import.read"))],
)
def get_pipeline_summary(
    execution_id: str,
    repository: ImportRepository = Depends(get_repository),
) -> PipelineSummary:
    execution = repository.get(execution_id)
    if execution is None:
        raise HTTPException(
            status_code=404, detail="Execução de importação não encontrada"
        )
    source = ImportSource(execution["source"])
    summary_path = (
        storage_root()
        / "accepted"
        / source.name
        / execution_id
        / "pipeline-summary.json"
    )
    if not summary_path.is_file():
        raise HTTPException(status_code=404, detail="Resumo do pipeline não disponível")
    with summary_path.open(encoding="utf-8") as stream:
        return PipelineSummary.model_validate(json.load(stream))
