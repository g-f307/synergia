"""Validate a WO Status workbook with the adapters, without persisting anything.

Prints a reconciliation report with counts per authorized sheet (read, ignored,
rejected, duplicated, normalized). It never prints cell values. With
``--execution-id`` it also compares those counts with what an execution
persisted, using read-only queries.

    python scripts/validate_wo_status.py arquivo.xlsx
    DATABASE_URL=... python scripts/validate_wo_status.py arquivo.xlsx \
        --execution-id <id>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.wo_status_report import build_report, compare_persisted  # noqa: E402


def _persisted_counts(database_url: str, execution_id: str) -> dict[str, dict]:
    import psycopg

    counts: dict[str, dict[str, int]] = {}
    with psycopg.connect(database_url) as connection:
        connection.read_only = True
        for kind, table in (
            ("imported", "imported_records"),
            ("normalized", "normalized_records"),
        ):
            for sheet, total in connection.execute(
                f"SELECT sheet_name, count(*) FROM synergia.{table} "
                "WHERE execution_id = %s GROUP BY sheet_name",
                (execution_id,),
            ):
                counts.setdefault(sheet, {"imported": 0, "normalized": 0})[kind] = total
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--execution-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="falha se houver deriva de contrato, desequilíbrio ou divergência",
    )
    arguments = parser.parse_args()
    report = build_report(arguments.workbook)
    if arguments.execution_id:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            parser.error("--execution-id exige DATABASE_URL")
        report["persistence"] = compare_persisted(
            report, _persisted_counts(database_url, arguments.execution_id)
        )
    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    if arguments.output:
        arguments.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    if not arguments.strict:
        return 0
    failed = (
        report["blocking"]
        or not report["balanced"]
        or not report.get("persistence", {"matches": True})["matches"]
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
