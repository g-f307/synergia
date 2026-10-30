"""Named constrained-decoding experiment, never an output repair or fallback."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from jsonschema import Draft202012Validator

import ai_quality_diagnosis as quality
from ai_poc_foundation import OllamaRuntime, PoCFoundationError

GUIDED_FIELDS = ["status", "open_questions_bounds"]
EVIDENCE_SCHEMA = (
    quality.ROOT / "docs/schemas/ai-reevaluation-quality-context.schema.json"
)


def evidence_context(context: dict) -> dict:
    quality.validate_document(context, "input")
    keys = ("case_id", "source", "file_sha256", "counts", "occurrences")
    projection = {
        "projection_version": "1.0.0",
        **{key: deepcopy(context[key]) for key in keys},
    }
    if not Draft202012Validator(json.loads(EVIDENCE_SCHEMA.read_text())).is_valid(
        projection
    ):
        raise PoCFoundationError("invalid_evidence_projection")
    return projection


def policy_schema(context: dict) -> dict:
    quality.validate_document(context, "input")
    uncertain = any(
        item["code"] == "missing_reference_data"
        or quality.CATEGORIES.get(item["code"], "unknown") == "unknown"
        for item in context["occurrences"]
    )
    output = quality.schema("output")
    output["properties"]["status"] = {
        "const": "insufficient_evidence" if uncertain else "completed"
    }
    questions = output["properties"]["open_questions"]
    questions["minItems" if uncertain else "maxItems"] = 1 if uncertain else 0
    return output


class GuidedQualityRuntime(OllamaRuntime):
    """Only deterministic status policy/question bounds are constrained.

    Categories, codes, diagnoses, confidence, evidence selection and free text
    remain model tasks, validated/scored unchanged. No gold or fixture is read.
    """

    guidance_failure: str | None = None
    rejected_response_sha256: str | None = None
    evidence_only_context = False

    def generate(self, prompt: str, *, model: str) -> tuple[str, int]:
        self.request_sha256 = None
        self.response_metrics = {}
        self.response_done_reason = None
        self.guidance_failure = None
        self.rejected_response_sha256 = None
        header, separator, raw_context = prompt.rpartition("\nCONTEXTO:\n")
        instructions, schema_separator, _ = header.partition("\nSCHEMA:\n")
        if not separator or not schema_separator:
            raise PoCFoundationError("guidance_requires_quality_context")
        try:
            context = json.loads(raw_context)
        except json.JSONDecodeError as exc:
            raise PoCFoundationError("guidance_requires_quality_context") from exc
        self.output_schema = policy_schema(context)
        if self.evidence_only_context:
            raw_context = json.dumps(evidence_context(context), ensure_ascii=False)
        # Give the model the same schema used by constrained decoding.
        request = (
            instructions
            + "\nSCHEMA:\n"
            + json.dumps(self.output_schema)
            + "\nCONTEXTO:\n"
            + raw_context
        )
        raw, count = super().generate(request, model=model)
        try:
            output = json.loads(raw)
            valid = Draft202012Validator(self.output_schema).is_valid(output)
        except json.JSONDecodeError:
            valid = False
        if not valid:
            self.guidance_failure = "guided_schema_violation"
            self.rejected_response_sha256 = hashlib.sha256(raw.encode()).hexdigest()
            raise PoCFoundationError("guided_schema_violation")
        return raw, count
