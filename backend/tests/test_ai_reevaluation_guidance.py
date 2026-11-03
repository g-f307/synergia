"""Constrained policy fields are explicit and never credited as model reasoning."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import ai_quality_diagnosis as quality  # noqa: E402
import ai_reevaluation as runner  # noqa: E402
from ai_poc_foundation import PoCFoundationError  # noqa: E402
from ai_reevaluation_guidance import GuidedQualityRuntime, policy_schema  # noqa: E402
from evaluate_ai_quality import score  # noqa: E402


def context(case):
    return quality.build_context(
        ROOT / f"data/synthetic/ai-quality-v3/development/{case}.csv",
        source="N-FP",
        case_id=case,
    )


def test_policy_constraint_preserves_classification_as_a_model_task():
    c = context("QD3-D02")
    schema = policy_schema(c)
    output = quality.baseline(c)
    assert Draft202012Validator(schema).is_valid(output)
    overcautious = copy.deepcopy(output)
    overcautious.update(status="insufficient_evidence", open_questions=["Qual valor?"])
    assert not Draft202012Validator(schema).is_valid(overcautious)
    # Category remains a model task; schema cannot force a correct score.
    output["diagnoses"][0]["category"] = "reference"
    assert Draft202012Validator(schema).is_valid(output)
    projection = {
        "status": output["status"],
        "diagnoses": [
            {key: item[key] for key in ("occurrence_code", "category", "evidence_ids")}
            for item in output["diagnoses"]
        ],
    }
    measured = score(
        c,
        {
            "expected": [
                ["required_field", "completeness", 2, "A"],
                ["invalid_quantity", "format", 2, "B"],
            ],
            "status": "completed",
        },
        {
            "diagnostic_projection": projection,
            "schema_valid": True,
            "outcome": "succeeded",
        },
    )
    assert measured["fp"] == measured["fn"] == 1


def test_unknown_policy_requires_question_and_only_declared_fields_are_narrowed():
    c = context("QD3-D03")
    original = quality.schema("output")
    constrained = policy_schema(c)
    valid = quality.baseline(c)
    assert Draft202012Validator(constrained).is_valid(valid)
    valid["open_questions"] = []
    assert not Draft202012Validator(constrained).is_valid(valid)
    assert original["properties"]["diagnoses"] == constrained["properties"]["diagnoses"]
    assert original["properties"]["case_id"] == constrained["properties"]["case_id"]


@pytest.mark.parametrize("case", ["QD3-D01", "QD3-D02", "QD3-D03"])
def test_guidance_validates_generated_output_and_never_repairs_it(case, monkeypatch):
    c = context(case)
    expected = quality.baseline(c)
    seen = {}

    def generate(self, prompt, *, model):
        seen["schema"] = self.output_schema
        supplied = json.loads(prompt.split("\nSCHEMA:\n")[1].split("\nCONTEXTO:\n")[0])
        assert supplied == self.output_schema
        assert json.loads(prompt.split("\nCONTEXTO:\n")[1]) == c
        return json.dumps(expected), 100

    monkeypatch.setattr(runner.OllamaRuntime, "generate", generate)
    runtime = GuidedQualityRuntime(runner.LocalModelConfig("test"))
    raw, count = runtime.generate(
        "instructions\nSCHEMA:\n{}\nCONTEXTO:\n" + json.dumps(c), model="test"
    )
    assert json.loads(raw) == expected
    assert count == 100
    assert seen["schema"]["properties"]["status"]["const"] == expected["status"]
    assert runtime.guidance_failure is None
    expected["status"] = (
        "insufficient_evidence" if expected["status"] == "completed" else "completed"
    )
    with pytest.raises(PoCFoundationError, match="guided_schema_violation"):
        runtime.generate(
            "instructions\nSCHEMA:\n{}\nCONTEXTO:\n" + json.dumps(c), model="test"
        )
    assert runtime.guidance_failure == "guided_schema_violation"
    assert len(runtime.rejected_response_sha256) == 64


def test_guidance_fails_closed_without_a_valid_context(monkeypatch):
    monkeypatch.setattr(
        runner.OllamaRuntime,
        "generate",
        lambda *a, **k: pytest.fail("No call permitted"),
    )
    runtime = GuidedQualityRuntime(runner.LocalModelConfig("test"))
    with pytest.raises(PoCFoundationError):
        runtime.generate("untrusted input", model="test")


def test_guidance_configuration_cannot_be_used_as_an_operational_agent():
    c = runner.configuration(
        ROOT
        / "scripts/ai_reevaluation_configs/quality-instruct-guided-development.json"
    )
    c["kind"] = "operational"
    with pytest.raises(PoCFoundationError, match="guidance_requires_quality_agent"):
        runner.validate_configuration(c)


def test_guided_run_counts_a_server_violation_as_failure(tmp_path, monkeypatch):
    class Sampler:
        failure = None

        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def report(self):
            return {}

    c = runner.configuration(
        ROOT
        / "scripts/ai_reevaluation_configs/quality-instruct-guided-development.json"
    )

    def frozen(value):
        return runner.freeze(value, metadata=lambda _: {}, identity=lambda: {})

    def wrong_response(self, prompt, *, model):
        current = json.loads(prompt.split("\nCONTEXTO:\n")[1])
        result = quality.baseline(current)
        result["status"] = (
            "completed"
            if result["status"] == "insufficient_evidence"
            else "insufficient_evidence"
        )
        return json.dumps(result), 5

    monkeypatch.setattr(runner.OllamaRuntime, "generate", wrong_response)
    state = runner.run(
        frozen(c),
        tmp_path / "run",
        freezer=frozen,
        allow_inference=True,
        sampler_factory=Sampler,
        loaded_models=lambda: [],
    )
    assert state["complete"]
    assert state["failed_measured_attempts"] == 8
    assert all(a["failure"] == "guided_schema_violation" for a in state["attempts"])
    summary = runner.summarize_run(state)
    assert summary["accepted_rate"] == 0
    assert summary["deterministic_guided_fields"] == ["status", "open_questions_bounds"]
    assert summary["case_correct_scope"] == "pipeline_with_deterministic_status"


def test_evidence_projection_excludes_valid_row_values_and_preserves_original_context():
    from ai_reevaluation_guidance import evidence_context

    original = context("QD3-D02")
    original["normalized_records"][0]["quantities"][0]["value"] = 987654.125
    projection = evidence_context(original)
    assert "normalized_records" not in projection
    assert "987654.125" not in json.dumps(projection)
    assert projection["occurrences"] == original["occurrences"]
    assert projection["counts"] == original["counts"]
    projection["counts"]["errors"] = 999
    assert original["counts"]["errors"] == 2


def test_evidence_runtime_sends_projection_but_keeps_output_contract(monkeypatch):
    original = context("QD3-D02")
    original["normalized_records"][0]["quantities"][0]["value"] = 987654.125
    expected = quality.baseline(original)
    c = runner.configuration(
        ROOT
        / "scripts/ai_reevaluation_configs"
        / "quality-instruct-evidence-guided-confirmation-development.json"
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return json.dumps(
                {
                    "response": json.dumps(expected),
                    "eval_count": 20,
                    "done_reason": "stop",
                }
            ).encode()

    class Opener:
        def open(self, request, timeout):
            payload = json.loads(request.data)
            prompt = payload["prompt"]
            projection = json.loads(prompt.split("\nCONTEXTO:\n")[1])
            assert projection["projection_version"] == "1.0.0"
            assert "schema_version" not in projection
            assert "normalized_records" not in projection
            assert "987654.125" not in prompt
            assert projection["case_id"] == original["case_id"]
            return Response()

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    runtime = runner.make_runtime(c)
    raw, _ = runtime.generate(
        "instructions\nSCHEMA:\n{}\nCONTEXTO:\n" + json.dumps(original),
        model=c["model"],
    )
    assert json.loads(raw) == expected
    assert json.loads(raw)["schema_version"] == "2.0.0"
    assert original["normalized_records"][0]["quantities"][0]["value"] == 987654.125


def test_evidence_projection_option_cannot_be_silently_ignored():
    c = runner.configuration(
        ROOT
        / "scripts/ai_reevaluation_configs"
        / "quality-instruct-evidence-guided-confirmation-development.json"
    )
    c["architecture"] = "free_contract"
    with pytest.raises(
        PoCFoundationError, match="evidence_projection_requires_guided_quality"
    ):
        runner.validate_configuration(c)
