from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai_operational_summary import (  # noqa: E402, I001
    OperationalPoCError,
    ToolRegistry,
    baseline,
    case_hash,
    load_case,
    run_agent,
    tool_context,
    validate_output,
)


CASE = ROOT / "data/synthetic/ai-poc-evaluation/operational/OP-02-input.json"


class FakeRuntime:
    def generate(self, prompt: str, *, model: str) -> tuple[str, int]:
        assert "pending_items" in prompt
        return json.dumps(baseline(load_case(CASE))), 10


def test_tools_are_allowlisted_and_scoped() -> None:
    case = load_case(CASE)
    registry = ToolRegistry(case)
    assert registry.call("list_pending", {"limit": 50}) == case["pending_items"]
    with pytest.raises(OperationalPoCError, match="não autorizada"):
        registry.call("delete_pending", {})
    with pytest.raises(OperationalPoCError, match="parâmetros"):
        registry.call("list_pending", {"limit": 50, "sql": "select 1"})


def test_baseline_and_agent_share_case_and_evidence() -> None:
    case = load_case(CASE)
    output = baseline(case)
    validate_output(case, output)
    agent_output = run_agent(case, FakeRuntime(), "synthetic")
    validate_output(case, agent_output)
    assert case_hash(case) == case_hash(load_case(CASE))
    assert (
        tool_context(case)["execution"]["execution_id"]
        == case["execution"]["execution_id"]
    )


def test_unknown_evidence_and_unbounded_tool_arguments_are_rejected() -> None:
    case = load_case(CASE)
    output = baseline(case)
    if output["findings"]:
        output["findings"][0]["evidence_ids"] = ["invented"]
        with pytest.raises(OperationalPoCError, match="evidência"):
            validate_output(case, output)


def test_missing_evidence_requires_uncertainty() -> None:
    case = load_case(ROOT / "data/synthetic/ai-operational-v2/OP-04-input.json")
    output = baseline(case)
    assert output["status"] == "insufficient_evidence"
    assert output["open_questions"]
