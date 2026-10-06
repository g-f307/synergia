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
from scripts.validate_project_assets import validate_operational_manifest  # noqa: E402
from scripts.evaluate_ai_operational import _score  # noqa: E402
from scripts.evaluate_ai_operational import _nearest_rank  # noqa: E402


CASE = ROOT / "data/synthetic/ai-poc-evaluation/operational/OP-02-input.json"


class FakeRuntime:
    last_prompt = ""
    step = 0

    def generate(self, prompt: str, *, model: str) -> tuple[str, int]:
        self.last_prompt = prompt
        self.step += 1
        calls = [
            ("get_execution", {"execution_id": "syn-op-02"}),
            ("list_pending", {}),
            ("list_classifications", {}),
        ]
        if self.step <= len(calls):
            name, arguments = calls[self.step - 1]
            return json.dumps(
                {"kind": "tool_call", "name": name, "arguments": arguments}
            ), 10
        return (
            json.dumps(
                {
                    "kind": "final",
                    "output": {
                        "schema_version": "1.1.0",
                        "case_id": "OP-02",
                        "status": "completed",
                        "summary": "Execução aguardando revisão.",
                        "findings": [
                            {
                                "finding_id": "pending:201",
                                "title": "Pendência 201",
                                "severity": "warning",
                                "statement": "Classificação requer revisão humana.",
                                "evidence_ids": ["ev-op02-p1"],
                            }
                        ],
                        "open_questions": [],
                        "human_next_steps": ["Validar os achados."],
                    },
                }
            ),
            10,
        )


def test_tools_are_allowlisted_and_scoped() -> None:
    case = load_case(CASE)
    registry = ToolRegistry(case)
    assert registry.call("list_pending", {"limit": 50}) == case["pending_items"]
    assert (
        registry.call("list_classifications", {"limit": 50}) == case["classifications"]
    )
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


def test_agent_receives_case_identity_schema_and_classifications() -> None:
    case = load_case(CASE)
    runtime = FakeRuntime()
    run_agent(case, runtime, "synthetic")
    assert "CASE_ID: OP-02" in runtime.last_prompt
    assert (
        '"$schema": "https://json-schema.org/draft/2020-12/schema"'
        in runtime.last_prompt
    )
    assert "classifications" in runtime.last_prompt


def test_unknown_evidence_and_unbounded_tool_arguments_are_rejected() -> None:
    case = load_case(CASE)
    output = baseline(case)
    if output["findings"]:
        output["findings"][0]["evidence_ids"] = ["invented"]
        with pytest.raises(OperationalPoCError, match="evidência"):
            validate_output(case, output)


def test_evaluation_scores_factual_fields_not_only_finding_ids() -> None:
    case = load_case(ROOT / "data/synthetic/ai-operational-v2/OP-03-input.json")
    gold = json.loads(
        (ROOT / "data/synthetic/ai-operational-v2/OP-03-gold.json").read_text(
            encoding="utf-8"
        )
    )
    output = baseline(case)
    output["findings"][0]["severity"] = "info"
    output["findings"][0]["evidence_ids"] = ["execution"]
    score = _score(output, gold)
    assert score["identifier_precision"] == 1.0
    assert score["precision"] == 0.0
    assert score["field_accuracy"] < 1.0


def test_p95_uses_nearest_rank_for_small_series() -> None:
    assert _nearest_rank([1.0, 2.0, 3.0, 100.0]) == 100.0


def test_missing_evidence_requires_uncertainty() -> None:
    case = load_case(ROOT / "data/synthetic/ai-operational-v2/OP-04-input.json")
    output = baseline(case)
    assert output["status"] == "insufficient_evidence"
    assert output["open_questions"]
    output["status"] = "completed"
    output["open_questions"] = []
    with pytest.raises(OperationalPoCError, match="contexto insuficiente"):
        validate_output(case, output)


def test_operational_manifest_is_checked_with_project_assets() -> None:
    manifest_path = ROOT / "data/synthetic/ai-operational-v2/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_operational_manifest(manifest_path, manifest)
