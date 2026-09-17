from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_performance_evidence_index import (  # noqa: E402
    _benchmark,
    _junit,
    _manifest,
    _run,
    build,
)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture_run(directory: Path, *, passed: bool = True) -> None:
    directory.mkdir()
    _write_json(
        directory / "environment.json",
        {
            "host": {"memory_total_bytes": 1000},
            "metadata": {"postgres_limits": "test"},
            "mass": {"logical_digest": "abc", "entities": {"serials": 1}},
        },
    )
    _write_json(directory / "workload.json", {"run_id": directory.name})
    _write_json(
        directory / "summary.json",
        {"measured_samples": 1, "resources": {"postgres": {"db_connections_max": 1}}},
    )
    _write_json(
        directory / "correctness.json",
        {"checks": [{"check": "serial-count", "passed": passed}]},
    )
    (directory / "samples.csv").write_text("operation,duration_ms\nread,1\n")
    (directory / "resources.csv").write_text("cpu_pct\n1\n")


def test_run_indexes_mass_environment_hashes_and_diagnostic_failures(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "run"
    _fixture_run(directory, passed=False)
    result = _run(directory, tmp_path)
    assert result["classification"] == "diagnostic"
    assert result["failed_checks"] == ["serial-count"]
    assert result["environment"]["mass"]["logical_digest"] == "abc"
    assert result["resources"]["postgres"]["db_connections_max"] == 1
    assert len(result["files"]["samples.csv"]["sha256"]) == 64


def test_run_rejects_missing_mass_and_required_files(tmp_path: Path) -> None:
    directory = tmp_path / "run"
    _fixture_run(directory)
    (directory / "samples.csv").unlink()
    with pytest.raises(ValueError, match="sem arquivos"):
        _run(directory, tmp_path)
    (directory / "samples.csv").write_text("operation,duration_ms\n")
    _write_json(directory / "environment.json", {"host": {}, "metadata": {}})
    with pytest.raises(ValueError, match="sem massa"):
        _run(directory, tmp_path)


def test_junit_records_failure_without_claiming_pass(tmp_path: Path) -> None:
    path = tmp_path / "tests.xml"
    path.write_text('<testsuite tests="2" failures="1" errors="0"/>')
    result = _junit(path, tmp_path)
    assert result["tests"] == 2
    assert result["passed"] is False
    assert len(result["sha256"]) == 64


def test_benchmark_rejects_rows_persisted_by_write_probe(tmp_path: Path) -> None:
    directory = tmp_path / "probe"
    directory.mkdir()
    _write_json(
        directory / "run.json",
        {
            "rule_evaluations_before": 1,
            "rule_evaluations_after": 2,
            "read": {"digest": "same"},
            "write": {"samples": [1]},
        },
    )
    with pytest.raises(ValueError, match="deixou avaliações"):
        _benchmark(directory, tmp_path)


def test_manifest_checks_source_hash_without_claiming_processing(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "mass"
    directory.mkdir()
    source = directory / "serials.csv"
    source.write_text("serial\nSYN-001\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    _write_json(
        directory / "manifest.json",
        {
            "logical_digest": "abc",
            "entities": {"serials": 1},
            "files": [
                {
                    "file": source.name,
                    "size_bytes": source.stat().st_size,
                    "sha256": digest,
                }
            ],
        },
    )
    result = _manifest(directory / "manifest.json", tmp_path)
    assert result["classification"] == "generated_only_not_processed"
    source.write_text("serial\nCHANGED\n")
    with pytest.raises(ValueError, match="Fonte alterada"):
        _manifest(directory / "manifest.json", tmp_path)


def test_build_refuses_overwrite_and_marks_baseline_non_comparable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / "run"
    _fixture_run(directory)
    output = tmp_path / "index.json"
    args = argparse.Namespace(
        run=[directory],
        junit=[],
        plan_run=[],
        benchmark_run=[],
        manifest=[],
        output=output,
    )
    result = build(args)
    assert result["summary"]["exploratory_pass_runs"] == 1
    assert result["baseline_status"] == "exploratory_non_comparable"
    assert result["release_candidate_status"] == "not_approved"
    with pytest.raises(ValueError, match="já existe"):
        build(args)
