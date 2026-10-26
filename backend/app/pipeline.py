from __future__ import annotations

import json
import logging
from collections.abc import Callable, Collection
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from app.ingestion_budget import LIMIT_GUIDANCE, IngestionBudget, IngestionLimitError
from app.normalization import normalize_column_name, normalize_tables
from app.observability.metrics import observe_ingestion
from app.observability.telemetry import safe_log
from app.processing import process_normalized_records
from app.spreadsheet_reader import IngestionRun, LazySheetRows
from app.total_decision import TotalDecisionImporter, expand_total_decision
from app.total_decision_spec import SOURCE as TOTAL_DECISION_SOURCE
from app.validation import (
    DataReadError,
    failed_validation_report,
    read_tables,
    validate_tables,
)
from app.wo_status import WoStatusImporter, expand_composite, is_composite

STRUCTURAL_ISSUES = {
    "contract_drift",
    "empty_file",
    "empty_sheet",
    "invalid_header",
    "invalid_structure",
    "missing_column",
    "read_error",
    "validation_read_error",
}
RULE_DETAIL_DEFER_THRESHOLD = 50_000


class PipelineRepository(Protocol):
    def commit_pipeline(self, execution_id: str, result: dict[str, Any]) -> None: ...

    def transition_execution(
        self, execution_id: str, target: str, reason: str
    ) -> None: ...


class SourceImporter(Protocol):
    def read(
        self, path: Path, extension: str, source: str
    ) -> tuple[list[tuple[str, list[str], list[list[Any]]]], list[dict[str, Any]]]: ...


class TabularSourceImporter:
    def read(
        self, path: Path, extension: str, source: str
    ) -> tuple[list[tuple[str, list[str], list[list[Any]]]], list[dict[str, Any]]]:
        return read_tables(path, extension, source)


IMPORTERS: dict[str, SourceImporter] = {
    source: TabularSourceImporter() for source in ("N-FP", "OWM", "GMES/OQC", "TMS")
}
IMPORTERS["WO Status"] = WoStatusImporter()
IMPORTERS[TOTAL_DECISION_SOURCE] = TotalDecisionImporter()


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
        return importer.read(path, extension, source)
    except IngestionLimitError:
        raise
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


def _run_of(tables: list[Any]) -> IngestionRun | None:
    """Find the shared ingestion run behind lazily read worksheets, if any."""
    for _, _, rows in tables:
        if isinstance(rows, LazySheetRows):
            return rows.run
    return None


def _record_ingestion(
    run: IngestionRun,
    *,
    outcome: str,
    rows_processed: int,
    rows_rejected: int,
    duration: float,
    reason: str | None = None,
) -> None:
    peak = observe_ingestion(
        outcome=outcome,
        duration_seconds=duration,
        rows_processed=rows_processed,
        rows_rejected=rows_rejected,
        reason=reason,
        allowed_reasons=frozenset(LIMIT_GUIDANCE),
        memory_budget_bytes=run.budget.max_memory_bytes,
    )
    safe_log(
        logging.INFO if outcome == "completed" else logging.WARNING,
        f"ingestion.{outcome}",
        source=run.source,
        reason_code=reason,
        processed_count=rows_processed,
        rejected_count=rows_rejected,
        duration_ms=int(duration * 1000),
        peak_memory_bytes=peak,
    )


def _record_execution(
    stats: list[dict[str, Any]], outcome: str, reason: str | None = None
) -> None:
    """Record every file of an execution under the execution's terminal outcome.

    Each file keeps the duration captured when its own phase ended, so later
    files and the consolidation never inflate it. The rejection reason is
    counted once per execution.
    """
    for position, stat in enumerate(stats):
        meter: IngestionRun = stat["meter"]
        duration = stat["duration"]
        _record_ingestion(
            meter,
            outcome=outcome,
            rows_processed=stat["rows"],
            rows_rejected=stat["rejected"],
            duration=(
                meter.clock.elapsed - stat["offset"] if duration is None else duration
            ),
            reason=reason if position == 0 else None,
        )


def _check_issue_total(budget: IngestionBudget, issues: list[dict[str, Any]]) -> None:
    if len(issues) > budget.max_issues:
        raise IngestionLimitError(
            "ingestion_issue_limit", limit=budget.max_issues, observed=len(issues)
        )


