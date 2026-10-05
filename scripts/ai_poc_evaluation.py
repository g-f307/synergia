#!/usr/bin/env python3
"""Validate and evaluate the frozen synthetic AI PoC contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SENSITIVE_FIELDS = {
    "authorization",
    "cookie",
    "password",
    "path",
    "secret",
    "storage_path",
    "token",
    "user_agent",
}


class ContractValidationError(ValueError):
    """Raised when a PoC payload violates schema or evidence constraints."""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_paths(kind: str, schema_dir: Path) -> tuple[Path, Path]:
    prefix = "ai-quality-diagnosis" if kind == "quality" else "ai-operational-summary"
    return (
        schema_dir / f"{prefix}-input.schema.json",
        schema_dir / f"{prefix}-output.schema.json",
    )


def _validate_schema(payload: dict[str, Any], schema_path: Path) -> None:
    validator = Draft202012Validator(
        _read_json(schema_path), format_checker=FormatChecker()
    )
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        raise ContractValidationError(f"{location}: {error.message}")


def _reject_sensitive_fields(value: Any, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in SENSITIVE_FIELDS:
                raise ContractValidationError(f"sensitive field '{key}' at {location}")
            _reject_sensitive_fields(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_fields(child, f"{location}[{index}]")


def _input_evidence_ids(kind: str, payload: dict[str, Any]) -> set[str]:
    if kind == "quality":
        return {item["evidence_id"] for item in payload["occurrences"]}
    return {
        item["evidence_id"]
        for collection in ("pending_items", "classifications", "events")
        for item in payload[collection]
    }


def _output_evidence_ids(kind: str, payload: dict[str, Any]) -> set[str]:
    collection = "diagnoses" if kind == "quality" else "findings"
    return {
        evidence_id
        for item in payload[collection]
        for evidence_id in item["evidence_ids"]
    }


def validate_contract_pair(
    kind: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    schema_dir: Path,
) -> None:
    input_schema, output_schema = _schema_paths(kind, schema_dir)
    _reject_sensitive_fields(input_payload)
    _reject_sensitive_fields(output_payload)
    _validate_schema(input_payload, input_schema)
    _validate_schema(output_payload, output_schema)
    if input_payload["case_id"] != output_payload["case_id"]:
        raise ContractValidationError("input and output case_id differ")
    unknown = _output_evidence_ids(kind, output_payload) - _input_evidence_ids(
        kind, input_payload
    )
    if unknown:
        raise ContractValidationError(
            f"unknown evidence reference(s): {sorted(unknown)}"
        )


def run_baseline(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind == "quality":
        grouped: dict[str, list[dict[str, Any]]] = {}
        for occurrence in payload["occurrences"]:
            grouped.setdefault(occurrence["code"], []).append(occurrence)
        diagnoses = [
            {
                "diagnosis_id": f"quality:{code}",
                "occurrence_code": code,
                "summary": items[0]["reason"],
                "impact": "Ocorrência determinística requer validação humana.",
                "verification_action": "Conferir a origem e a regra indicada.",
                "evidence_ids": [item["evidence_id"] for item in items],
            }
            for code, items in sorted(grouped.items())
        ]
        insufficient = any(
            item["code"] == "missing_reference_data"
            for item in payload["occurrences"]
        )
        return {
            "schema_version": "1.1.0",
            "case_id": payload["case_id"],
            "status": "insufficient_evidence" if insufficient else "completed",
            "diagnoses": diagnoses,
            "open_questions": (
                ["Qual fonte de referência autorizada deve ser usada?"]
                if insufficient
                else []
            ),
        }

    findings = [
        {
            "finding_id": f"pending:{item['id']}",
            "title": f"Pendência {item['id']}",
            "severity": "warning",
            "statement": item["reason"],
            "evidence_ids": [item["evidence_id"]],
        }
        for item in payload["pending_items"]
    ]
    insufficient = payload["execution"]["lifecycle"] == "partial" and not any(
        payload[name] for name in ("pending_items", "classifications", "events")
    )
    return {
        "schema_version": "1.1.0",
        "case_id": payload["case_id"],
        "status": "insufficient_evidence" if insufficient else "completed",
        "summary": f"Execução em estado {payload['execution']['status']}.",
        "findings": findings,
        "open_questions": (
            ["Quais evidências autorizadas estão disponíveis para a execução?"]
            if insufficient
            else []
        ),
        "human_next_steps": ["Validar os achados com as evidências exibidas."],
    }


def evaluate_output(
    kind: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    gold_payload: dict[str, Any],
    schema_dir: Path,
) -> dict[str, Any]:
    validate_contract_pair(kind, input_payload, output_payload, schema_dir)
    validate_contract_pair(kind, input_payload, gold_payload, schema_dir)
    collection = "diagnoses" if kind == "quality" else "findings"
    identifier = "diagnosis_id" if kind == "quality" else "finding_id"
    actual = {item[identifier] for item in output_payload[collection]}
    expected = {item[identifier] for item in gold_payload[collection]}
    correct = len(actual & expected)
    precision = correct / len(actual) if actual else float(not expected)
    recall = correct / len(expected) if expected else float(not actual)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "schema_valid": True,
        "evidence_references_valid": True,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def verify_manifest(dataset_dir: Path) -> list[str]:
    manifest = _read_json(dataset_dir / "evaluation-manifest.json")
    failures = []
    for relative_path, expected in manifest["sha256"].items():
        actual = hashlib.sha256((dataset_dir / relative_path).read_bytes()).hexdigest()
        if actual != expected:
            failures.append(relative_path)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("quality", "operational"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--schemas", type=Path, default=Path("docs/schemas"))
    args = parser.parse_args()
    input_payload = _read_json(args.input)
    output_payload = run_baseline(args.kind, input_payload)
    args.output.write_text(
        json.dumps(output_payload, indent=2) + "\n", encoding="utf-8"
    )
    validate_contract_pair(args.kind, input_payload, output_payload, args.schemas)
    if args.gold:
        metrics = evaluate_output(
            args.kind,
            input_payload,
            output_payload,
            _read_json(args.gold),
            args.schemas,
        )
        print(json.dumps(metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
