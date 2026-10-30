"""Verify the proposed corpus and protocol, without evaluating a real model."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ai_operational_summary import load_case, validate_output  # noqa: E402
from ai_quality_diagnosis import build_context  # noqa: E402
from build_ai_quality_dataset import verify  # noqa: E402

QUALITY = ROOT / "data/synthetic/ai-quality-v3"
OPERATIONAL = ROOT / "data/synthetic/ai-operational-v3"
ANNOTATIONS = json.loads((QUALITY / "scenarios.json").read_text())
OPERATIONS = json.loads((OPERATIONAL / "manifest.json").read_text())
PROTOCOL = json.loads((ROOT / "docs/ai-reevaluation-protocol.json").read_text())


def test_protocol_requires_review_and_freeze_before_evaluation():
    assert PROTOCOL["issue"] == 148
    assert PROTOCOL["status"] in {
        "draft_pending_review",
        "prepared",
        "calibrating",
        "frozen",
    }
    review = PROTOCOL["human_review"]
    assert review["status"] in {"pending", "approved"}
    if review["status"] == "pending":
        assert all(
            review[key] is None for key in ("reviewer", "reviewed_on", "decision")
        )
        assert PROTOCOL["evaluation"]["status"] == "not_started"
        assert PROTOCOL["decision"]["quality"] == "not_decided"
        assert PROTOCOL["decision"]["operational"] == "not_decided"
    else:
        assert all(review[key] for key in ("reviewer", "reviewed_on", "decision"))
    if PROTOCOL["evaluation"]["status"] != "not_started":
        assert PROTOCOL["status"] == "frozen"
        assert review["status"] == "approved"
        assert PROTOCOL["evaluation"]["final_configurations"]
    assert PROTOCOL["evaluation"]["requires_approved_gold"] is True
    assert PROTOCOL["evaluation"]["requires_frozen_configuration"] is True
    assert PROTOCOL["evaluation"]["retain_failed_attempts"] is True
    assert PROTOCOL["evaluation"]["repetitions_per_configuration"] >= 3
    assert PROTOCOL["decision"]["product_integration_authorized"] is False


def test_corpus_counts_splits_and_pending_gold_match_the_protocol():
    expected = {
        "quality": {"development": 4, "evaluation": 12},
        "operational": {"development": 4, "evaluation": 8},
    }
    for kind, data in (("quality", ANNOTATIONS), ("operational", OPERATIONS)):
        ids = [case["case_id"] for case in data["cases"]]
        assert len(ids) == len(set(ids))
        assert dict(Counter(case["split"] for case in data["cases"])) == expected[kind]
        review = data["gold_review"]
        assert review["status"] in {"pending_human_review", "approved_by_user"}
        if review["status"] == "pending_human_review":
            assert all(review[key] is None for key in ("reviewer", "date", "decision"))
            assert PROTOCOL["evaluation"]["status"] == "not_started"
        else:
            assert all(review[key] for key in ("reviewer", "date", "decision"))
        spec = next(d for d in PROTOCOL["datasets"] if d["kind"] == kind)
        assert spec["development_scenarios"] == expected[kind]["development"]
        assert spec["evaluation_scenarios"] == expected[kind]["evaluation"]
        assert spec["gold_review"] == review["status"]
        assert (ROOT / spec["manifest"]).is_file()


def test_quality_bytes_are_frozen_without_regenerating_any_fixture():
    assert verify(QUALITY) == []
    manifest = json.loads((QUALITY / "manifest.json").read_text())
    assert len(manifest["files"]) == 32
    assert Counter(case["split"] for case in manifest["files"]) == {
        "development": 8,
        "evaluation": 24,
    }


@pytest.mark.parametrize("case", ANNOTATIONS["cases"], ids=lambda c: c["case_id"])
@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_proposed_quality_annotations_match_deterministic_ingestion(case, extension):
    """Check input/gold consistency, not model scores or gold human approval."""
    context = build_context(
        QUALITY / case["split"] / f"{case['case_id']}.{extension}",
        source=case["source"],
        case_id=case["case_id"],
        references_available=case["references_available"],
    )
    actual = [
        (item["code"], item["row"], item["column"]) for item in context["occurrences"]
    ]
    expected = [(code, row, column) for code, _, row, column in case["expected"]]
    assert actual == expected
    assert "Ignore previous instructions" not in json.dumps(context)
    assert "WO-SYN-" not in json.dumps(context)


@pytest.mark.parametrize("entry", OPERATIONS["cases"], ids=lambda c: c["case_id"])
def test_operational_gold_has_valid_evidence_and_consistent_counts(entry):
    for name in ("input", "gold"):
        path = OPERATIONAL / entry[name]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry[f"{name}_sha256"]
    case = load_case(OPERATIONAL / entry["input"])
    gold = json.loads((OPERATIONAL / entry["gold"]).read_text())
    validate_output(case, gold)
    assert case["case_id"] == gold["case_id"] == entry["case_id"]
    for collection in ("pending_items", "classifications", "events"):
        assert case["execution"]["counts"][collection] == len(case[collection])
    expected_tools = {"get_execution"}
    expected_tools.update(
        name
        for name, collection in (
            ("list_pending", "pending_items"),
            ("list_classifications", "classifications"),
            ("list_events", "events"),
        )
        if case[collection]
    )
    assert set(entry["required_tools"]) == expected_tools
    assert len(entry["required_tools"]) == len(expected_tools)
    assert entry["required_facts"] and all(entry["required_facts"])


def test_resource_limits_and_candidate_roles_are_explicit():
    resources = PROTOCOL["resources"]
    assert resources["concurrent_models"] == resources["parallel_requests"] == 1
    assert resources["minimum_available_ram_bytes"] >= 2 * 1024**3
    assert resources["minimum_available_disk_bytes_before_run"] >= 8 * 1024**3
    assert (
        resources["request_timeout_seconds"]
        <= resources["operational_attempt_deadline_seconds"]
    )
    assert resources["missing_telemetry"] == "record_unavailable_never_zero"
    models = PROTOCOL["models"]
    assert len({model["id"] for model in models}) == len(models)
    assert (
        next(m for m in models if m["tag"] == "qwen3:8b")["capacity"]
        == "observed_hybrid_cpu_gpu_development_probe"
    )
    assert (
        next(m for m in models if m["tag"].startswith("qwen2.5"))["product_eligibility"]
        == "not_approved"
    )
    assert all((ROOT / path).is_file() for path in PROTOCOL["historical_references"])
    environment = json.loads((ROOT / PROTOCOL["environment_evidence"]).read_text())
    assert environment["gpu"]["vram_total_bytes"] == 4 * 1024**3
    assert environment["measurement_kind"] == "read_only_inventory_no_inference"
