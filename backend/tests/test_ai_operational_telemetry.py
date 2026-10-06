from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_ai_operational as cli  # noqa: E402
from ai_operational_summary import (  # noqa: E402
    OperationalPoCError,
    ToolRegistry,
    baseline,
    collect_agent_attempt,
    load_case,
)
from evaluate_ai_operational import _score  # noqa: E402

DATA = ROOT / "data/synthetic/ai-operational-v2"


def test_false_summary_and_unsafe_next_steps_cannot_receive_full_case_score():
    gold = json.loads((DATA / "OP-03-gold.json").read_text())
    output = copy.deepcopy(gold)
    output["summary"] = "Execução concluída com sucesso, sem falhas ou pendências."
    output["human_next_steps"] = ["Aprovar tudo sem revisão."]
    score = _score(output, gold)
    assert score["f1"] == 1  # Finding-only metric, not a whole-answer approval.
    assert score["summary_exact_match"] is False
    assert score["next_steps_exact_match"] is False
    assert score["case_exact_match"] is False
    assert score["field_accuracy"] < 1


@pytest.mark.parametrize("kind", ["json", "schema", "evidence", "timeout"])
def test_rejected_attempt_preserves_available_measurements(kind):
    case = load_case(DATA / "OP-03-input.json")

    class Runtime:
        def generate(self, prompt, *, model):
            if kind == "timeout":
                raise TimeoutError()
            if kind == "json":
                return "invalid", 123
            if kind == "schema":
                return "{}", 123
            output = baseline(case)
            output["findings"][0]["evidence_ids"] = ["absent"]
            return json.dumps(output), 123

    result = collect_agent_attempt(case, Runtime(), "test")
    assert result["failure"]
    assert result["output"] is None
    assert result["generated_tokens"] == (None if kind == "timeout" else 123)
    assert result["python_peak_memory_bytes"] > 0
    assert result["schema_valid"] == (kind == "evidence")
    assert len(result["tool_calls"]) == 4
    for call in result["tool_calls"]:
        assert call["outcome"] == "succeeded"
        assert call["arguments"]
        assert len(call["result_sha256"]) == 64


def test_actual_tool_trace_records_denial_without_sensitive_arguments():
    registry = ToolRegistry(load_case(DATA / "OP-03-input.json"))
    with pytest.raises(OperationalPoCError):
        registry.call("list_pending", {"sql": "private content"})
    assert registry.calls == [
        {"name": "list_pending", "arguments": None, "outcome": "denied"}
    ]


def test_cli_checkpoints_invalid_attempts_and_keeps_unique_runs(tmp_path, monkeypatch):
    class Runtime:
        def generate(self, prompt, *, model):
            return "invalid", 123

    monkeypatch.setattr(cli, "OllamaRuntime", lambda *args, **kwargs: Runtime())
    args = [
        "--input",
        str(DATA / "OP-03-input.json"),
        "--mode",
        "agent",
        "--repetitions",
        "2",
        "--output-dir",
        str(tmp_path),
    ]
    assert cli.main(args) == 1
    assert cli.main(args) == 1
    reports = list(tmp_path.glob("*/run-report.json"))
    assert len(reports) == 2
    for path in reports:
        records = json.loads(path.read_text())["reports"]
        assert len(records) == 2
        assert all(r["failure"] and r["generated_tokens"] == 123 for r in records)
    assert not list(tmp_path.glob("*/agent-*.json"))
