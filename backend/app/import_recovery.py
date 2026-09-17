from __future__ import annotations

import hashlib
from datetime import UTC
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.business_rules import RULE_CATALOG
from app.execution import PIPELINE_VERSION, import_fingerprint
from app.imports import PostgresImportRepository, _write_pipeline_artifacts
from app.pipeline import read_source, run_pipeline_batch


class ImportRecoveryError(ValueError):
    """An interrupted execution cannot be resumed without violating integrity."""


def _verified_path(root: Path, storage_key: str, digest: str, size: int | None):
    if not storage_key or Path(storage_key).is_absolute():
        raise ImportRecoveryError("Arquivo aceito sem chave relativa segura")
    root = root.resolve(strict=True)
    try:
        path = (root / storage_key).resolve(strict=True)
        path.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ImportRecoveryError("Arquivo aceito fora do armazenamento") from exc
    if "accepted" not in path.relative_to(root).parts:
        raise ImportRecoveryError("Arquivo não está na área aceita")
    hasher = hashlib.sha256()
    actual_size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
            actual_size += len(chunk)
    if hasher.hexdigest() != digest or (size is not None and size != actual_size):
        raise ImportRecoveryError("Hash ou tamanho do arquivo aceito divergiu")
    return path


def _advance(
    repository: PostgresImportRepository,
    execution_id: str,
    status: str,
    result_status: str,
) -> None:
    if result_status == "validation_failed":
        if status in {"pending", "reprocessing"}:
            repository.transition_execution(
                execution_id, "validating", "interrupted_pipeline_resumed"
            )
            return
        if status != "validating":
            raise ImportRecoveryError("Validação bloqueante mudou durante a retomada")
        return
    remaining = {
        "pending": ("validating", "normalizing", "consolidating", "applying_rules"),
        "reprocessing": (
            "validating",
            "normalizing",
            "consolidating",
            "applying_rules",
        ),
        "validating": ("normalizing", "consolidating", "applying_rules"),
        "normalizing": ("consolidating", "applying_rules"),
        "consolidating": ("applying_rules",),
        "applying_rules": (),
    }[status]
    for target in remaining:
        repository.transition_execution(
            execution_id, target, "interrupted_pipeline_resumed"
        )


