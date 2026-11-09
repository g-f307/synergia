"""Final campaign controls with fake runtime; never use services or credentials."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate_ai_knowledge_final as evaluator  # noqa: E402
import run_ai_knowledge_final as runner  # noqa: E402
from ai_knowledge import KnowledgeError, digest, read  # noqa: E402
from render_ai_knowledge_final import render_html  # noqa: E402


def protocol():
    result = copy.deepcopy(read(ROOT / "docs/ai-knowledge-poc-protocol.json"))
    result["budget"]["minimum_disk_free_bytes"] = 0
    return result


@pytest.fixture
def simulated(tmp_path, monkeypatch):
    run = tmp_path / "classification"
    run.mkdir()
    requests = [
        {
            "case_id": f"E{i + 1:02d}",
            "card_id": "K03",
            "seed": 125,
            "model": model,
            "body": {"model": model},
        }
        for i, model in enumerate(
            ["qwen3:4b-instruct", "qwen3:4b-instruct", "qwen3:8b"]
        )
    ]
    plan = {
        "kind": "classification",
        "phase": "evaluation",
        "requests": requests,
        "requests_sha256": digest(requests),
    }
    monkeypatch.setattr(runner, "frozen_plan", lambda *_: ({}, protocol(), {}, plan))
    monkeypatch.setattr(runner, "inventory", lambda *_: {})
    monkeypatch.setattr(runner, "hardware", lambda: {})
    calls = []

    class FakeRuntime:
        def request(self, route, payload=None, timeout=None):
            if route == "chat":
                calls.append(payload)
                return {"message": {"content": "{}"}, "done_reason": "stop"}
            return {"models": []}

        def unload(self, model):
            pass

    class FakeSampler:
        failure = None

        def __init__(self, *_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def report(self):
            return {"resource_failure": None}

    monkeypatch.setattr(runner, "Runtime", FakeRuntime)
    monkeypatch.setattr(runner, "Sampler", FakeSampler)
    return tmp_path, run, plan, calls


def test_one_model_per_batch_resume_and_semantic_failure_are_not_retried(simulated):
    root, run, plan, calls = simulated
    runner.execute(root, run, 32)
    assert len(calls) == 2
    assert not (run / "complete.json").exists()
    # {} is semantically invalid; still a completed, charged call, never repaired.
    first = (run / "attempt-000.json").read_bytes()
    runner.execute(root, run, 32)
    assert len(calls) == 3
    complete = read(run / "complete.json")
    assert complete["calls"] == 3
    assert complete["raw_sha256"] == [
        hashlib.sha256((run / f"attempt-{i:03d}.json").read_bytes()).hexdigest()
        for i in range(3)
    ]
    runner.execute(root, run, 32)
    assert len(calls) == 3
    assert (run / "attempt-000.json").read_bytes() == first
    assert read(root / "budget.json")["generative_calls"] == 3


def test_transport_uncertainty_is_retained_and_blocks_resume(simulated, monkeypatch):
    root, run, plan, calls = simulated

    class FailedRuntime:
        def request(self, route, payload=None, timeout=None):
            assert route == "chat"
            calls.append(payload)
            raise TimeoutError("synthetic transport uncertainty")

        def unload(self, model):
            pytest.fail("No unload after uncertain call")

    monkeypatch.setattr(runner, "Runtime", FailedRuntime)
    with pytest.raises(TimeoutError):
        runner.execute(root, run, 32)
    assert read(run / "attempt-000.json")["error"] == "TimeoutError"
    assert read(root / "budget.json")["receipts"][0]["state"] == "transport_uncertain"
    with pytest.raises(KnowledgeError, match="reconciliation"):
        runner.execute(root, run, 32)
    assert len(calls) == 1


def test_completed_payload_mutation_is_not_silently_replayed(simulated):
    root, run, plan, calls = simulated
    runner.execute(root, run, 1)
    plan["requests"][0]["body"]["model"] = "changed"
    with pytest.raises(KnowledgeError, match="reconciliation"):
        runner.execute(root, run, 32)
    assert len(calls) == 1


def test_prepare_preserves_all_seeds_order_and_serialized_payloads(
    tmp_path, monkeypatch
):
    config = read(runner.FINAL)
    matrix = read(ROOT / config["matrix_path"])
    monkeypatch.setattr(runner, "context", lambda *_: (config, protocol(), matrix))
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "source_hashes", lambda: {})
    monkeypatch.setattr(
        runner, "frozen_plan", lambda *_: (config, protocol(), matrix, {})
    )
    real_read = runner.read

    def no_gold(path):
        assert "-gold.json" not in str(path)
        return real_read(path)

    monkeypatch.setattr(runner, "read", no_gold)
    retrieval = tmp_path / "retrieval"
    retrieval.mkdir()
    ranking = {
        "rows": [
            {"case_id": cid, "rankings": {"focused/dense": ["K03"]}}
            for cid in matrix["cases"]
        ]
    }
    (retrieval / "rankings.json").write_text(json.dumps(ranking))
    run = tmp_path / "run"
    runner.prepare(tmp_path, retrieval, run)
    plan = read(run / "plan.json")
    assert len(plan["requests"]) == 48 * 2 * 3
    for seed, expected in [
        (125, ["qwen3:4b-instruct", "qwen3:8b"]),
        (126, ["qwen3:8b", "qwen3:4b-instruct"]),
        (127, ["qwen3:4b-instruct", "qwen3:8b"]),
    ]:
        rows = [r for r in plan["requests"] if r["seed"] == seed]
        assert [rows[0]["model"], rows[48]["model"]] == expected
        assert [r["case_id"] for r in rows[:48]] == matrix["execution_order"][
            str(seed)
        ]["cases"]
    for req in plan["requests"]:
        assert (
            digest(req["body"])
            == matrix["cases"][req["case_id"]]["reader_bodies_sha256"][
                f"{req['model']}/K03/{req['seed']}"
            ]
        )
    with pytest.raises(FileExistsError):
        runner.prepare(tmp_path, retrieval, tmp_path / "another")


def test_labels_cannot_be_opened_before_full_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(
        evaluator,
        "frozen_plan",
        lambda *_: ({}, {}, {}, {"kind": "classification"}),
    )

    def forbidden(path):
        pytest.fail("No reference read permitted before completion")

    monkeypatch.setattr(evaluator, "read", forbidden)
    with pytest.raises(KnowledgeError, match="all_final_requests"):
        evaluator.score(tmp_path, tmp_path)


def test_pooling_uses_denominators_and_keeps_seed_slots_explicit():
    tasks = [
        {
            "cases": 2,
            "answerable": 1,
            "displayed_items": n,
            "correct_displayed_items": ok,
            "high_errors_exposed": 0,
            "covered_cases": ok,
            "complete_cases": ok,
            "correct_check_cases": ok,
        }
        for n, ok in [(1, 1), (9, 0)]
    ]
    result = evaluator.pool_tasks(tasks)
    assert result["precision"] == 0.1
    assert result["coverage"] == 0.5
    assert result["cases"] == 4
    assert "not independent" in result["unit"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("precision", 0.89),
        ("coverage", 0.74),
        ("next_check_relevance", 0.84),
        ("high_errors_exposed", 1),
        ("precision", None),
    ],
)
def test_generation_gate_uses_chosen_model_full_campaign(field, value):
    observed = {
        "precision": 1,
        "coverage": 1,
        "next_check_relevance": 1,
        "high_errors_exposed": 0,
    }
    observed[field] = value
    scores = {
        "models": {"chosen": {"pooled_tasks": observed}, "other": {"pooled_tasks": {}}}
    }
    config = {
        "generation_model": "chosen",
        "rubric": "docs/ai-knowledge-poc-rubric.json",
    }
    gate = evaluator.generation_gate(scores, config)
    assert gate["passed"] is False
    assert gate["model"] == "chosen"
    assert gate["scores_sha256"] == digest(scores)


def test_generation_gate_accepts_exact_frozen_thresholds():
    observed = {
        "precision": 0.9,
        "coverage": 0.75,
        "next_check_relevance": 0.85,
        "high_errors_exposed": 0,
    }
    scores = {"models": {"chosen": {"pooled_tasks": observed}}}
    config = {
        "generation_model": "chosen",
        "rubric": "docs/ai-knowledge-poc-rubric.json",
    }
    assert evaluator.generation_gate(scores, config)["passed"]


def test_local_comparator_escapes_untrusted_fact_text():
    data = {
        "cases": [{"note": "</script><script>alert('unsafe')</script>"}],
        "seeds": [125],
    }
    html = render_html(data)

    class Parser(HTMLParser):
        inside = False
        payload = ""
        external = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "script" and attrs.get("id") == "data":
                self.inside = True
            if tag == "script" and "src" in attrs:
                self.external.append(attrs["src"])

        def handle_endtag(self, tag):
            if tag == "script":
                self.inside = False

        def handle_data(self, text):
            if self.inside:
                self.payload += text

    parser = Parser()
    parser.feed(html)
    assert json.loads(parser.payload) == data
    assert not parser.external
    assert "<script>alert" not in html
    assert "innerHTML" not in html


def test_cli_requires_explicit_inference_flag():
    with pytest.raises(SystemExit) as error:
        runner.main(
            [
                "execute",
                "--budget-root",
                str(ROOT / ".test-tmp/no-inference"),
                "--run-dir",
                str(ROOT / ".test-tmp/no-inference/run"),
            ]
        )
    assert error.value.code == 2
