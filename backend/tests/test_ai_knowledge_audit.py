"""Offline tests of grouped inference, independent recount and audit preservation."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ai_knowledge import KnowledgeError  # noqa: E402
from audit_ai_knowledge import (  # noqa: E402
    COUNTS,
    aggregate_groups,
    blindness_data,
    bootstrap,
    count_cases,
    historic_sources,
    label_free_messages,
    ledger_audit,
    reconstruct,
    wilson,
)


def counts(**kwargs):
    return {**dict.fromkeys(COUNTS, 0), **kwargs}


def test_wilson_boundaries_do_not_invent_certainty():
    zero = wilson(0, 24)
    perfect = wilson(24, 24)
    assert zero["low"] == 0
    assert 0.13 < zero["high"] < 0.14
    assert 0.86 < perfect["low"] < 0.87
    assert perfect["high"] == 1
    middle = wilson(12, 24)
    assert middle["low"] == pytest.approx(1 - middle["high"])
    with pytest.raises(KnowledgeError):
        wilson(1, 0)


def test_label_check_examines_decoded_json_content_not_escaped_container():
    label_free_messages({"messages": [{"content": '{"facts": []}'}]})
    body = {
        "messages": [
            {"content": json.dumps({"semantic_annotations": {"K01": "supported"}})}
        ]
    }
    with pytest.raises(KnowledgeError, match="reference_key_in_payload"):
        label_free_messages(body)


def test_group_draws_keep_multiplicity_and_actual_denominators():
    group = counts(
        cases=6,
        answerable=3,
        displayed_items=4,
        correct_displayed_items=1,
        covered_cases=1,
        complete_cases=1,
        correct_check_cases=1,
    )
    result = aggregate_groups([group], [0, 0, 0])
    assert result["cases"] == 18
    assert result["displayed_items"] == 12
    assert result["precision"] == 0.25
    assert result["coverage"] == 1 / 3


def test_bootstrap_is_paired_reproducible_and_does_not_multiply_groups():
    groups = [
        counts(
            cases=6,
            answerable=3,
            displayed_items=2,
            correct_displayed_items=2,
            complete_cases=4,
            covered_cases=2,
            correct_check_cases=2,
        ),
        counts(
            cases=6,
            answerable=6,
            displayed_items=8,
            correct_displayed_items=2,
            complete_cases=1,
            covered_cases=1,
            correct_check_cases=1,
        ),
    ]
    args = {"B1": groups, "model": copy.deepcopy(groups)}
    result = bootstrap(args, draws=100, seed=7)
    assert result == bootstrap(args, draws=100, seed=7)
    assert result["groups"] == 2
    assert result["arms"]["B1"]["precision"]["estimate"] == 0.4
    for interval in result["paired_differences_vs_B1"]["model"].values():
        assert interval["estimate"] == interval["low"] == interval["high"] == 0


def test_no_display_does_not_become_perfect_bootstrap_precision():
    group = counts(cases=6, complete_cases=6)
    result = bootstrap({"B1": [group], "model": [group]}, draws=20, seed=7)
    interval = result["arms"]["model"]["precision"]
    assert interval["estimate"] is interval["low"] is interval["high"] is None
    assert interval["undefined_draws"] == 20


def test_independent_recount_ignores_reported_complete_and_checks_extra_steps():
    cases = [{"case_id": "C1", "group_id": "G1"}]
    gold = {
        "C1": {
            "expected": {"K1": "supported", "K2": "not_applicable"},
            "relevant_cards": ["K1"],
            "expected_checks": ["V1"],
        }
    }
    cards = {"K1": {"verification": {"id": "V1"}}, "K2": {"verification": {"id": "V2"}}}
    row = {
        "case_id": "C1",
        "card_id": "K1",
        "schema_valid": True,
        "guard_accepted": True,
        "reference_valid": True,
        "missing_valid": True,
        "parsed": {"status": "supported"},
        "complete_raw": False,
    }
    result, _ = count_cases(cases, [row], gold, cards)
    assert result["complete_cases"] == result["correct_check_cases"] == 1
    extra = {**row, "card_id": "K2"}
    result, _ = count_cases(cases, [row, extra], gold, cards)
    assert result["covered_cases"] == 1
    assert result["complete_cases"] == result["correct_check_cases"] == 0
    assert result["high_errors_exposed"] == 1


def test_ledger_counts_texts_and_rejects_duplicate_results_or_time_drift():
    ledger = {
        "receipts": [
            {
                "route": "chat",
                "count": 1,
                "state": "completed",
                "result": "one",
                "elapsed_seconds": 2,
            },
            {
                "route": "embed",
                "count": 8,
                "state": "completed",
                "result": "two",
                "elapsed_seconds": 1,
            },
        ],
        "generative_calls": 1,
        "embedding_texts": 8,
        "active_seconds": 3,
    }
    assert ledger_audit(ledger)["embedding_texts"] == 8
    duplicated = copy.deepcopy(ledger)
    duplicated["receipts"][1]["result"] = "one"
    with pytest.raises(KnowledgeError, match="duplicated"):
        ledger_audit(duplicated)
    ledger["active_seconds"] += 0.1
    with pytest.raises(KnowledgeError, match="time_accounting"):
        ledger_audit(ledger)


def test_historical_patch_is_checked_without_editing_the_delivered_source():
    source = "a\nb\nc\n"
    patch = (
        "--- delivered/file\n+++ calibration/file\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n"
    )
    assert reconstruct(source, patch) == "a\nB\nc\n"
    assert source == "a\nb\nc\n"
    with pytest.raises(KnowledgeError, match="context_mismatch"):
        reconstruct("a\nchanged\nc\n", patch)


def test_archived_sources_do_not_require_unsquashed_git_objects(tmp_path, monkeypatch):
    import audit_ai_knowledge as module

    monkeypatch.setattr(module, "ROOT", tmp_path)
    source = tmp_path / "source.py"
    source.write_text("new\n")
    sha = hashlib.sha256(b"old\n").hexdigest()
    archive = tmp_path / "docs/evidence/issue-183-historical-source-patches.json"
    archive.parent.mkdir(parents=True)
    archive.write_text(
        json.dumps(
            {
                "patches": {
                    "source.py": {
                        "expected_sha256": sha,
                        "patch": (
                            "--- delivered/source.py\n+++ block2/source.py\n"
                            "@@ -1 +1 @@\n-new\n+old\n"
                        ),
                    }
                }
            }
        )
    )
    result = historic_sources(
        {"frozen_source_hashes": {"source.py": sha}}, {"runs": {}}
    )
    assert result["source_hash_comparisons"] == 1
    assert result["requires_old_git_objects"] is False
    assert source.read_text() == "new\n"


def test_blind_copy_masks_identity_grades_and_raw_without_changing_original():
    data = {
        "cases": [
            {
                "case_id": "E01",
                "panels": [
                    {"name": "B1", "seed": None, "items": []},
                    {
                        "name": "qwen3:4b",
                        "seed": 125,
                        "policy": "supported_only",
                        "raw": [{"expected": "supported"}],
                        "items": [
                            {
                                "correct": True,
                                "high_error": False,
                                "title": "Fictitious card",
                            }
                        ],
                    },
                    {"name": "qwen3:4b", "seed": 126, "items": []},
                ],
            }
        ]
    }
    before = copy.deepcopy(data)
    blinded, mapping = blindness_data(data)
    assert data == before
    assert (blinded, mapping) == blindness_data(data)
    assert "qwen" not in json.dumps(blinded)
    assert "raw" not in json.dumps(blinded)
    assert "correct" not in json.dumps(blinded)
    panels = blinded["cases"][0]["panels"]
    names = {p["name"] for p in panels if p["seed"] is not None}
    assert len(names) == 1
    assert mapping["E01"][names.pop()] == "qwen3:4b"
