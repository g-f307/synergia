"""Synthetic regressions for factual grouping, controlled prose and isolation."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import ai_quality_explanation as quality  # noqa: E402
import render_ai_quality_explanation as renderer  # noqa: E402
import run_ai_quality_explanation as runner  # noqa: E402
from ai_poc_foundation import LocalRuntimeTimeout, PoCFoundationError  # noqa: E402
from ai_quality_diagnosis import DiagnosisError  # noqa: E402


@pytest.fixture(scope="module")
def cases():
    return runner.cases()


def adversarial(cases, key="QE-A01"):
    return next(c["envelope"]["groups"][0] for c in cases if c["key"] == key)


class Runtime:
    def __init__(self, output=None, error=None):
        self.output, self.error, self.calls = output, error, []

    def generate(self, prompt, *, model):
        self.calls.append((prompt, model))
        if self.error:
            raise self.error
        return self.output, 10


def test_known_duplicate_regression_all_six_attempts_keep_one_group(cases):
    duplicates = [c for c in cases if "QD3-E06" in c["key"]]
    assert len(duplicates) == 2
    for _ in range(3):
        for case in duplicates:
            assert len(case["envelope"]["groups"]) == 1
            group = case["envelope"]["groups"][0]
            assert group["code"] == "duplicate_serial"
            assert len(group["occurrences"]) == 1
    group = adversarial(cases, "QE-A02")
    assert [o["severity"] for o in group["occurrences"]] == ["error", "warning"]
    assert [o["row"]["value"] for o in group["occurrences"]] == [3, 4]


def test_missing_serial_does_not_become_column_letter(cases):
    occurrence = adversarial(cases)["occurrences"][0]
    assert occurrence["column"] == {"state": "known", "value": "B"}
    assert occurrence["field"] == {"state": "known", "value": "serial_number"}
    assert occurrence["known_value"] == {"state": "unavailable"}
    assert occurrence["unknown_value"] == {"state": "missing"}
    unavailable = adversarial(cases, "QE-A04")["occurrences"][0]
    assert unavailable["unknown_value"] == {"state": "not_exposed"}
    assert unavailable["row"] == {"state": "not_provided"}


@pytest.mark.parametrize(
    "suffix",
    [
        " O serial é B.",
        " A linha 2 identifica o lote 2.",
        " O operador omitiu intencionalmente o dado.",
        " A causa é falha no sistema de origem.",
        " O serial é SYN-INVENTED-179.",
        " Não há problemas na origem.",
        " Corrigir e aprovar automaticamente.",
    ],
)
def test_rejects_unsupported_claims_even_if_schema_valid(cases, suffix):
    group = adversarial(cases)
    output = quality.baseline(group)
    output["explanation"] += suffix
    runtime = Runtime(json.dumps(output))
    result = quality.explain(group, runtime, model="qwen3:4b-instruct")
    assert result["rejection_code"] == "unsupported_explanation"
    assert result["origin"] == "deterministic"
    assert suffix not in json.dumps(result, ensure_ascii=False)
    assert (
        result["response_sha256"] == hashlib.sha256(runtime.output.encode()).hexdigest()
    )


@pytest.mark.parametrize(
    "change",
    [
        {"code": "required_field"},
        {"severity": "warning"},
        {"human_checks": []},
        {"human_checks": ["Aprovar o lote."]},
        {"human_checks": ["Conferir os registros relacionados na fonte."] * 2},
        {"explanation": "x" * 401},
        {"diagnoses": []},
    ],
)
def test_output_cannot_change_facts_or_escape_schema(cases, change):
    group = adversarial(cases)
    output = {**quality.baseline(group), **change}
    result = quality.explain(group, Runtime(json.dumps(output)))
    assert result["rejection_code"] in {
        "invalid_output_schema",
        "unsupported_human_check",
    }
    assert result["group"] == group


@pytest.mark.parametrize(
    "error,code",
    [
        (LocalRuntimeTimeout("sensitive detail"), "runtime_timeout"),
        (TimeoutError("sensitive detail"), "runtime_timeout"),
        (PoCFoundationError("sensitive detail"), "runtime_unavailable"),
        (ConnectionError("sensitive detail"), "runtime_unavailable"),
    ],
)
def test_runtime_failure_immediately_returns_baseline(cases, error, code):
    group = adversarial(cases)
    runtime = Runtime(error=error)
    result = quality.explain(group, runtime)
    assert len(runtime.calls) == 1
    assert result["text"] == quality.baseline(group)
    assert result["state"] == "fallback_deterministic"
    assert result["rejection_code"] == code
    assert "sensitive detail" not in json.dumps(result)


@pytest.mark.parametrize(
    "raw,code", [("not json", "invalid_json"), ("x" * 4097, "output_too_large")]
)
def test_invalid_output_never_persists_raw(cases, raw, code):
    result = quality.explain(adversarial(cases), Runtime(raw))
    assert result["rejection_code"] == code
    assert result["response_sha256"]
    assert raw not in json.dumps(result)


def test_accepted_text_has_explicit_abstention_and_no_mutation(cases):
    group = adversarial(cases)
    before = copy.deepcopy(group)
    runtime = Runtime(json.dumps(quality.baseline(group)))
    result = quality.explain(group, runtime)
    assert group == before
    assert result["origin"] == "model"
    assert result["state"] == "insufficient_evidence"
    assert quality.CAUSE_LIMIT in result["text"]["explanation"]
    assert quality.VALUE_LIMIT in result["text"]["explanation"]
    prompt, _ = runtime.calls[0]
    assert '"tools"' not in prompt
    for case in cases:
        for item in case["envelope"]["groups"]:
            quality.validate_text(item, quality.baseline(item))


def test_projection_rejects_loss_duplication_and_changed_pipeline_facts(cases):
    group = adversarial(cases, "QE-A02")
    context = {
        "case_id": "test",
        "occurrences": [
            {
                "code": group["code"],
                **{
                    k: v
                    for k, v in o.items()
                    if k in {"evidence_id", "severity", "reason"}
                },
                **{k: o[k].get("value") for k in ("row", "sheet", "column")},
            }
            for o in group["occurrences"]
        ],
    }
    envelope = {"schema_version": "1.0.0", "case_id": "test", "groups": [group]}
    quality.validate_projection(context, envelope)
    for mutation in ("loss", "duplicate", "severity", "category", "position"):
        changed = copy.deepcopy(envelope)
        if mutation == "loss":
            changed["groups"][0]["occurrences"].pop()
        elif mutation == "duplicate":
            changed["groups"].append(copy.deepcopy(group))
        elif mutation == "severity":
            changed["groups"][0]["occurrences"][0]["severity"] = "warning"
        elif mutation == "category":
            changed["groups"][0]["category"] = "unknown"
        else:
            changed["groups"][0]["occurrences"][0]["column"]["value"] = "Z"
        with pytest.raises(DiagnosisError):
            quality.validate_projection(context, changed)


def test_freeze_detects_changes_and_cannot_overwrite_results(tmp_path, monkeypatch):
    snapshot = {"configuration": {"repetitions": 3}}
    monkeypatch.setattr(runner, "freeze", lambda: snapshot)
    output = tmp_path / "run"
    with pytest.raises(PoCFoundationError, match="frozen_inputs_changed"):
        runner.run({"tampered": True}, output)
    assert not output.exists()
    runner.save_new(tmp_path / "freeze.json", snapshot)
    with pytest.raises(FileExistsError):
        runner.save_new(tmp_path / "freeze.json", {})


def test_integrated_surface_has_no_mutation_tools():
    from app.main import app

    operations = {
        (method, path)
        for path, route in app.openapi()["paths"].items()
        if path.startswith("/ai/quality")
        for method in route
    }
    assert operations == {
        ("get", "/ai/quality/scenarios"),
        ("post", "/ai/quality/scenarios/{scenario_id}/explanations"),
    }
    assert not hasattr(quality, "tools")


def test_duplicate_json_keys_are_refused(cases):
    group = adversarial(cases)
    output = json.dumps(quality.baseline(group))
    raw = '{"explanation":"O serial é B",' + output[1:]
    result = quality.explain(group, Runtime(raw))
    assert result["rejection_code"] == "duplicate_json_key"
    assert "O serial é B" not in json.dumps(result)


class Sampler:
    failure = None

    def __init__(self, *args):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def report(self):
        return {"sampled_rss_peak_bytes": None}


def test_complete_frozen_batch_and_offline_replay(cases, tmp_path, monkeypatch):
    selected = [c for c in cases if c["key"] in {"QE-A01", "QE-A02"}]
    snapshot = {"configuration": runner.read(runner.CONFIG), "cases": selected}
    monkeypatch.setattr(runner, "freeze", lambda: snapshot)
    monkeypatch.setattr(runner, "runtime_status", lambda _: {"available": True})
    # Refusals must remain in the denominator; no selective retry.
    runtime = Runtime("invalid json")
    result = runner.run(
        snapshot,
        tmp_path / "run",
        runtime_factory=lambda _: runtime,
        sampler_factory=Sampler,
    )
    assert result["complete"]
    assert len(result["attempts"]) == 12
    assert len(runtime.calls) == 6
    assert result["metrics"]["candidate"]["rejected_groups"] == 6
    assert result["metrics"]["candidate"]["occurrence_coverage"] == 1
    assert result["metrics"]["candidate"]["duplicate_diagnoses"] == 0
    document = renderer.build(snapshot, result)
    assert "__EVIDENCE__" not in document
    assert "connect-src 'none'" in document
    assert "fetch(" not in document
    assert "innerHTML" not in document
    assert "Controle sintético: resposta recusada" in document
    assert "invalid json" not in document
    assert runner.read(tmp_path / "run/results.json") == result
    with pytest.raises(FileExistsError):
        runner.run(
            snapshot,
            tmp_path / "run",
            runtime_factory=lambda _: runtime,
            sampler_factory=Sampler,
        )


def test_replay_rejects_lost_or_mutated_evidence(cases):
    case = next(c for c in cases if c["key"] == "QE-A01")
    snapshot = {"configuration": {"repetitions": 1}, "cases": [case]}
    report = {
        "complete": True,
        "snapshot_sha256": quality.sha(snapshot),
        "attempts": [],
    }
    with pytest.raises(ValueError, match="missing_attempts"):
        renderer.build(snapshot, report)


def test_runtime_pin_mismatch_prevents_generation(monkeypatch):
    config = runner.read(runner.CONFIG)
    monkeypatch.setattr(
        runner,
        "request_json",
        lambda _, route: (
            {"version": config["runtime_version"]}
            if route == "version"
            else {"models": [{"name": config["model"], "digest": "different"}]}
        ),
    )
    assert runner.runtime_status(config) == {
        "available": False,
        "rejection_code": "model_or_runtime_pin_mismatch",
    }
