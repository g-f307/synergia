"""Count-only validation and reconciliation. No source value is returned."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.pipeline import read_source, run_pipeline_batch
from app.total_decision_spec import SOURCE, load_spec
from app.upload_security import UnsafeUpload, inspect_content, policy_for
from app.wo_status_report import _ValidationOnlyRepository, compare_persisted

__all__ = ["build_report", "compare_persisted"]


def build_report(workbook: Path) -> dict:
    policy = policy_for(SOURCE)
    size = workbook.stat().st_size
    if size > policy.max_bytes:
        raise UnsafeUpload("file_too_large")
    inspect_content(workbook, ".xlsx", policy)
    tables, issues = read_source(workbook, ".xlsx", SOURCE)
    result = run_pipeline_batch(
        execution_id="validation-only",
        inputs=[
            {
                "file_name": "workbook.xlsx",
                "source": SOURCE,
                "source_file_id": 0,
                "tables": tables,
                "read_issues": issues,
            }
        ],
        repository=_ValidationOnlyRepository(),
        classified_at=datetime.now(UTC).isoformat(),
    )
    spec = load_spec()
    stats = getattr(tables[0][2], "stats", Counter()) if tables else Counter()
    rejected = {
        i["row"]
        for i in result["issues"]
        if i["severity"] == "error" and (i.get("row") or 0) >= 4
    }
    duplicates = {i["row"] for i in result["issues"] if i["code"] == "duplicate_row"}
    imported = len(result["imported_records"])
    normalized = len(result["normalized_records"])
    ignored = stats["ignored_blank"]
    sheet = {
        "sheet": spec.sheet.name,
        "logical_source": "GMES/OQC",
        "read": stats["scanned"],
        "ignored_total": ignored,
        "entered_validation": imported,
        "rejected": len(rejected),
        "duplicated": len(duplicates),
        "imported": imported,
        "normalized": normalized,
        "balanced": stats["scanned"] == ignored + imported
        and imported == normalized + len(rejected),
        "codes": dict(sorted(Counter(i["code"] for i in result["issues"]).items())),
    }
    blocking = result["blocking"] or bool(result["blocked_sheets"])
    return {
        "contains_source_values": False,
        "adapter": spec.label,
        "contract_version": spec.contract_version,
        "source": SOURCE,
        "status": result["status"],
        "blocking": blocking,
        "summary_rows_excluded": list(spec.summary_rows),
        "sheets": [sheet],
        "balanced": sheet["balanced"],
    }
