"""Testes do runner de campanha, falhas, pin e microbenchmark p95 da #192."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


def test_ci_fake_campaign_runner_preserves_runs_and_raw_bytes(tmp_path):
    from run_ai_assistance_campaign import nearest_rank_p95, run_campaign

    assert nearest_rank_p95([float(i) for i in range(1, 31)]) == 29.0

    report1 = run_campaign(mode="ci-fake", output_dir=tmp_path)
    report2 = run_campaign(mode="ci-fake", output_dir=tmp_path)
    assert report1["run_id"] != report2["run_id"]
    assert Path(report1["run_dir"]).is_dir()
    assert Path(report2["run_dir"]).is_dir()

    assert report1["overall_passed"] is True
    assert report1["freeze_verified_start"] is True
    assert report1["freeze_verified_end"] is True
    assert len(report1["cases"]) == 30

    insufficient = [c for c in report1["cases"] if c["sufficiency"] == "insufficient"]
    assert len(insufficient) >= 2
    for item in insufficient:
        assert item["generation_ms"] is None
        assert item["inference_applicable"] is False
        assert item["provider_calls"] == 0
        assert item["state"] == "insufficient_evidence"

    sufficient = [c for c in report1["cases"] if c["sufficiency"] == "sufficient"]
    for item in sufficient:
        assert item["provider_calls"] == 1
        assert item["raw_response_bytes"] is not None
        assert (Path(report1["run_dir"]) / "raw" / f"{item['case_id']}.bin").is_file()

    p95 = report1["microbenchmark_non_inference_p95"]
    assert p95["covers_db_auth_persistence"] is False
    assert p95["warmups"] == 5
    assert p95["sample_count"] == 30
    assert p95["p95_ms"]["microbenchmark_total"] < 1000.0

    gates = report1["gates"]
    assert gates["valid_references"]["passed"] is True
    assert gates["no_external_facts"]["passed"] is True
    assert gates["no_unavailable_on_sufficient"]["passed"] is True
    assert gates["inference_completed"]["passed"] is True
    assert gates["freeze_unchanged"]["passed"] is True

    run_dir = Path(report1["run_dir"])
    assert (run_dir / "ci-fake-report.json").is_file()
    assert (run_dir / "manifest-hashes.json").is_file()


def test_real_campaign_fails_nonzero_when_runtime_unreachable(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_ai_assistance_campaign.py"),
            "--mode",
            "real",
            "--endpoint",
            "http://127.0.0.1:1",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["overall_passed"] is False
    assert summary["gates"]["no_unavailable_on_sufficient"]["passed"] is False
    assert summary["gates"]["inference_completed"]["passed"] is False
    run_dir = Path(summary["run_dir"])
    assert (run_dir / "real-qwen-report.json").is_file()


def test_real_campaign_refuses_mismatched_env_model_or_digest(tmp_path, monkeypatch):
    from run_ai_assistance_campaign import run_campaign

    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_MODEL", "other-model:1b")
    with pytest.raises(ValueError, match="Modelo ou digest"):
        run_campaign(mode="real", output_dir=tmp_path)


def test_validate_delivered_output_rejects_invented_id_and_prohibited_phrase():
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from generate_ai_assistance_corpus import build_case_context
    from run_ai_assistance_campaign import validate_delivered_output

    ctx = build_case_context(
        ROOT / "data" / "synthetic" / "ai-assistance-v1" / "cases" / "AA-01.json"
    )
    ext_id = "11111111-1111-4111-8111-111111111111"
    bad = SimpleNamespace(
        state="ready",
        origin="model",
        summary=f"O sistema decidiu devido a erro externo {ext_id}.",
        findings=[],
        human_checks=[],
        limitations=["Limitação registrada."],
        context_sha256=ctx.context_sha256,
        prompt_sha256="0" * 64,
        model="qwen3:4b-instruct",
        digest="sha256:" + "0" * 64,
        elapsed_ms=10,
        created_at=datetime.now(UTC),
    )
    refs_ok, no_ext, reason = validate_delivered_output(
        result=bad,
        context=ctx,
        forbidden_org_ids=set(),
        context_ms=1,
    )
    assert no_ext is False
    assert reason is not None

    invented_no_uuid = SimpleNamespace(
        state="ready",
        origin="model",
        summary="O lote quarenta e dois apresentou divergência inventada.",
        findings=[],
        human_checks=[],
        limitations=["Limitação registrada."],
        context_sha256=ctx.context_sha256,
        prompt_sha256="0" * 64,
        model="qwen3:4b-instruct",
        digest="sha256:" + "0" * 64,
        elapsed_ms=10,
        created_at=datetime.now(UTC),
    )
    _, no_ext_2, reason_2 = validate_delivered_output(
        result=invented_no_uuid,
        context=ctx,
        forbidden_org_ids=set(),
        context_ms=1,
    )
    assert no_ext_2 is False
    assert reason_2 is not None
