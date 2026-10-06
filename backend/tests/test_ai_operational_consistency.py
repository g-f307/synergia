from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate_ai_operational as evaluation  # noqa: E402


@pytest.mark.parametrize(
    ("scenario", "repetitions", "expected"),
    [
        ("invalid", 3, 0),
        ("mixed", 3, 0),
        ("identical", 3, 1),
        ("different", 3, 0),
        ("reordered", 3, 1),
        ("identical", 1, None),
    ],
)
def test_consistency_uses_valid_outputs_not_equal_scores(
    tmp_path, monkeypatch, scenario, repetitions, expected
):
    attempts = {}

    class Runtime:
        def generate(self, prompt, *, model):
            case_id = prompt.split("CASE_ID: ", 1)[1].splitlines()[0]
            index = attempts.get(case_id, 0)
            attempts[case_id] = index + 1
            if scenario == "invalid" or (scenario == "mixed" and index == 1):
                return "invalid json", 10
            case = evaluation.load_case(
                ROOT / "data/synthetic/ai-operational-v2" / f"{case_id}-input.json"
            )
            output = evaluation.baseline(case)
            if scenario == "different":
                output["summary"] = f"Resumo alternativo {index}."
            if scenario == "reordered" and index == 1:
                output = dict(reversed(list(output.items())))
            return json.dumps(output), 10

    monkeypatch.setattr(evaluation, "OllamaRuntime", lambda config, **kwargs: Runtime())
    destination = tmp_path / "evaluation.json"
    result = evaluation.main(
        [
            "--mode",
            "both",
            "--repetitions",
            str(repetitions),
            "--output",
            str(destination),
        ]
    )
    report = json.loads(destination.read_text())
    assert result == int(scenario in {"invalid", "mixed"})
    assert report["summary"]["agent"]["consistency_rate"] == expected
    assert report["summary"]["agent"]["consistency_cases"] == (
        4 if repetitions >= 2 else 0
    )
    assert report["summary"]["baseline"]["consistency_rate"] is None
    records = [r for r in report["records"] if r["mode"] == "agent"]
    assert len(records) == 4 * repetitions
    assert all(r["output_sha256"] is None for r in records if r["failure"])
    if scenario == "different":
        case_records = [r for r in records if r["case_id"] == "OP-02"]
        assert all(
            r["score"]["f1"] == case_records[0]["score"]["f1"] for r in case_records
        )
        assert len({r["output_sha256"] for r in case_records}) == repetitions
