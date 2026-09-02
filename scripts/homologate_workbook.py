from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.execution import validate_transition  # noqa: E402
from app.normalization import normalize_column_name  # noqa: E402
from app.pipeline import read_source, run_pipeline_batch  # noqa: E402
from app.validation import validate_tables  # noqa: E402


class RecordingRepository:
    def __init__(self) -> None:
        self.state = "pending"

    def transition_execution(self, execution_id: str, target: str, reason: str) -> None:
        validate_transition(self.state, target)
        self.state = target

    def commit_pipeline(self, execution_id: str, result: dict[str, Any]) -> None:
        self.transition_execution(execution_id, result["status"], result["status"])


def _inventory(tables: list[tuple[str, list[str], list[list[Any]]]]) -> list[dict]:
    inventory = []
    for sheet, headers, rows in tables:
        populated = [
            row for row in rows if any(value not in (None, "") for value in row)
        ]
        types = {
            normalize_column_name(header): sorted(
                {
                    type(row[index]).__name__
                    for row in populated
                    if index < len(row) and row[index] not in (None, "")
                }
            )
            for index, header in enumerate(headers)
        }
        inventory.append(
            {
                "sheet": sheet,
                "header_row": (
                    getattr(rows[0], "row_number", 2) - 1 if rows else 1
                ),
                "columns": [normalize_column_name(value) for value in headers],
                "rows": len(populated),
                "types": types,
            }
        )
    return inventory


def homologate(
    workbook: Path,
    *,
    source: str = "GMES/OQC",
    companion_plan: Path | None = None,
) -> dict:
    tables, read_issues = read_source(workbook, workbook.suffix.lower(), source)
    validation = validate_tables(tables, source, initial_issues=read_issues)
    report: dict[str, Any] = {
        "contains_source_values": False,
        "source": source,
        "inventory": _inventory(tables),
        "validation": {
            "rows": validation["row_count"],
            "errors": validation["error_count"],
            "warnings": validation["warning_count"],
            "issue_counts": dict(
                sorted(Counter(item["code"] for item in validation["issues"]).items())
            ),
        },
    }
    if companion_plan is None:
        report["pipeline"] = {
            "executed": False,
            "reason": "companion_plan_not_provided",
        }
        return report

    plan_tables, plan_issues = read_source(
        companion_plan, companion_plan.suffix.lower(), "N-FP"
    )
    result = run_pipeline_batch(
        execution_id="homologation-local",
        inputs=[
            {
                "file_name": "companion-plan",
                "source": "N-FP",
                "source_file_id": 1,
                "tables": plan_tables,
                "read_issues": plan_issues,
            },
            {
                "file_name": "reference-workbook",
                "source": source,
                "source_file_id": 2,
                "tables": tables,
                "read_issues": read_issues,
            },
        ],
        repository=RecordingRepository(),
        classified_at="2026-09-01T00:00:00+00:00",
    )
    report["pipeline"] = {
        "executed": True,
        "status": result["status"],
        "summary": result["summary"],
        "processing": result["processing"]["summary"],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--source", default="GMES/OQC")
    parser.add_argument("--companion-plan", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = homologate(
        args.workbook,
        source=args.source,
        companion_plan=args.companion_plan,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
