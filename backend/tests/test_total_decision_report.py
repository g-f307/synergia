import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.total_decision_report import build_report, compare_persisted

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.generate_total_decision_fixture import (  # noqa: E402
    SENSITIVE_SENTINEL,
    build_workbook,
)


@pytest.fixture
def workbook(tmp_path):
    path = tmp_path / "private-filename.xlsx"
    path.write_bytes(build_workbook(edge=True))
    return path


def test_count_only_report_balances_and_never_contains_source_values(workbook):
    report = build_report(workbook)
    sheet = report["sheets"][0]
    assert report["balanced"] is True
    assert report["summary_rows_excluded"] == [3]
    assert (
        sheet["read"],
        sheet["imported"],
        sheet["normalized"],
        sheet["rejected"],
    ) == (
        4,
        4,
        1,
        3,
    )
    text = json.dumps(report)
    for forbidden in (SENSITIVE_SENTINEL, "SYN-WO", "private-filename", "SOURCE-SYN"):
        assert forbidden not in text


def test_reconciliation_detects_differences(workbook):
    report = build_report(workbook)
    expected = {"Sheet1": {"imported": 4, "normalized": 1}}
    assert compare_persisted(report, expected)["matches"] is True
    assert compare_persisted(report, {})["matches"] is False
    expected["unexpected"] = {"imported": 1, "normalized": 1}
    assert compare_persisted(report, expected)["matches"] is False


def test_cli_runs_without_pythonpath_and_requires_db_for_comparison(workbook):
    script = ROOT / "scripts/validate_total_decision.py"
    process = subprocess.run(
        [sys.executable, "-I", str(script), str(workbook), "--strict"],
        capture_output=True,
        text=True,
        env={"PATH": ""},
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["balanced"] is True
    assert SENSITIVE_SENTINEL not in process.stdout + process.stderr
    process = subprocess.run(
        [sys.executable, "-I", str(script), str(workbook), "--execution-id", "syn"],
        capture_output=True,
        text=True,
        env={"PATH": ""},
    )
    assert process.returncode == 2
    assert "DATABASE_URL" in process.stderr


def test_strict_cli_reports_drift_and_unreadable_files_without_values(workbook):
    from openpyxl import load_workbook

    book = load_workbook(workbook)
    book.active["AK1"] = "WRONG-PRIVATE-HEADER"
    book.save(workbook)
    script = ROOT / "scripts/validate_total_decision.py"
    for content in (None, b"invalid workbook"):
        if content is not None:
            workbook.write_bytes(content)
        process = subprocess.run(
            [sys.executable, "-I", str(script), str(workbook), "--strict"],
            capture_output=True,
            text=True,
        )
        assert process.returncode == 1
        assert json.loads(process.stdout)["blocking"] is True
        assert "WRONG-PRIVATE-HEADER" not in process.stdout
