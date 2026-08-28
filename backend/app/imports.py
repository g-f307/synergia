from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from collections.abc import Generator
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Protocol
from uuid import uuid4

import psycopg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from app.errors import ErrorResponse
from app.pipeline import read_source, run_pipeline

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


class ImportRepository(Protocol):
    def start(
        self, execution_id: str, source: str, actor_type: str, actor: str
    ) -> None: ...

    def claim_file(
        self,
        execution_id: str,
        *,
        file_name: str,
        extension: str,
        size_bytes: int,
        digest: str,
        media_type: str | None,
        storage_key: str,
    ) -> str | None: ...

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
        self, execution_id: str, source: str, actor_type: str, actor: str
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO synergia.executions
                    (id, status, source, actor_type, actor_identifier)
                VALUES (%s, 'running', %s, %s, %s)
                """,
                (execution_id, source, actor_type, actor),
            )

    def claim_file(
        self,
        execution_id: str,
        *,
        file_name: str,
        extension: str,
        size_bytes: int,
        digest: str,
        media_type: str | None,
        storage_key: str,
    ) -> str | None:
        with self._connect() as connection:
            inserted = connection.execute(
                """
                INSERT INTO synergia.source_files
                    (execution_id, file_name, extension, content_hash, media_type,
                     size_bytes, storage_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (content_hash) DO NOTHING
                RETURNING execution_id
                """,
                (
                    execution_id,
                    file_name,
                    extension,
                    digest,
                    media_type,
                    size_bytes,
                    storage_key,
                ),
            ).fetchone()
            if inserted:
                return None

            duplicate = connection.execute(
                """
                SELECT execution_id
                FROM synergia.source_files
                WHERE content_hash = %s
                """,
                (digest,),
            ).fetchone()
            if duplicate is None:
                raise RuntimeError("Conflito de hash sem execução original")
            return duplicate["execution_id"]

    def mark_completed(self, execution_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE synergia.executions
                SET status = 'completed', finished_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (execution_id,),
            )

    def mark_validation_failed(self, execution_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE synergia.executions
                SET status = 'validation_failed', failure_reason = 'validation_failed',
                    finished_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (execution_id,),
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
            source_file = connection.execute(
                """
                SELECT id FROM synergia.source_files
                WHERE execution_id = %s FOR UPDATE
                """,
                (execution_id,),
            ).fetchone()
            if source_file is None:
                raise RuntimeError("Arquivo da execução não encontrado")
            source_file_id = source_file["id"]
            rejected = {
                (issue.get("sheet"), issue.get("row"))
                for issue in result["issues"]
                if issue["severity"] == "error" and issue["scope"] == "record"
            }
            imported_ids: dict[tuple[str, int], int] = {}
            for record in result["imported_records"]:
                key = (record["sheet"], record["row"])
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
                key = (issue.get("sheet"), issue.get("row"))
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
                        imported_ids[(record["sheet"], record["row"])],
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
                    source_file_id,
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
                (execution_id, source_file_id, execution_id, Jsonb(summary)),
            )
            connection.execute(
                """
                UPDATE synergia.executions
                SET status = %s, failure_reason = %s, finished_at = now(),
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    result["status"],
                    "validation_failed" if result["blocking"] else None,
                    execution_id,
                ),
            )

    def abort_claim(self, execution_id: str, reason: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM synergia.source_files WHERE execution_id = %s",
                (execution_id,),
            )
            connection.execute(
                """
                UPDATE synergia.executions
                SET status = 'failed', failure_reason = %s,
                    finished_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (reason, execution_id),
            )

    def finish(
        self,
        execution_id: str,
        state: str,
        reason: str,
        duplicate_of: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE synergia.executions
                SET status = %s, failure_reason = %s,
                    duplicate_of_execution_id = %s,
                    finished_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (state, reason, duplicate_of, execution_id),
            )

    def get(self, execution_id: str) -> dict | None:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT e.id AS execution_id, e.status, e.source,
                       sf.file_name, sf.extension, sf.size_bytes,
                       sf.content_hash AS sha256, e.actor_type,
                       e.actor_identifier, e.started_at, e.finished_at,
                       e.failure_reason, e.duplicate_of_execution_id
                FROM synergia.executions e
                LEFT JOIN synergia.source_files sf ON sf.execution_id = e.id
                WHERE e.id = %s
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
    repository.finish(execution_id, "failed", code)
    logger.warning("import_failed execution_id=%s reason=%s", execution_id, code)
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message, "execution_id": execution_id},
    )


@router.post(
    "",
    response_model=ImportStatus,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar e registrar um arquivo de entrada",
    responses={
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
    source: Annotated[ImportSource, Form(description="Sistema de origem do arquivo")],
    file: Annotated[UploadFile, File(description="Arquivo XLSX, CSV ou JSON")],
    imported_by: Annotated[str | None, Form(description="Usuário responsável")] = None,
    technical_origin: Annotated[
        str | None, Form(description="Identificador da origem técnica")
    ] = None,
    repository: ImportRepository = Depends(get_repository),
) -> ImportStatus:
    execution_id = str(uuid4())
    actor_type, actor = (
        ("user", imported_by.strip())
        if imported_by and imported_by.strip()
        else ("technical", technical_origin.strip())
        if technical_origin and technical_origin.strip()
        else ("", "")
    )
    if not actor:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "missing_actor",
                "message": "Informe imported_by ou technical_origin",
            },
        )
    repository.start(execution_id, source.value, actor_type, actor)
    logger.info("import_started execution_id=%s source=%s", execution_id, source.value)

    safe_name = Path(file.filename or "").name
    extension = Path(safe_name).suffix.lower()
    if extension not in {".xlsx", ".csv", ".json"}:
        _error(
            repository,
            execution_id,
            415,
            "unsupported_extension",
            "Extensão não suportada",
        )

    temp_path: Path | None = None
    try:
        digest = hashlib.sha256()
        size_bytes = 0
        with NamedTemporaryFile(
            delete=False, dir=storage_root(), suffix=".upload"
        ) as temp:
            temp_path = Path(temp.name)
            while chunk := await file.read(1024 * 1024):
                size_bytes += len(chunk)
                digest.update(chunk)
                temp.write(chunk)
        if size_bytes == 0:
            _error(repository, execution_id, 422, "empty_file", "Arquivo vazio")
        content_hash = digest.hexdigest()
        tables, read_issues = read_source(temp_path, extension, source.value)
        destination = (
            storage_root() / source.name / execution_id / f"original{extension}"
        )
        storage_key = str(destination.relative_to(storage_root()))
        duplicate_of = repository.claim_file(
            execution_id,
            file_name=safe_name,
            extension=extension[1:],
            size_bytes=size_bytes,
            digest=content_hash,
            media_type=file.content_type,
            storage_key=storage_key,
        )
        if duplicate_of:
            repository.finish(execution_id, "duplicate", "duplicate_file", duplicate_of)
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
        try:
            destination.parent.mkdir(parents=True, exist_ok=False)
            shutil.move(temp_path, destination)
            temp_path = None
        except OSError as exc:
            destination.unlink(missing_ok=True)
            try:
                destination.parent.rmdir()
            except OSError:
                pass
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
        try:
            run_pipeline(
                execution_id=execution_id,
                file_name=safe_name,
                source=source.value,
                repository=repository,
                tables=tables,
                read_issues=read_issues,
                classified_at=datetime.now(UTC).isoformat(),
                known_organizations=configured_organizations(),
                prepare_commit=lambda result: _write_pipeline_artifacts(
                    destination.parent, result
                ),
            )
        except Exception as exc:
            _remove_pipeline_artifacts(destination.parent)
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
            "import_processed execution_id=%s size_bytes=%d", execution_id, size_bytes
        )
    except HTTPException:
        raise
    except ValueError as exc:
        _error(repository, execution_id, 422, "invalid_file", str(exc))
    finally:
        await file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    result = repository.get(execution_id)
    if result is None:
        raise RuntimeError("Execução recém-criada não encontrada")
    return ImportStatus.model_validate(result)


@router.get(
    "/{execution_id}",
    response_model=ImportStatus,
    summary="Consultar o estado de uma importação",
    responses={404: {"model": ErrorResponse, "description": "Execução não encontrada"}},
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
    "/{execution_id}/validation-report",
    response_model=ValidationReport,
    summary="Visualizar o relatório de validação da execução",
    responses={
        404: {"model": ErrorResponse, "description": "Relatório não encontrado"}
    },
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
    report_path = storage_root() / source.name / execution_id / "validation-report.json"
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
        storage_root() / source.name / execution_id / "normalized-data.json"
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
    summary_path = storage_root() / source.name / execution_id / "pipeline-summary.json"
    if not summary_path.is_file():
        raise HTTPException(status_code=404, detail="Resumo do pipeline não disponível")
    with summary_path.open(encoding="utf-8") as stream:
        return PipelineSummary.model_validate(json.load(stream))
