from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai_poc_evaluation import (  # noqa: E402, I001
    ContractValidationError,
    evaluate_output,
    run_baseline,
    validate_contract_pair,
    verify_manifest,
)


SCHEMAS = ROOT / "docs" / "schemas"
DATASET = ROOT / "data" / "synthetic" / "ai-poc-evaluation"


def _load(relative_path: str) -> dict:
    return json.loads((DATASET / relative_path).read_text(encoding="utf-8"))


def test_rejects_output_reference_absent_from_input() -> None:
    input_payload = _load("quality/QD-02-input.json")
    output_payload = run_baseline("quality", input_payload)
    output_payload["diagnoses"][0]["evidence_ids"] = ["invented-evidence"]

    with pytest.raises(ContractValidationError, match="unknown evidence"):
        validate_contract_pair("quality", input_payload, output_payload, SCHEMAS)


def test_rejects_sensitive_field_at_any_depth() -> None:
    input_payload = _load("operational/OP-02-input.json")
    input_payload["pending_items"][0]["authorization"] = "Bearer synthetic"
    output_payload = run_baseline("operational", _load("operational/OP-02-input.json"))

    with pytest.raises(ContractValidationError, match="sensitive field"):
        validate_contract_pair("operational", input_payload, output_payload, SCHEMAS)


def test_rejects_additional_payload_field() -> None:
    input_payload = _load("operational/OP-02-input.json")
    input_payload["pending_items"][0]["payload"] = {"uncontrolled": True}
    output_payload = run_baseline("operational", _load("operational/OP-02-input.json"))

    with pytest.raises(ContractValidationError, match="Additional properties"):
        validate_contract_pair("operational", input_payload, output_payload, SCHEMAS)


@pytest.mark.parametrize(
    "kind, case_id",
    [
        ("quality", "QD-01"),
        ("quality", "QD-02"),
        ("quality", "QD-03"),
        ("quality", "QD-04"),
        ("operational", "OP-01"),
        ("operational", "OP-02"),
        ("operational", "OP-03"),
        ("operational", "OP-04"),
    ],
)
def test_baseline_is_schema_valid_and_matches_frozen_gold(
    kind: str, case_id: str
) -> None:
    input_payload = _load(f"{kind}/{case_id}-input.json")
    gold_payload = _load(f"{kind}/{case_id}-gold.json")

    output_payload = run_baseline(kind, input_payload)
    metrics = evaluate_output(
        kind, input_payload, output_payload, gold_payload, SCHEMAS
    )

    assert metrics == {
        "schema_valid": True,
        "evidence_references_valid": True,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }


def test_frozen_dataset_manifest_matches_files() -> None:
    assert verify_manifest(DATASET) == []
