from __future__ import annotations

import json
from collections.abc import Callable, Collection
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from app.normalization import normalize_column_name, normalize_tables
from app.processing import process_normalized_records
from app.validation import (
    DataReadError,
    failed_validation_report,
    read_tables,
    validate_tables,
)

STRUCTURAL_ISSUES = {
    "empty_file",
    "empty_sheet",
    "invalid_header",
    "invalid_structure",
    "missing_column",
    "read_error",
    "validation_read_error",
}


class PipelineRepository(Protocol):
    def commit_pipeline(self, execution_id: str, result: dict[str, Any]) -> None: ...


class SourceImporter(Protocol):
    def read(
        self, path: Path, extension: str
    ) -> tuple[list[tuple[str, list[str], list[list[Any]]]], list[dict[str, Any]]]: ...


class TabularSourceImporter:
    def read(
        self, path: Path, extension: str
    ) -> tuple[list[tuple[str, list[str], list[list[Any]]]], list[dict[str, Any]]]:
        return read_tables(path, extension)


IMPORTERS: dict[str, SourceImporter] = {
    source: TabularSourceImporter() for source in ("N-FP", "OWM", "GMES/OQC", "TMS")
}


def read_source(
    path: Path,
    extension: str,
    source: str,
    importers: dict[str, SourceImporter] | None = None,
) -> tuple[list[tuple[str, list[str], list[list[Any]]]], list[dict[str, Any]]]:
    """Read a source file once and convert recoverable read errors into issues."""
    importer = (importers or IMPORTERS).get(source)
    if importer is None:
        raise ValueError(f"Fonte sem importador configurado: {source}")

    try:
        return importer.read(path, extension)
    except DataReadError as exc:
        report = failed_validation_report(
            source, "read_error", exc.reason, sheet=exc.sheet, row=exc.row
        )
        return [], report["issues"]
    except (json.JSONDecodeError, UnicodeError, OSError) as exc:
        raise ValueError(f"arquivo {extension[1:].upper()} inválido") from exc
    except Exception as exc:
        if extension == ".xlsx":
            raise ValueError("arquivo XLSX inválido") from exc
        raise


def _original_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _imported_records(
    tables: list[tuple[str, list[str], list[list[Any]]]], source: str
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for sheet, headers, rows in tables:
        fields = [normalize_column_name(header) for header in headers]
        for row_number, row in enumerate(rows, 2):
            if not any(value not in (None, "") for value in row):
                continue
            records.append(
                {
                    "source": source,
                    "sheet": sheet,
                    "row": row_number,
                    "original_values": {
                        field: (
                            _original_value(row[index]) if index < len(row) else None
                        )
                        for index, field in enumerate(fields)
                    },
                }
            )
    return records


def run_pipeline(
    *,
    execution_id: str,
    file_name: str,
    source: str,
    repository: PipelineRepository,
    tables: list[tuple[str, list[str], list[list[Any]]]],
    read_issues: list[dict[str, Any]],
    classified_at: str,
    known_organizations: Collection[str] | None = None,
    prepare_commit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Import, validate and normalize one stored file, then commit atomically."""
    validation = validate_tables(tables, source, known_organizations, read_issues)

    imported = _imported_records(tables, source)
    issues = validation["issues"]
    structural_blocked = any(
        issue["severity"] == "error" and issue["code"] in STRUCTURAL_ISSUES
        for issue in issues
    )
    rejected_rows = {
        (issue["sheet"], issue["row"])
        for issue in issues
        if issue["severity"] == "error" and (issue.get("row") or 0) > 1
    }
    eligible_rows = (
        set()
        if structural_blocked
        else {(record["sheet"], record["row"]) for record in imported} - rejected_rows
    )
    normalized = normalize_tables(tables, source, eligible_rows)
    normalized_records = [
        {**record, "execution_id": execution_id} for record in normalized["records"]
    ]
    processing = process_normalized_records(
        normalized_records,
        execution_id=execution_id,
        classified_at=classified_at,
    )
    issues = [*issues, *normalized["issues"]]
    for issue in issues:
        issue["file_name"] = file_name
        issue["scope"] = (
            "record"
            if (issue.get("row") or 0) > 1
            else "structure"
            if issue["code"] in STRUCTURAL_ISSUES
            else "file"
        )

    error_count = sum(issue["severity"] == "error" for issue in issues)
    warning_count = sum(issue["severity"] == "warning" for issue in issues)
    summary = {
        "rows_read": len(imported),
        "valid_records": len(eligible_rows),
        "rejected_records": (
            len(imported) if structural_blocked else len(rejected_rows)
        ),
        "normalized_records": normalized["record_count"],
        "errors": error_count,
        "warnings": warning_count,
    }
    status = "validation_failed" if structural_blocked else "completed"
    result = {
        "execution_id": execution_id,
        "source": source,
        "file_name": file_name,
        "status": status,
        "blocking": structural_blocked,
        "summary": summary,
        "imported_records": imported,
        "issues": issues,
        "normalized_records": normalized_records,
        "processing": processing,
    }
    if prepare_commit is not None:
        prepare_commit(result)
    repository.commit_pipeline(execution_id, result)
    return result
