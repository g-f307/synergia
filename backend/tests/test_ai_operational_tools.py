from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ai_operational_summary import (  # noqa: E402
    MAX_MODEL_STEPS,
    MAX_TOOL_CALLS,
    ToolRegistry,
    baseline,
    collect_agent_attempt,
    load_case,
)
from evaluate_ai_operational import score_tool_calls  # noqa: E402


def case(number="01"):
    return load_case(ROOT / f"data/synthetic/ai-operational-v2/OP-{number}-input.json")


def call(name, arguments):
    return {"kind": "tool_call", "name": name, "arguments": arguments}


class Sequence:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    def generate(self, prompt, *, model):
        self.prompts.append(prompt)
        return json.dumps(next(self.responses)), 7


def test_model_selects_read_then_receives_result_and_finishes():
    value = case()
    runtime = Sequence(
        [
            call("get_execution", {"execution_id": "syn-op-01"}),
            {"kind": "final", "output": baseline(value)},
        ]
    )
    result = collect_agent_attempt(value, runtime, "test")
    assert result["failure"] is None
    assert '"lifecycle": "completed"' not in runtime.prompts[0]
    assert '"lifecycle": "completed"' in runtime.prompts[1]
    assert result["generated_tokens"] == 14
    assert result["tool_calls"][0]["arguments"] == {"execution_id": "syn-op-01"}
    assert result["tool_calls"][0]["result_sha256"]
    score = score_tool_calls(value, ["get_execution"], result["tool_calls"])
    assert score["accuracy"] == score["recall"] == 1


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("delete_execution", {}),
        ("get_execution", {}),
        ("get_execution", {"execution_id": "outside"}),
        ("list_pending", {"limit": True}),
        ("list_pending", {"limit": 51}),
        ("list_pending", {"status": []}),
        ("list_pending", {"priority": "urgent"}),
        ("list_events", {"sql": "private query"}),
    ],
)
def test_invalid_call_is_denied_recorded_and_model_can_recover(name, arguments):
    value = case()
    runtime = Sequence(
        [
            call(name, arguments),
            call("get_execution", {"execution_id": "syn-op-01"}),
            {"kind": "final", "output": baseline(value)},
        ]
    )
    result = collect_agent_attempt(value, runtime, "test")
    assert result["failure"] is None
    assert result["tool_calls"][0]["outcome"] == "denied"
    assert result["tool_calls"][0]["arguments"] is None
    assert "private query" not in runtime.prompts[-1]
    score = score_tool_calls(value, ["get_execution"], result["tool_calls"])
    assert score["denied"] == 1
    assert score["accuracy"] == 0.5


def test_unnecessary_duplicate_calls_reduce_accuracy_and_are_bounded():
    value = case()
    runtime = Sequence(
        [call("get_execution", {"execution_id": "syn-op-01"})] * (MAX_MODEL_STEPS + 2)
    )
    result = collect_agent_attempt(value, runtime, "test")
    assert result["failure"] == "tool_call_limit"
    assert len(runtime.prompts) == MAX_MODEL_STEPS
    assert (
        sum(c["outcome"] == "succeeded" for c in result["tool_calls"]) == MAX_TOOL_CALLS
    )
    score = score_tool_calls(value, ["get_execution"], result["tool_calls"])
    assert score["correct"] == 1
    assert score["incorrect"] == MAX_TOOL_CALLS


def test_no_tool_choice_is_not_perfect_accuracy():
    value = case()
    runtime = Sequence([{"kind": "final", "output": baseline(value)}])
    result = collect_agent_attempt(value, runtime, "test")
    assert result["failure"] == "unretrieved_evidence"
    assert score_tool_calls(value, ["get_execution"], [])["accuracy"] == 0


def test_allowed_but_unnecessary_tool_is_not_a_correct_choice():
    value = case()
    registry = ToolRegistry(value)
    registry.call("list_pending", {})
    registry.call("get_execution", {"execution_id": "syn-op-01"})
    score = score_tool_calls(value, ["get_execution"], registry.calls)
    assert score["accuracy"] == score["precision"] == 0.5
    assert score["recall"] == 1


def test_denied_calls_also_consume_the_iteration_budget():
    runtime = Sequence([call("delete_execution", {})] * (MAX_MODEL_STEPS + 1))
    result = collect_agent_attempt(case(), runtime, "test")
    assert result["failure"] == "tool_call_limit"
    assert len(runtime.prompts) == MAX_MODEL_STEPS
    assert sum(c["outcome"] == "denied" for c in result["tool_calls"]) == MAX_TOOL_CALLS


def test_expired_attempt_does_not_call_the_model(monkeypatch):
    import ai_operational_summary as module

    monkeypatch.setattr(module, "MAX_ATTEMPT_SECONDS", 0)
    runtime = Sequence([])
    result = collect_agent_attempt(case(), runtime, "test")
    assert result["failure"] == "attempt_time_limit"
    assert runtime.prompts == []


def test_cannot_cite_case_evidence_not_returned_by_a_tool():
    value = case("02")
    runtime = Sequence(
        [
            call("get_execution", {"execution_id": "syn-op-02"}),
            {"kind": "final", "output": baseline(value)},
        ]
    )
    assert (
        collect_agent_attempt(value, runtime, "test")["failure"]
        == "unretrieved_evidence"
    )


def test_filtered_query_missing_relevant_evidence_counts_as_incorrect():
    value = case("02")
    registry = ToolRegistry(value)
    registry.call("list_pending", {"status": "closed"})
    score = score_tool_calls(value, ["get_execution", "list_pending"], registry.calls)
    assert score["correct"] == 0
    assert score["missing"] == 2
    assert score["incorrect"] == 1