def _recover_import_locked(
    database_url: str,
    storage_root: Path,
    execution_id: str,
    *,
    apply: bool = False,
) -> dict:
    """Inspect and recover while the per-execution recovery lock is held."""
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        execution = connection.execute(
            """
            SELECT e.status, e.started_at, e.pipeline_version,
                   e.rule_catalog_version, o.organization_code
            FROM synergia.executions e
            LEFT JOIN synergia.iam_organizations o ON o.id = e.organization_id
            WHERE e.id = %s
            """,
            (execution_id,),
        ).fetchone()
        if execution is None:
            raise ImportRecoveryError("Execução não encontrada")
        if execution["status"] in {
            "completed",
            "completed_with_errors",
            "validation_failed",
            "failed",
            "duplicate",
            "cancelled",
        }:
            return {
                "execution_id": execution_id,
                "action": "already_terminal",
                "status": execution["status"],
            }
        if execution["status"] not in {
            "pending",
            "reprocessing",
            "validating",
            "normalizing",
            "consolidating",
            "applying_rules",
        }:
            raise ImportRecoveryError("Estado de execução não recuperável")
        if (
            execution["pipeline_version"] != PIPELINE_VERSION
            or execution["rule_catalog_version"] != RULE_CATALOG["version"]
        ):
            raise ImportRecoveryError("Versão do pipeline ou catálogo mudou")
        output_count = connection.execute(
            """
            SELECT (SELECT count(*) FROM synergia.pipeline_summaries
                    WHERE execution_id = %s)
                 + (SELECT count(*) FROM synergia.imported_records
                    WHERE execution_id = %s)
                 + (SELECT count(*) FROM synergia.normalized_records
                    WHERE execution_id = %s)
                 + (SELECT count(*) FROM synergia.pipeline_issues
                    WHERE execution_id = %s)
                 + (SELECT count(*) FROM synergia.workorders
                    WHERE execution_id = %s) AS total
            """,
            (execution_id,) * 5,
        ).fetchone()["total"]
        if output_count:
            raise ImportRecoveryError(
                "Execução legada com saída parcial exige reconciliação manual"
            )
        files = connection.execute(
            """
            SELECT id, source, file_name, extension, content_hash,
                   size_bytes, storage_key
            FROM synergia.source_files WHERE execution_id = %s ORDER BY id
            """,
            (execution_id,),
        ).fetchall()
        claim = connection.execute(
            "SELECT request_fingerprint FROM synergia.execution_idempotency "
            "WHERE execution_id = %s AND request_type = 'import'",
            (execution_id,),
        ).fetchone()
    if claim is None:
        if execution["status"] not in {"pending", "reprocessing"}:
            raise ImportRecoveryError("Execução ativa sem reserva idempotente")
        if apply:
            PostgresImportRepository(database_url).transition_execution(
                execution_id, "failed", "interrupted_before_processing"
            )
        return {
            "execution_id": execution_id,
            "action": "fail_incomplete_reservation",
            "applied": apply,
            "source_files": len(files),
        }
    if not files or not execution["organization_code"]:
        raise ImportRecoveryError("Arquivos ou organização da execução ausentes")
    hashes = [file["content_hash"] for file in files]
    expected = import_fingerprint(
        hashes, execution["pipeline_version"], execution["rule_catalog_version"]
    )
    if claim["request_fingerprint"] != expected:
        raise ImportRecoveryError("Reserva idempotente não corresponde aos arquivos")
    paths = [
        _verified_path(
            storage_root, file["storage_key"], file["content_hash"], file["size_bytes"]
        )
        for file in files
    ]
    # Multi-source imports live under accepted/<source>/<execution_id>. The
    # source directories differ by design; the execution directory must not.
    if {path.parent.name for path in paths} != {execution_id}:
        raise ImportRecoveryError("Arquivos aceitos não compartilham a execução")
    preview = {
        "execution_id": execution_id,
        "action": "resume_pipeline",
        "applied": False,
        "source_files": len(files),
        "status_before": execution["status"],
    }
    if not apply:
        return preview
    repository = PostgresImportRepository(database_url)
    inputs = []
    for file, path in zip(files, paths, strict=True):
        extension = "." + str(file["extension"] or "").lstrip(".")
        if path.suffix.lower() != extension.lower():
            raise ImportRecoveryError("Extensão do arquivo aceito divergiu")
        tables, read_issues = read_source(path, extension, file["source"])
        inputs.append(
            {
                "file_name": file["file_name"],
                "source": file["source"],
                "source_file_id": file["id"],
                "tables": tables,
                "read_issues": read_issues,
            }
        )

    def prepare(result: dict) -> None:
        _advance(repository, execution_id, execution["status"], result["status"])
        _write_pipeline_artifacts(paths[0].parent, result)

    result = run_pipeline_batch(
        execution_id=execution_id,
        inputs=inputs,
        repository=repository,
        classified_at=execution["started_at"].astimezone(UTC).isoformat(),
        known_organizations={execution["organization_code"].upper()},
        prepare_commit=prepare,
        resume=True,
    )
    final = repository.get(execution_id)
    return {
        **preview,
        "applied": True,
        "status_after": final["status"],
        "normalized_records": result["summary"]["normalized_records"],
    }


def recover_import(
    database_url: str,
    storage_root: Path,
    execution_id: str,
    *,
    apply: bool = False,
) -> dict:
    """Preview or resume one import from its verified accepted source files.

    Apply only with upload workers stopped. A session-level advisory lock
    serializes repeated recovery calls for the same execution and is released
    automatically if the operator process exits abruptly.
    """
    if not apply:
        return _recover_import_locked(
            database_url, storage_root, execution_id, apply=False
        )
    with psycopg.connect(database_url, autocommit=True) as lock_connection:
        lock_connection.execute(
            "SELECT pg_advisory_lock(hashtext(%s))",
            (f"synergia-import-recovery:{execution_id}",),
        )
        try:
            return _recover_import_locked(
                database_url, storage_root, execution_id, apply=True
            )
        finally:
            lock_connection.execute(
                "SELECT pg_advisory_unlock(hashtext(%s))",
                (f"synergia-import-recovery:{execution_id}",),
            )
