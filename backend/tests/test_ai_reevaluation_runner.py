"""Offline regression for reserved-set gates, crashes and local runtime telemetry."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import ai_reevaluation as runner  # noqa: E402
import ai_reevaluation_telemetry as telemetry  # noqa: E402
from ai_poc_foundation import LocalRuntimeTimeout, PoCFoundationError  # noqa: E402


class FakeSampler:
    failure = None

    def __init__(self, *args):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def report(self):
        return {
            "sampled_rss_peak_bytes": None,
            "sampled_total_gpu_used_peak_bytes": None,
        }


def config(kind="quality", mode="baseline"):
    middle = "baseline" if mode == "baseline" else "qwen3-4b-auto"
    path = ROOT / f"scripts/ai_reevaluation_configs/{kind}-{middle}-development.json"
    return runner.configuration(path)


def frozen(value):
    return runner.freeze(
        value, metadata=lambda _: {"fake": True}, identity=lambda: {"fake": True}
    )


def invoke(snapshot, output, **kwargs):
    return runner.run(
        snapshot, output, freezer=frozen, sampler_factory=FakeSampler, **kwargs
    )


@pytest.mark.parametrize("kind,measured", [("quality", 24), ("operational", 12)])
def test_baselines_use_all_cases_three_times_without_runtime(kind, measured, tmp_path):
    snapshot = frozen(config(kind))
    state = invoke(
        snapshot, tmp_path / "run", runtime_factory=lambda _: pytest.fail("no model")
    )
    assert state["complete"]
    assert state["quality_denominator"] == measured
    assert state["planned_quality_denominator"] == measured
    assert state["failed_measured_attempts"] == 0
    assert len(state["attempts"]) == measured + 1
    assert all(a["result"]["free_text_review"] == "pending" for a in state["attempts"])
    assert all("E0" not in a["case"] for a in state["attempts"])
    before = runner.read(tmp_path / "run/run.json")
    assert invoke(snapshot, tmp_path / "run", resume=True) == before


@pytest.mark.parametrize("kind", ["quality", "operational"])
def test_reserved_evaluation_requires_exact_final_selection(kind):
    value = config(kind)
    value["split"] = "evaluation"
    protocol = runner.read(runner.PROTOCOL)
    _, review = runner.corpus(kind)
    with pytest.raises(PoCFoundationError, match="frozen_selection"):
        runner.check_gate(value, protocol, review)
    protocol["status"] = "frozen"
    protocol["evaluation"]["final_configurations"] = [
        {"id": value["id"], "config_sha256": runner.digest(value)}
    ]
    runner.check_gate(value, protocol, review)
    value["options"]["num_ctx"] = 8192
    with pytest.raises(PoCFoundationError, match="frozen_selection"):
        runner.check_gate(value, protocol, review)


@pytest.mark.parametrize("kind", ["quality", "operational"])
def test_warmup_for_reserved_plan_only_uses_development(kind):
    snapshot = frozen(config(kind))
    snapshot["configuration"]["split"] = "evaluation"
    cases, _ = runner.corpus(kind)
    snapshot["cases"] = [c["key"] for c in cases if c["split"] == "evaluation"]
    attempts = runner.plan(snapshot)
    assert "D01" in attempts[0]["case"]
    assert all("E" in a["case"] for a in attempts[1:])


def test_gold_approval_is_required_even_for_development():
    value = config()
    protocol = runner.read(runner.PROTOCOL)
    _, review = runner.corpus("quality")
    protocol["human_review"]["status"] = "pending"
    with pytest.raises(PoCFoundationError, match="gold_review_required"):
        runner.check_gate(value, protocol, review)


@pytest.mark.parametrize(
    "mutation", ["options", "cases", "hashes", "hardware", "runtime"]
)
def test_changed_snapshot_rejected_before_directory_or_inference(mutation, tmp_path):
    snapshot = frozen(config())
    snapshot[mutation] = {} if mutation != "cases" else ["other"]
    with pytest.raises(PoCFoundationError, match="changed"):
        invoke(snapshot, tmp_path / "run")
    assert not (tmp_path / "run").exists()


class InvalidRuntime:
    response_metrics = {"eval_count": 3}
    response_done_reason = "length"

    def generate(self, prompt, *, model):
        # No annotation/rubric or expected-label metadata may leak into prompts.
        assert "gold_review" not in prompt
        assert "expected_facts" not in prompt
        return "invalid json", 3


@pytest.mark.parametrize("kind", ["quality", "operational"])
def test_invalid_responses_preserved_in_denominator_with_generation(kind, tmp_path):
    snapshot = frozen(config(kind, "agent"))
    state = invoke(
        snapshot,
        tmp_path / "run",
        allow_inference=True,
        runtime_factory=lambda _: InvalidRuntime(),
        loaded_models=lambda: [],
    )
    assert state["complete"]
    assert state["failed_measured_attempts"] == state["planned_quality_denominator"]
    assert all(a["failure"] == "invalid_json" for a in state["attempts"])
    assert all(a["generation"][0]["truncated"] for a in state["attempts"])
    assert all(
        a["resources"]["sampled_total_gpu_used_peak_bytes"] is None
        for a in state["attempts"]
    )


def test_inference_requires_explicit_flag(tmp_path):
    snapshot = frozen(config(mode="agent"))
    with pytest.raises(PoCFoundationError, match="explicit_inference"):
        invoke(snapshot, tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_crash_is_journaled_before_call_and_not_retried(tmp_path, monkeypatch):
    snapshot = frozen(config())
    original = runner.execute_case

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "execute_case", interrupt)
    with pytest.raises(KeyboardInterrupt):
        invoke(snapshot, tmp_path / "run")
    state = runner.read(tmp_path / "run/run.json")
    assert state["attempts"][0]["state"] == "started"
    assert len(state["attempts"]) == 1
    monkeypatch.setattr(runner, "execute_case", original)
    state = invoke(snapshot, tmp_path / "run", resume=True)
    assert state["complete"]
    assert state["attempts"][0]["failure"] == "interrupted"
    assert state["attempts"][0]["result"] is None
    assert len(state["attempts"]) == 25


def test_new_run_refuses_existing_results_and_resume_refuses_duplicate_ids(tmp_path):
    snapshot = frozen(config())
    invoke(snapshot, tmp_path / "run")
    with pytest.raises(PoCFoundationError, match="existing_run_requires_resume"):
        invoke(snapshot, tmp_path / "run")
    state = runner.read(tmp_path / "run/run.json")
    state["attempts"].append(state["attempts"][0])
    runner.save(tmp_path / "run/run.json", state)
    with pytest.raises(PoCFoundationError, match="duplicate_attempt"):
        invoke(snapshot, tmp_path / "run", resume=True)


def test_low_resources_prevent_request_and_leave_incomplete_report(tmp_path):
    class Unavailable(FakeSampler):
        failure = "available_ram_limit"

    snapshot = frozen(config())
    state = runner.run(
        snapshot, tmp_path / "run", freezer=frozen, sampler_factory=Unavailable
    )
    assert not state["complete"]
    assert state["quality_denominator"] == 0
    assert state["planned_quality_denominator"] == 24
    assert state["stop_reason"] == "available_ram_limit"
    assert state["attempts"] == []


def test_concurrent_other_model_is_rejected(tmp_path):
    snapshot = frozen(config(mode="agent"))
    with pytest.raises(PoCFoundationError, match="dedicated_runtime"):
        invoke(
            snapshot,
            tmp_path / "run",
            allow_inference=True,
            loaded_models=lambda: [{"name": "other"}],
        )


@pytest.mark.parametrize("kind", ["quality", "operational"])
def test_timeout_is_failure_never_fallback(kind, tmp_path):
    class TimedOut:
        def generate(self, *args, **kwargs):
            raise LocalRuntimeTimeout("local timeout")

    state = invoke(
        frozen(config(kind, "agent")),
        tmp_path / "run",
        allow_inference=True,
        runtime_factory=lambda _: TimedOut(),
        loaded_models=lambda: [],
    )
    assert all(a["failure"] == "runtime_timeout" for a in state["attempts"])
    assert state["failed_measured_attempts"] == state["planned_quality_denominator"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("endpoint", "https://remote:443/api/generate"),
        ("prompt", "../other.txt"),
        ("extra", True),
        ("request_timeout_seconds", 301),
    ],
)
def test_configuration_rejects_remote_paths_unbounded_options(field, value, tmp_path):
    c = config()
    c[field] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(c))
    with pytest.raises(PoCFoundationError):
        runner.configuration(path)


def test_resource_limits_and_unavailable_are_explicit():
    protocol = runner.read(runner.PROTOCOL)
    limits = protocol["resources"]
    before = {"ram_available_bytes": 5 * 1024**3, "swap_used_bytes": 0, "gpus": None}
    assert telemetry.resource_failure(before, before, limits) is None
    current = copy.deepcopy(before)
    current["swap_used_bytes"] = limits["max_swap_growth_bytes"] + 1
    assert telemetry.resource_failure(before, current, limits) == "swap_growth_limit"
    current = dict(before, ram_available_bytes=None)
    assert (
        telemetry.resource_failure(before, current, limits)
        == "ram_telemetry_unavailable"
    )
    current = dict(
        before, gpus=[{"total_bytes": 4 * 1024**3, "used_bytes": 4 * 1024**3}]
    )
    assert telemetry.resource_failure(before, current, limits) == "gpu_headroom_limit"


def test_gpu_unavailable_and_multiple_cards(monkeypatch):
    monkeypatch.setattr(telemetry, "command", lambda _: None)
    assert telemetry.gpu_memory() is None
    monkeypatch.setattr(telemetry, "command", lambda _: "4096, 1024\n8192, 2048")
    assert telemetry.gpu_memory() == [
        {"total_bytes": 4096 * 1024**2, "used_bytes": 1024 * 1024**2},
        {"total_bytes": 8192 * 1024**2, "used_bytes": 2048 * 1024**2},
    ]


def test_comparison_requires_same_cases_and_baseline_and_reports_failures(tmp_path):
    baseline = invoke(frozen(config()), tmp_path / "baseline")
    agent = invoke(
        frozen(config(mode="agent")),
        tmp_path / "agent",
        allow_inference=True,
        runtime_factory=lambda _: InvalidRuntime(),
        loaded_models=lambda: [],
    )
    report = runner.compare([baseline, agent])
    assert report["decision"] == "not_decided"
    assert report["runs"][0]["accepted_rate"] == 1
    assert report["runs"][1]["accepted_rate"] == 0
    assert report["runs"][1]["failures"] == {"invalid_json": 24}
    assert report["runs"][1]["mean_latency_ms"] is not None
    assert report["runs"][1]["generated_tokens_known"] == 72
    assert report["runs"][1]["semantic_fidelity"] == "pending_human_review"
    assert report["runs"][1]["valid_structural_consistency"] == 0
    with pytest.raises(PoCFoundationError, match="requires_baseline"):
        runner.compare([agent])
    modified = copy.deepcopy(agent)
    modified["snapshot"]["cases"] = []
    with pytest.raises(PoCFoundationError, match="identical_cases"):
        runner.compare([baseline, modified])


def test_interrupted_measured_attempt_counts_as_failure_and_unknown_latency(
    tmp_path, monkeypatch
):
    snapshot = frozen(config())
    original = runner.execute_case
    count = 0

    def interrupt(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise KeyboardInterrupt
        return original(*args)

    monkeypatch.setattr(runner, "execute_case", interrupt)
    with pytest.raises(KeyboardInterrupt):
        invoke(snapshot, tmp_path / "run")
    monkeypatch.setattr(runner, "execute_case", original)
    state = invoke(snapshot, tmp_path / "run", resume=True)
    summary = runner.summarize_run(state)
    assert state["failed_measured_attempts"] == 1
    assert summary["measured_attempts"] == 24
    assert summary["accepted_rate"] == 23 / 24
    assert summary["latency_unknown_attempts"] == 1
    assert summary["accepted_f1_micro"] is None


def test_pinned_runtime_model_quantization_and_thinking_capability(monkeypatch):
    c = config(mode="agent")
    responses = {
        "version": {"version": c["runtime_version"]},
        "tags": {
            "models": [
                {
                    "name": c["model"],
                    "digest": c["model_digest"],
                    "details": {"quantization_level": "Q4_K_M"},
                }
            ]
        },
        "show": {"license": "Apache-2.0", "capabilities": ["completion"]},
    }
    monkeypatch.setattr(
        runner, "request_json", lambda _, route, payload=None: responses[route]
    )
    result = runner.runtime_metadata(c)
    assert result["digest"] == c["model_digest"]
    assert "license" not in result
    c["think"] = True
    with pytest.raises(PoCFoundationError, match="thinking_not_supported"):
        runner.runtime_metadata(c)
    c["think"] = False
    responses["tags"]["models"][0]["details"]["quantization_level"] = "Q8_0"
    with pytest.raises(PoCFoundationError, match="quantization_pin"):
        runner.runtime_metadata(c)
    responses["version"]["version"] = "0.0.0"
    with pytest.raises(PoCFoundationError, match="runtime_pin"):
        runner.runtime_metadata(c)


def test_pending_license_candidate_not_eligible():
    c = config(mode="agent")
    c["model"] = "llama3.2:1b"
    _, review = runner.corpus("quality")
    with pytest.raises(PoCFoundationError, match="license_review_required"):
        runner.check_gate(c, runner.read(runner.PROTOCOL), review)


def test_remaining_deadline_is_applied_to_each_request(monkeypatch):
    c = config(mode="agent")
    clock = iter([0, 598, 599])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(clock))
    runtime = runner.make_runtime(c)

    def generate(prompt, *, model):
        assert runtime.config.timeout_seconds == 2
        return "{}", 1

    monkeypatch.setattr(runtime, "generate", generate)
    metered = runner.MeteredRuntime(runtime, c, FakeSampler())
    assert metered.generate("synthetic", model=c["model"]) == ("{}", 1)


def test_think_and_keep_alive_explicit_no_reasoning_persisted(monkeypatch):
    c = config(mode="agent")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(
                {
                    "response": "{}",
                    "thinking": "private reasoning",
                    "done_reason": "length",
                    "eval_count": 12,
                    "load_duration": 100,
                    "model": c["model"],
                }
            ).encode()

    class Opener:
        def open(self, request, timeout):
            body = json.loads(request.data)
            assert body["think"] is False
            assert body["keep_alive"] == 600
            assert body["options"]["num_ctx"] == 4096
            return Response()

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    runtime = runner.make_runtime(c)
    assert runtime.generate("synthetic", model=c["model"]) == ("{}", 12)
    assert runtime.response_done_reason == "length"
    assert runtime.response_metrics["eval_count"] == 12
    assert not hasattr(runtime, "thinking")
    assert "private reasoning" not in str(runtime.__dict__)
