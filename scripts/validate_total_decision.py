"""Validate Total Decision without persistence; output only sanitized counts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.ingestion_budget import IngestionLimitError  # noqa: E402
from app.total_decision_report import build_report, compare_persisted  # noqa: E402
from app.upload_security import UnsafeUpload  # noqa: E402


def persisted_counts(database_url: str, execution_id: str, workbook: Path) -> dict:
    with workbook.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    with psycopg.connect(database_url) as connection:
        connection.read_only = True
        row = connection.execute(
            "SELECT id FROM synergia.source_files WHERE execution_id = %s "
            "AND source = 'Total Decision' AND content_hash = %s",
            (execution_id, digest),
        ).fetchone()
        if row is None:
            raise ValueError("Arquivo incompatível com a execução")
        counts = {}
        for kind, table in (
            ("imported", "imported_records"),
            ("normalized", "normalized_records"),
        ):
            for sheet, total in connection.execute(
                f"SELECT sheet_name, count(*) FROM synergia.{table} "
                "WHERE execution_id = %s AND source_file_id = %s "
                "GROUP BY sheet_name",
                (execution_id, row[0]),
            ):
                counts.setdefault(sheet, {"imported": 0, "normalized": 0})[kind] = total
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--execution-id")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.execution_id and not os.getenv("DATABASE_URL"):
        parser.error("--execution-id exige DATABASE_URL")
    try:
        report = build_report(args.workbook)
        if args.execution_id:
            report["persistence"] = compare_persisted(
                report,
                persisted_counts(
                    os.environ["DATABASE_URL"], args.execution_id, args.workbook
                ),
            )
    except (IngestionLimitError, UnsafeUpload) as exc:
        report = {
            "contains_source_values": False,
            "blocking": True,
            "error_code": getattr(exc, "code", None)
            or getattr(exc, "reason_code", "validation_failed"),
        }
    except (OSError, ValueError, psycopg.Error):
        report = {
            "contains_source_values": False,
            "blocking": True,
            "error_code": "validation_failed",
        }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return int(
        bool(
            report["blocking"]
            or (
                args.strict
                and (
                    not report.get("balanced", False)
                    or not report.get("persistence", {"matches": True})["matches"]
                )
            )
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
