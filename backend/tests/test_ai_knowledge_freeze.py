"""Offline freeze tests; reserved inputs are serialized, never inferred/labeled."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ai_knowledge import DATA, KnowledgeError, inputs, project, read  # noqa: E402
from freeze_ai_knowledge import choose, matrix, reader_body  # noqa: E402
from run_ai_knowledge_development import prepare  # noqa: E402


def task(complete, coverage, high=0):
    return {
        "complete_case_accuracy": complete,
        "coverage": coverage,
        "precision": 1,
        "high_errors_exposed": high,
    }


def test_policy_selection_does_not_reward_abstention_or_size_over_accuracy():
    groups = {
        "qwen3:4b-instruct/historical/typed_checklist": {
            "tasks": {
                "supported_and_possible": task(0.8, 0.9),
                "supported_only": task(0.5, 0.5),
            },
            "mean_seconds": 2,
        },
        "qwen3:8b/recommended/typed_checklist": {
            "tasks": {
                "supported_and_possible": task(0.7, 0.8),
                "supported_only": task(0.4, 0.4),
            },
            "mean_seconds": 6,
        },
    }
    report = {"kind": "validation", "split": "validation", "groups": groups}
    configs, best = choose(report)
    assert best == "qwen3:4b-instruct"
    assert configs[best]["policy"] == "supported_and_possible"
    groups["qwen3:4b-instruct/historical/typed_checklist"]["tasks"][
        "supported_and_possible"
    ]["high_errors_exposed"] = 1
    configs, _ = choose(report)
    assert configs[best]["policy"] == "supported_only"


def test_development_cannot_be_used_as_final_validation_selection():
    with pytest.raises(KnowledgeError, match="completed_validation"):
        choose({"kind": "confirm", "split": "development"})


def test_reserved_matrix_is_deterministic_gold_free_and_not_execution():
    configs = {
        m: {"profile": "historical", "variant": "typed_checklist"}
        for m in ["qwen3:4b-instruct", "qwen3:8b"]
    }
    result = matrix(configs)
    assert result == matrix(configs)
    assert result["inference_executed"] is False
    assert len(result["cases"]) == 48
    assert len(result["generation_preselected_cases"]) == 24
    assert len(set(result["generation_preselected_cases"])) == 24
    assert all(len(c["reader_bodies_sha256"]) == 60 for c in result["cases"].values())
    for order in result["execution_order"].values():
        assert set(order["cases"]) == set(result["cases"])
    assert result["execution_order"]["125"]["models"] == list(configs)
    assert result["execution_order"]["126"]["models"] == list(reversed(configs))
    for forbidden in ["expected_status", "relevant_cards", "semantic_annotations"]:
        assert forbidden not in str(result)


def test_frozen_serializer_matches_the_executed_development_contract(tmp_path):
    prepare("calibration", tmp_path / "calibration")
    request = read(tmp_path / "calibration/plan.json")["requests"][0]
    case = next(c for c in inputs("development") if c["case_id"] == request["case_id"])
    card = next(
        c for c in read(DATA / "knowledge.json") if c["id"] == request["card_id"]
    )
    config = {"profile": request["profile"], "variant": request["variant"]}
    assert (
        reader_body(
            request["body"]["model"], config, card, project(case), request["seed"]
        )
        == request["body"]
    )