def _check_execution_memory(
    budget: IngestionBudget, rows: int, cells: int, *, final: bool
) -> None:
    estimate = (
        budget.estimated_memory(rows, cells)
        if final
        else budget.minimum_memory(rows, cells)
    )
    if estimate > budget.max_memory_bytes:
        raise IngestionLimitError(
            "workbook_memory_limit", limit=budget.max_memory_bytes, observed=estimate
        )


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
            row_number = getattr(row, "row_number", row_number)
            # An adapter rejects some rows without values (a blocked sheet, a gap
            # in the active region); they still count as read, with their row.
            if not getattr(row, "adapter_issues", None) and not any(
                value not in (None, "") for value in row
            ):
                continue
            records.append(
                {
                    "source": source,
                    "sheet": sheet,
                    "row": row_number,
                    "original_values": {
                        field: (
                            _original_value(getattr(row, "original_values", row)[index])
                            if index < len(row)
                            else None
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
    source_file_id: int,
    classified_at: str,
    known_organizations: Collection[str] | None = None,
    prepare_commit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Import, validate and normalize one stored file, then commit atomically."""
    return run_pipeline_batch(
        execution_id=execution_id,
        inputs=[
            {
                "file_name": file_name,
                "source": source,
                "source_file_id": source_file_id,
                "tables": tables,
                "read_issues": read_issues,
            }
        ],
        repository=repository,
        classified_at=classified_at,
        known_organizations=known_organizations,
        prepare_commit=prepare_commit,
    )


def run_pipeline_batch(
    *,
    execution_id: str,
    inputs: list[dict[str, Any]],
    repository: PipelineRepository,
    classified_at: str,
    known_organizations: Collection[str] | None = None,
    prepare_commit: Callable[[dict[str, Any]], None] | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Process every source file from one execution without rereading originals."""
    stats: list[dict[str, Any]] = []
    try:
        result = _run_pipeline_batch(
            execution_id=execution_id,
            inputs=inputs,
            repository=repository,
            classified_at=classified_at,
            known_organizations=known_organizations,
            prepare_commit=prepare_commit,
            resume=resume,
            stats=stats,
        )
    except IngestionLimitError as exc:
        _record_execution(stats, "rejected", exc.code)
        exc.recorded = True
        raise
    except Exception:
        _record_execution(stats, "failed")
        raise
    _record_execution(stats, "completed")
    return result


def _run_pipeline_batch(
    *,
    execution_id: str,
    inputs: list[dict[str, Any]],
    repository: PipelineRepository,
    classified_at: str,
    known_organizations: Collection[str] | None,
    prepare_commit: Callable[[dict[str, Any]], None] | None,
    resume: bool,
    stats: list[dict[str, Any]],
) -> dict[str, Any]:
    # A composite upload becomes one input per authorized sheet, each with its
    # logical source, so the usual per-source flow applies unchanged.
    inputs = [
        sub
        for item in inputs
        for sub in (
            expand_composite(item)
            if is_composite(str(item["source"]))
            else [expand_total_decision(item)]
            if item["source"] == TOTAL_DECISION_SOURCE
            else [item]
        )
    ]
    if not resume:
        repository.transition_execution(execution_id, "validating", "pipeline_started")
    imported_records: list[dict[str, Any]] = []
    normalized_records: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    blocked_files: set[int] = set()
    # A composite upload isolates a structural failure to its sheet.
    blocked_sheets: set[tuple[int, str | None]] = set()
    valid_records = 0
    rejected_records = 0
    lazy_budgets: list[IngestionBudget] = []
    held_rows = 0
    held_cells = 0
    # One time window for the whole execution, shared by every sheet and by the
    # consolidation, bounded by the most restrictive source.
    runs = [run for item in inputs if (run := _run_of(item["tables"])) is not None]
    execution_clock = (
        IngestionBudget.most_restrictive([run.budget for run in runs]).start()
        if runs
        else None
    )

    for item in inputs:
        source = str(item["source"])
        file_name = str(item["file_name"])
        source_file_id = int(item["source_file_id"])
        tables = item["tables"]
        run = _run_of(tables)
        # CSV and JSON have no lazy sheets or budget, but are still measured.
        meter = run or IngestionRun(source)
        stat: dict[str, Any] = {
            "meter": meter,
            "rows": 0,
            "rejected": 0,
            "duration": None,
            "offset": 0.0,
        }
        stats.append(stat)
        if run is not None:
            lazy_budgets.append(run.budget)
        max_issues = run.budget.max_issues if run is not None else None
        if run is not None and execution_clock is not None:
            run.attach(execution_clock)
            stat["offset"] = execution_clock.elapsed
            run.begin("validating")
        validation = validate_tables(
            tables,
            source,
            known_organizations,
            item["read_issues"],
            max_issues,
            item.get("schema"),
        )
        if run is not None:
            run.begin("importing")
        imported = [
            {
                **record,
                "execution_id": execution_id,
                "source_file_id": source_file_id,
                "file_name": file_name,
            }
            for record in _imported_records(tables, source)
        ]
        file_issues = validation["issues"]
        structural_blocked = any(
            issue["severity"] == "error" and issue["code"] in STRUCTURAL_ISSUES
            for issue in file_issues
        )
        if structural_blocked and item.get("schema") is not None:
            blocked_sheets.add((source_file_id, tables[0][0] if tables else None))
        elif structural_blocked:
            blocked_files.add(source_file_id)
        rejected_rows = {
            (issue["sheet"], issue["row"])
            for issue in file_issues
            if issue["severity"] == "error" and (issue.get("row") or 0) > 1
        }
        eligible_rows = (
            set()
            if structural_blocked
            else {(record["sheet"], record["row"]) for record in imported}
            - rejected_rows
        )
        if run is not None:
            run.begin("normalizing")
        normalized = normalize_tables(tables, source, eligible_rows, max_issues)
        normalized_records.extend(
            {
                **record,
                "execution_id": execution_id,
                "source_file_id": source_file_id,
                "file_name": file_name,
            }
            for record in normalized["records"]
        )
        for issue in [*file_issues, *normalized["issues"]]:
            issue["file_name"] = file_name
            issue["source"] = source
            issue["source_file_id"] = source_file_id
            issue["scope"] = (
                "record"
                if (issue.get("row") or 0) > 1
                else "structure"
                if issue["code"] in STRUCTURAL_ISSUES
                else "file"
            )
            issues.append(issue)
        if lazy_budgets:
            # Issues accumulate across files, so the limit is the most restrictive
            # one among the sources seen so far (and again over all of them below).
            _check_issue_total(IngestionBudget.most_restrictive(lazy_budgets), issues)
        imported_records.extend(imported)
        valid_records += len(eligible_rows)
        file_rejected = len(imported) if structural_blocked else len(rejected_rows)
        rejected_records += file_rejected
        stat["rows"] = len(imported)
        stat["rejected"] = file_rejected
        stat["duration"] = meter.clock.elapsed - stat["offset"]
        # Every file of the execution accumulates in the same lists, so the
        # budget is also checked on the running totals; only the cheapest
        # regime is known to apply until the normalized count is final.
        held_rows += len(imported)
        held_cells += sum(len(record["original_values"]) for record in imported)
        if lazy_budgets:
            _check_execution_memory(
                IngestionBudget.most_restrictive(lazy_budgets),
                held_rows,
                held_cells,
                final=False,
            )
        # The normalized/imported representations are now authoritative. Drop
        # the lazy table handles before the next phase; no pass keeps a copy of
        # the parsed worksheet.
        item["tables"] = []

    # The budgets of every source in the execution apply together, so the result
    # does not depend on the order of the files.
    aggregate = IngestionBudget.most_restrictive(lazy_budgets) if lazy_budgets else None
    if aggregate is not None:
        _check_issue_total(aggregate, issues)
        # ``defer_rule_details`` below depends on the normalized count of the
        # whole execution, which is only known now; the estimate uses that same
        # cardinality and covers every file accumulated in the execution.
        _check_execution_memory(
            aggregate,
            len(normalized_records),
            sum(len(record["values"]) for record in normalized_records),
            final=True,
        )

    checkpoint = execution_clock.check if execution_clock is not None else None
    nothing_usable = bool(blocked_files or blocked_sheets) and not normalized_records
    if nothing_usable:
        processing = process_normalized_records(
            normalized_records,
            execution_id=execution_id,
            classified_at=classified_at,
        )
    else:
        if not resume:
            repository.transition_execution(
                execution_id, "normalizing", "validation_completed"
            )
            repository.transition_execution(
                execution_id, "consolidating", "normalization_completed"
            )
        processing = process_normalized_records(
            normalized_records,
            execution_id=execution_id,
            classified_at=classified_at,
            defer_rule_details=(len(normalized_records) >= RULE_DETAIL_DEFER_THRESHOLD),
            checkpoint=checkpoint,
            on_consolidated=(
                None
                if resume
                else lambda: repository.transition_execution(
                    execution_id, "applying_rules", "consolidation_completed"
                )
            ),
        )
    error_count = sum(issue["severity"] == "error" for issue in issues)
    warning_count = sum(issue["severity"] == "warning" for issue in issues)
    summary = {
        "rows_read": len(imported_records),
        "valid_records": valid_records,
        "rejected_records": rejected_records,
        "normalized_records": len(normalized_records),
        "errors": error_count,
        "warnings": warning_count,
    }
    status = (
        "validation_failed"
        if nothing_usable
        else "completed_with_errors"
        if error_count or processing["summary"]["failed_workorders"]
        else "completed"
    )
    sources = list(dict.fromkeys(str(item["source"]) for item in inputs))
    file_names = list(dict.fromkeys(str(item["file_name"]) for item in inputs))
    result = {
        "execution_id": execution_id,
        "source": sources[0],
        "sources": sources,
        "file_name": file_names[0],
        "file_names": file_names,
        "status": status,
        "blocking": bool(blocked_files) or nothing_usable,
        "blocked_source_file_ids": sorted(blocked_files),
        "blocked_sheets": [
            {"source_file_id": file_id, "sheet": sheet}
            for file_id, sheet in sorted(blocked_sheets, key=str)
        ],
        "summary": summary,
        "imported_records": imported_records,
        "issues": issues,
        "normalized_records": normalized_records,
        "processing": processing,
    }
    if prepare_commit is not None:
        prepare_commit(result)
    repository.commit_pipeline(execution_id, result)
    return result
