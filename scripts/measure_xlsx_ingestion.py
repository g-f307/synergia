"""Measure the XLSX ingestion path: duration, rows and peak memory per phase.

The script never prints cell values, file names inside the workbook or issue
details; only counts, durations and sizes. Run one workbook per process so the
resident-memory high-water mark belongs to that scenario.

Examples:
    python scripts/measure_xlsx_ingestion.py --synthetic-rows 50000 --columns 20
    INGESTION_ALLOWED_SHEETS="CTNR STATUS" python scripts/measure_xlsx_ingestion.py \
        planilha/arquivo.xlsx --source TMS
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import tempfile
import time
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
# Offline tool over local files chosen by the operator; set the variable to
# restrict the sheets (the service default authorizes none).
os.environ.setdefault("INGESTION_ALLOWED_SHEETS", "*")

from app.ingestion_budget import IngestionLimitError  # noqa: E402
from app.normalization import normalize_tables  # noqa: E402
from app.upload_security import (  # noqa: E402
    UnsafeUpload,
    inspect_content,
    policy_for,
)
from app.validation import read_tables, validate_tables  # noqa: E402


def _peak_rss() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def _synthetic_workbook(target: Path, rows: int, columns: int) -> None:
    from openpyxl import Workbook

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Dados")
    names = ["workorder", "status", "model", "lot"] + [
        f"campo_{index}" for index in range(max(columns - 4, 0))
    ]
    sheet.append(names[:columns])
    for index in range(rows):
        row = [f"WO-{index:08d}", "open", "MODELO-XYZ", f"LOT-{index % 997:04d}"]
        row += [f"valor-{index}-{column}" for column in range(columns - 4)]
        sheet.append(row[:columns])
    workbook.save(target)


def _phase(report: dict, name: str, started: float) -> None:
    report["phases"][name] = {
        "seconds": round(time.monotonic() - started, 2),
        "peak_rss_bytes": _peak_rss(),
    }


def measure(path: Path, source: str) -> dict:
    report: dict = {
        "source": source,
        "file_bytes": path.stat().st_size,
        "phases": {},
        "outcome": "completed",
    }
    with zipfile.ZipFile(path) as archive:
        report["uncompressed_bytes"] = sum(
            entry.file_size for entry in archive.infolist()
        )
    report["baseline_peak_rss_bytes"] = _peak_rss()
    try:
        started = time.monotonic()
        inspect_content(path, ".xlsx", policy_for(source))
        _phase(report, "admission", started)

        started = time.monotonic()
        tables, read_issues = read_tables(path, ".xlsx", source)
        _phase(report, "open", started)
        report["sheets"] = [sheet for sheet, _, _ in tables]

        started = time.monotonic()
        validation = validate_tables(tables, source, initial_issues=read_issues)
        _phase(report, "validation", started)
        report["rows_validated"] = validation["row_count"]
        report["issue_counts"] = dict(
            sorted(Counter(item["code"] for item in validation["issues"]).items())
        )

        started = time.monotonic()
        normalized = normalize_tables(tables, source)
        _phase(report, "normalization", started)
        report["records_normalized"] = normalized["record_count"]
    except UnsafeUpload as error:
        report.update(outcome="rejected_at_admission", reason_code=error.reason_code)
        if error.details:
            report["limit_details"] = {
                key: value
                for key, value in error.details.items()
                if key != "guidance"
            }
    except IngestionLimitError as error:
        report.update(outcome="rejected_while_reading", reason_code=error.code)
        report["limit_details"] = {
            key: value for key, value in error.details().items() if key != "guidance"
        }
    report["peak_rss_bytes"] = _peak_rss()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workbook", nargs="?", type=Path)
    parser.add_argument("--source", default="OWM")
    parser.add_argument("--synthetic-rows", type=int)
    parser.add_argument("--columns", type=int, default=12)
    arguments = parser.parse_args()
    if (arguments.workbook is None) == (arguments.synthetic_rows is None):
        parser.error("informe um arquivo ou --synthetic-rows")

    if arguments.workbook is not None:
        report = measure(arguments.workbook, arguments.source)
    else:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "sintetico.xlsx"
            _synthetic_workbook(target, arguments.synthetic_rows, arguments.columns)
            report = measure(target, arguments.source)
            report["synthetic"] = {
                "rows": arguments.synthetic_rows,
                "columns": arguments.columns,
            }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
