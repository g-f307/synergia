from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ai_assistance_contract import (
    AiAssistanceRequest,
    AiAssistanceResponse,
    contract_examples,
    serialize_context,
    validate_raw_response,
)
from app.main import create_app

pytestmark = pytest.mark.security


def validate(payload, refs=()):
    return AiAssistanceResponse.model_validate_json(
        json.dumps(payload), context={"evidence_refs": frozenset(refs)}
    )


@pytest.mark.parametrize("state", contract_examples())
def test_examples(state):
    assert validate(contract_examples()[state]).state == state


@pytest.mark.parametrize("field", ["prompt", "question", "model", "facts", "text"])
def test_free_form_input_rejected(field):
    assert AiAssistanceRequest.model_validate_json("{}").model_dump() == {}
    with pytest.raises(ValidationError):
        AiAssistanceRequest.model_validate_json(json.dumps({field: "synthetic"}))


@pytest.mark.parametrize("value", ["null", "[]", '""', "false", "1"])
def test_request_requires_object(value):
    with pytest.raises(ValidationError):
        AiAssistanceRequest.model_validate_json(value)


def test_http_request_rejects_prompt_with_422():
    application = FastAPI()

    @application.post("/contract")
    def contract(payload: AiAssistanceRequest | None = None):
        return {}

    with TestClient(application) as client:
        assert client.post("/contract").status_code == 200
        assert client.post("/contract", json={}).status_code == 200
        assert client.post("/contract", json={"prompt": "synthetic"}).status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "complete"),
        ("summary", "x" * 601),
        ("summary", ""),
        ("summary", 1),
        ("summary", "<b>Texto</b>"),
        ("summary", "[Evidência](https://example.invalid)"),
        ("summary", "Execute o reprocessamento."),
        ("summary", "Delete the execution."),
        ("summary", "```bash```"),
        ("summary", "Texto\u200boculto"),
        ("summary", "ｅｘｅｃｕｔｅ o comando"),
        ("human_checks", ["Conferência necessária."] * 4),
        ("human_checks", ["Clique no botão."]),
        ("limitations", None),
        ("limitations", ["Limitação."] * 6),
        ("created_at", "2026-11-14T00:00:00"),
        ("assistance_id", "not-a-uuid"),
        ("execution_id", 1),
        ("extra", "forbidden"),
    ],
)
def test_response_rejects_invalid_fields(field, value):
    example = copy.deepcopy(contract_examples()["ready"])
    example[field] = value
    with pytest.raises(ValidationError):
        validate(example)


def finding(refs=None):
    return {
        "title": "Divergência registrada",
        "explanation": "Há uma divergência registrada.",
        "evidence_refs": ["DIV-01"] if refs is None else refs,
    }


@pytest.mark.parametrize(
    "refs,allowed",
    [
        (["DIV-01"], []),
        (["DIV-02"], ["DIV-01"]),
        (["https://example.invalid"], ["https://example.invalid"]),
        ([], []),
        (["DIV-01", "DIV-01"], ["DIV-01"]),
        ([f"DIV-{i}" for i in range(11)], [f"DIV-{i}" for i in range(11)]),
    ],
)
def test_evidence_must_be_unique_opaque_and_in_context(refs, allowed):
    example = contract_examples()["ready"]
    example["findings"] = [finding(refs)]
    with pytest.raises(ValidationError):
        validate(example, allowed)


def test_findings_limits_and_positive_grounding():
    example = contract_examples()["ready"]
    example["summary"] = "a" * 600
    example["findings"] = [finding()] * 5
    assert len(validate(example, ["DIV-01"]).findings) == 5
    example["findings"].append(finding())
    with pytest.raises(ValidationError):
        validate(example, ["DIV-01"])
    example["findings"] = [finding()]
    example["findings"][0]["title"] = "a" * 121
    with pytest.raises(ValidationError):
        validate(example, ["DIV-01"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("contract_version", "2.0.0"),
        ("origin", "agent"),
        ("origin", "model"),
        ("context_hash", "bad"),
        ("prompt_hash", "bad"),
        ("digest", "latest"),
        ("model", "model-without-digest"),
        ("timings", {"context_ms": 1, "generation_ms": 1, "total_ms": 1}),
        ("timings", {"context_ms": 0, "generation_ms": 0, "total_ms": 30001}),
        ("timings", {"context_ms": "0", "generation_ms": 0, "total_ms": 0}),
        ("timings", {"context_ms": -1, "generation_ms": 0, "total_ms": 0}),
        ("extra", "forbidden"),
    ],
)
def test_provenance_is_strict_and_coherent(field, value):
    example = contract_examples()["ready"]
    example["provenance"][field] = value
    with pytest.raises(ValidationError):
        validate(example)


@pytest.mark.parametrize("state", ["insufficient_evidence", "unavailable", "rejected"])
def test_fallback_cannot_publish_model_findings(state):
    example = contract_examples()[state]
    example["limitations"] = []
    with pytest.raises(ValidationError):
        validate(example)
    example = contract_examples()[state]
    example["findings"] = [finding()]
    with pytest.raises(ValidationError):
        validate(example, ["DIV-01"])


def test_limits_count_utf8_bytes():
    assert len(validate_raw_response(b"a" * 8192)) == 8192
    with pytest.raises(ValueError):
        validate_raw_response(b"a" * 8193)
    with pytest.raises(ValueError):
        validate_raw_response(b"\xff")
    assert len(serialize_context({"a": "x" * 8184})) == 8192
    with pytest.raises(ValueError):
        serialize_context({"a": "x" * 8185})
    with pytest.raises(ValueError):
        serialize_context({"a": "á" * 4093})


def test_openapi_snapshot():
    schema = create_app().openapi()
    contract = schema["x-ai-assistance"]
    names = {
        "AiAssistanceRequest",
        "AiAssistanceResponse",
        "AiAssistanceFinding",
        "AiAssistanceProvenance",
        "AiAssistanceTimings",
        "AiAssistanceCapability",
    }
    actual = {
        "contract": contract,
        "schemas": {
            key: value
            for key, value in schema["components"]["schemas"].items()
            if key in names
        },
    }
    expected = Path(__file__).parent / "fixtures/ai_assistance_openapi_1_0_0.json"
    assert actual == json.loads(expected.read_text())
    assert "/executions/{execution_id}/ai-assistance" not in schema["paths"]
