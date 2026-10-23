from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_ingestion_validation.py"
CORPUS = ROOT / "data/synthetic/ingestion-v1"
sys.path.insert(0, str(ROOT))

from scripts.ingestion_corpus import execute, workorder  # noqa: E402


def run(*args, **overrides):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("INGESTION_", "UPLOAD_", "SYNERGIA_INGESTION_"))
    }
    env.update(overrides)
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )


def test_both_adapter_families_complete_volume_and_reject_each_budget(tmp_path):
    output = tmp_path / "report.json"
    process = run("--rows", 40, "--output", output)
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report == json.loads(output.read_text())
    assert report["passed"] is True
    assert len(report["runs"]) == 12
    assert report["environment"]["cpu_model"]
    assert report["environment"]["physical_memory_bytes"] > 0
    for case in report["runs"]:
        assert case["passed"]
        assert case["peak_rss_bytes"] >= case["baseline_peak_rss_bytes"] > 0
        assert case["duration_seconds"] > 0
        assert case["configuration"]["ingestion"]["max_memory_bytes"] > 0
    for forbidden in (
        "SYN-WO",
        "SYNTHETIC-RESTRICTED-CONTENT",
        "SYNTHETIC-DENIED-CONTENT",
    ):
        assert forbidden not in process.stdout + process.stderr


@pytest.mark.parametrize(
    "args,env",
    [
        (["--real-workbook", "private.xlsx", "--source", "Total Decision"], {}),
        (["--real-workbook", "private.xlsx", "--allow-real"], {}),
        (
            [
                "--real-workbook",
                "private.xlsx",
                "--source",
                "Total Decision",
                "--allow-real",
            ],
            {"CI": "true"},
        ),
        (["--worker", "private.xlsx", "--source", "Total Decision"], {}),
    ],
)
def test_real_files_require_explicit_opt_in_and_are_forbidden_in_ci(args, env):
    process = run(*args, **env)
    assert process.returncode == 2
    assert "Traceback" not in process.stderr


def test_opt_in_mode_emits_no_filename_hash_or_private_sheet_name(tmp_path):
    path = tmp_path / "PRIVATE-FILENAME.xlsx"
    content = (CORPUS / "td-additional.xlsx").read_bytes()
    path.write_bytes(content)
    process = run(
        "--real-workbook",
        path,
        "--source",
        "Total Decision",
        "--allow-real",
        CI="false",
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["input_kind"] == "restricted_opt_in"
    assert len(report["runs"]) == 1
    assert report["generated_rows_per_family"] is None
    for forbidden in (
        str(path),
        path.name,
        "SYNTHETIC-PRIVATE-SHEET",
        "SYN-WO",
        "sha256",
    ):
        assert forbidden not in process.stdout + process.stderr


def test_watchdog_is_a_failure_not_a_successful_budget_rejection():
    process = run("--rows", 4, "--source", "Total Decision", "--timeout", "0.000001")
    assert process.returncode == 1
    report = json.loads(process.stdout)
    assert not report["passed"]
    assert all(
        c["reason_code"] == "watchdog_timeout" and not c["passed"]
        for c in report["runs"]
    )


def test_volume_generator_does_not_invent_negative_container_quantities(tmp_path):
    path = tmp_path / "volume.xlsx"
    path.write_bytes(workorder(rows=160, tail=8)[0])
    report, _ = execute(path, "WO Status")
    container = next(s for s in report["sheets"] if s["sheet"] == "CTNR STATUS")
    assert container["normalized"] == 80
    assert container["rejected"] == 0
    assert "invalid_quantity" not in report["codes"]
