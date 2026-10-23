from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.execution import validate_transition
from app.pipeline import read_source, run_pipeline_batch
from app.wo_status_spec import COMPOSITE_SOURCE, load_spec

DUPLICATE_CODES = frozenset({"duplicate_row", "duplicate_serial"})
IGNORED_STATS = ("ignored_blank", "ignored_tail", "ignored_non_substantive")
PLACEHOLDER_STATS = ("rejected_gap", "rejected_blocked")


class _ValidationOnlyRepository:
    """Follows the state machine without persisting anything."""

    def __init__(self) -> None:
        self.state = "pending"

    def transition_execution(self, execution_id: str, target: str, reason: str) -> None:
        validate_transition(self.state, target)
        self.state = target

    def commit_pipeline(self, execution_id: str, result: dict[str, Any]) -> None:
        self.transition_execution(execution_id, result["status"], result["status"])


def _rows(issues: list[dict[str, Any]], sheet: str, *, errors_only: bool) -> set[int]:
    return {
        issue["row"]
        for issue in issues
        if issue.get("sheet") == sheet
        and (issue.get("row") or 0) > 1
        and (not errors_only or issue["severity"] == "error")
    }


def build_report(workbook: Path, *, execution_id: str = "validacao-sem-persistencia"):
    """Run the WO Status adapters and the pipeline without persisting anything.

    The report holds counts, codes and row numbers only; no cell value, so it
    can be attached to evidence.
    """
    spec = load_spec()
    digest = hashlib.sha256(workbook.read_bytes()).hexdigest()
    tables, read_issues = read_source(workbook, ".xlsx", COMPOSITE_SOURCE)
    repository = _ValidationOnlyRepository()
    result = run_pipeline_batch(
        execution_id=execution_id,
        inputs=[
            {
                "file_name": workbook.name,
                "source": COMPOSITE_SOURCE,
                "source_file_id": 0,
                "tables": list(tables),
                "read_issues": read_issues,
            }
        ],
        repository=repository,
        classified_at=datetime.now(UTC).isoformat(),
    )
    issues = result["issues"]
    normalized = Counter(record["sheet"] for record in result["normalized_records"])
    imported = Counter(record["sheet"] for record in result["imported_records"])
    sheet_codes = {
        sheet: {item["code"] for item in issues if item.get("sheet") == sheet}
        for sheet in {item.get("sheet") for item in issues}
    }
    by_name = {sheet: rows for sheet, _, rows in tables}
    sheets = []
    for sheet in spec.sheets:
        codes = sheet_codes.get(sheet.name, set())
        rows = by_name.get(sheet.name)
        stats = getattr(rows, "stats", Counter())
        if rows is None:
            status = "missing" if "sheet_missing" in codes else "not_authorized"
        elif "contract_drift" in codes:
            status = "drift"
        elif sheet.blocked:
            status = "blocked"
        else:
            status = "ingested"
        ignored = sum(stats[name] for name in IGNORED_STATS)
        placeholders = sum(stats[name] for name in PLACEHOLDER_STATS)
        passed = stats["emitted"] + placeholders
        rejected_rows = _rows(issues, sheet.name, errors_only=True)
        duplicated = {
            item["row"]
            for item in issues
            if item.get("sheet") == sheet.name and item["code"] in DUPLICATE_CODES
        }
        sheets.append(
            {
                "sheet": sheet.name,
                "logical_source": sheet.logical_source,
                "status": status,
                "blocked_reason": sheet.blocked,
                "read": stats["scanned"],
                "ignored": {name: stats[name] for name in IGNORED_STATS},
                "ignored_total": ignored,
                "entered_validation": passed,
                "rejected": len(rejected_rows),
                "duplicated": len(duplicated),
                "imported": imported[sheet.name],
                "normalized": normalized[sheet.name],
                "balanced": (
                    stats["scanned"] == ignored + passed
                    and passed == normalized[sheet.name] + len(rejected_rows)
                )
                if rows is not None and status in {"ingested", "blocked"}
                else None,
                "issue_codes": dict(
                    sorted(
                        Counter(
                            item["code"]
                            for item in issues
                            if item.get("sheet") == sheet.name
                        ).items()
                    )
                ),
            }
        )
    ignored_sheets = sorted(
        item["sheet"] for item in issues if item["code"] == "sheet_ignored"
    )
    return {
        "contains_source_values": False,
        "adapter": spec.label,
        "contract_version": spec.contract_version,
        "file": {
            "name": workbook.name,
            "size_bytes": workbook.stat().st_size,
            "sha256": digest,
        },
        "status": result["status"],
        "blocking": result["blocking"] or bool(result["blocked_sheets"]),
        "summary": result["summary"],
        "sheets": sheets,
        "ignored_sheets": ignored_sheets,
        "balanced": all(sheet["balanced"] is not False for sheet in sheets),
    }


def compare_persisted(
    report: dict[str, Any], persisted: dict[str, dict[str, int]]
) -> dict[str, Any]:
    """Compare the expected per-sheet counts with what was persisted."""
    differences = []
    for sheet in report["sheets"]:
        actual = persisted.get(sheet["sheet"], {"imported": 0, "normalized": 0})
        for kind in ("imported", "normalized"):
            if actual.get(kind, 0) != sheet[kind]:
                differences.append(
                    {
                        "sheet": sheet["sheet"],
                        "kind": kind,
                        "expected": sheet[kind],
                        "persisted": actual.get(kind, 0),
                    }
                )
    known = {sheet["sheet"] for sheet in report["sheets"]}
    differences.extend(
        {"sheet": sheet, "kind": "unexpected_sheet", "persisted": counts}
        for sheet, counts in sorted(persisted.items())
        if sheet not in known and any(counts.values())
    )
    return {"matches": not differences, "differences": differences}
