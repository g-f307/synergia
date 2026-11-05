"""Read-only quality explanation PoC; deterministic facts and closed language."""

from __future__ import annotations

import hashlib
import json
import tracemalloc
from collections import defaultdict
from pathlib import Path

from ai_poc_foundation import LocalRuntimeTimeout, PoCFoundationError
from ai_quality_diagnosis import CATEGORIES, DiagnosisError, validate_document
from app import ai_quality_core as shared
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "scripts/ai_poc_prompts/quality-explanation-v1.txt"
CAUSE_LIMIT = shared.CAUSE_LIMIT
VALUE_LIMIT = shared.VALUE_LIMIT
baseline = shared.baseline
language = shared.language


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def contract(kind: str) -> dict:
    return read(ROOT / f"docs/schemas/ai-quality-explanation-v1-{kind}.schema.json")


def positioned(value) -> dict:
    return (
        {"state": "known", "value": value}
        if value is not None
        else {"state": "not_provided"}
    )


def project(context: dict, headers: list, rows: list) -> dict:
    """Project pipeline occurrences, never evaluation labels or inferred values.

    headers/rows come only from the hash-verified synthetic scenario. Missing
    cell values and values not exposed by this projection have distinct states.
    A column letter is never used as the field name or cell value.
    """
    validate_document(context, "input")
    grouped = defaultdict(list)
    seen = set()
    for occurrence in context["occurrences"]:
        ref = occurrence["evidence_id"]
        if ref in seen:
            raise DiagnosisError("duplicate_input_evidence")
        seen.add(ref)
        column = occurrence["column"]
        index = None
        if isinstance(column, str) and column.isalpha() and column.isupper():
            index = 0
            for letter in column:
                index = index * 26 + ord(letter) - ord("A") + 1
            index -= 1
        elif column in headers:
            index = headers.index(column)
        field = headers[index] if index is not None and index < len(headers) else None
        row = occurrence["row"]
        available = (
            index is not None
            and row is not None
            and 2 <= row < len(rows) + 2
            and index < len(rows[row - 2])
        )
        value = rows[row - 2][index] if available else None
        missing = available and value in (None, "")
        grouped[occurrence["code"]].append(
            {
                "evidence_id": ref,
                "severity": occurrence["severity"],
                "reason": occurrence["reason"],
                "field": positioned(field),
                "column": positioned(column),
                "row": positioned(row),
                "sheet": positioned(occurrence["sheet"]),
                "known_value": {"state": "observed", "value": value}
                if available and not missing
                else {"state": "unavailable"},
                "unknown_value": {
                    "state": "missing"
                    if missing
                    else ("not_applicable" if available else "not_exposed")
                },
            }
        )
    envelope = {
        "schema_version": "1.0.0",
        "case_id": context["case_id"],
        "groups": [
            {
                "code": code,
                "category": CATEGORIES.get(code, "unknown"),
                "causal_evidence": "not_provided",
                "occurrences": items,
            }
            for code, items in sorted(grouped.items())
        ],
    }
    validate_projection(context, envelope)
    return envelope


def validate_projection(context: dict, envelope: dict) -> None:
    if not Draft202012Validator(contract("input")).is_valid(envelope):
        raise DiagnosisError("invalid_envelope_schema")
    expected = {x["evidence_id"]: x for x in context["occurrences"]}
    actual = {}
    codes = set()
    if envelope["case_id"] != context["case_id"]:
        raise DiagnosisError("case_mismatch")
    for group in envelope["groups"]:
        if group["code"] in codes:
            raise DiagnosisError("duplicate_diagnosis")
        codes.add(group["code"])
        if group["category"] != CATEGORIES.get(group["code"], "unknown"):
            raise DiagnosisError("category_changed")
        for item in group["occurrences"]:
            ref = item["evidence_id"]
            if ref in actual:
                raise DiagnosisError("duplicate_projected_evidence")
            original = expected.get(ref)
            if original is None or any(
                [
                    original["code"] != group["code"],
                    original["severity"] != item["severity"],
                    original["reason"] != item["reason"],
                    any(
                        positioned(original[k]) != item[k]
                        for k in ("sheet", "row", "column")
                    ),
                ]
            ):
                raise DiagnosisError("pipeline_fact_changed")
            actual[ref] = item
    if actual.keys() != expected.keys():
        raise DiagnosisError("occurrence_loss")


def validate_text(group: dict, output) -> None:
    try:
        shared.validate_text(group, output)
    except shared.ExplanationError as exc:
        raise DiagnosisError(str(exc)) from exc


class RuntimeAdapter:
    def __init__(self, runtime):
        self.runtime = runtime

    def generate(self, prompt, *, model):
        try:
            return self.runtime.generate(prompt, model=model)
        except LocalRuntimeTimeout as exc:
            raise TimeoutError from exc
        except PoCFoundationError as exc:
            raise shared.RuntimeUnavailable from exc


def explain(group: dict, runtime=None, *, model: str = "baseline") -> dict:
    tracemalloc.start()
    try:
        result = shared.explain(
            group, RuntimeAdapter(runtime) if runtime else None, model=model
        )
        result["python_peak_memory_bytes"] = tracemalloc.get_traced_memory()[1]
        result["runtime_metrics"] = getattr(runtime, "response_metrics", {}).copy()
        return result
    finally:
        tracemalloc.stop()
