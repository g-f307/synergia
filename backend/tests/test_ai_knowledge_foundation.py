"""Meaningful contract/leakage/unknown controls; no runtime or credentials."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ai_knowledge import (  # noqa: E402
    DATA,
    KnowledgeError,
    factual_slice,
    inputs,
    messages,
    project,
    read,
    response_schema,
    validate_corpus,
    values,
    verify_bundle,
    write_new,
)
from prepare_ai_knowledge import render_cards  # noqa: E402


def case(cid="D01"):
    return copy.deepcopy(next(c for c in inputs("development") if c["case_id"] == cid))


def rehash(root):
    manifest = read(root / "manifest.json")
    for name in manifest["files"]:
        manifest["files"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    (root / "manifest.json").write_text(json.dumps(manifest))


def test_inventory_challenge_balance_and_group_counts():
    result = validate_corpus()
    assert result["groups"] == 48
    groups = {}
    for split, count in {"development": 32, "validation": 16, "evaluation": 48}.items():
        assert result["splits"][split]["cases"] == count
        assert set(Counter(c["group_id"] for c in inputs(split)).values()) == {2}
        for c in inputs(split):
            assert c["group_id"] not in groups or groups[c["group_id"]] == split
            groups[c["group_id"]] = split
    gold = read(DATA / "evaluation-gold.json")
    assert sum(g["semantic_case"] for g in gold.values()) >= 16


def test_fact_projection_preserves_false_unknown_and_confirmed_absence():
    c = case("D09")
    c["fields"]["long_hold"] = {"state": "unknown", "value": None}
    env = project(c)
    facts = {f["field"]: f for f in env["facts"]}
    assert facts["hold"]["value"] is True
    assert facts["long_hold"]["state"] == "unknown"
    assert facts["reason"]["state"] == "confirmed_absent"
    assert values(env)["any_hold"] is True
    c["fields"]["hold"]["value"] = False
    assert values(project(c))["any_hold"] is None


def test_chronology_compares_instants_including_timezone_offsets():
    assert values(project(case("D13")))["hold_after_pass"] is True
    assert values(project(case("D14")))["hold_after_pass"] is False
    assert values(project(case("D04")))["hold_after_pass"] is None


def test_lot_identity_is_literal_not_fuzzy_or_order_equivalence():
    c = case()
    assert values(project(c))["scope_relation"] == "different"
    c["fields"]["approval_lot"]["value"] = "SYN-LOT-1"
    c["fields"]["hold_lot"]["value"] = "SYN-LOT-01"
    assert values(project(c))["scope_relation"] == "different"


@pytest.mark.parametrize(
    "field,item,error",
    [
        ("hold", {"state": "observed", "value": "false"}, "invalid_boolean_fact"),
        ("planned", {"state": "observed", "value": True}, "invalid_quantity_fact"),
        ("planned", {"state": "observed", "value": -1}, "invalid_quantity_fact"),
        ("reason", {"state": "unknown", "value": "secret"}, "invalid_state_value"),
        ("reason", {"state": "observed", "value": None}, "invalid_state_value"),
        (
            "held_at",
            {"state": "observed", "value": "2026-10-01"},
            "invalid_synthetic_chronology",
        ),
    ],
)
def test_invalid_facts_are_not_coerced(field, item, error):
    c = case("D03")
    c["fields"][field] = item
    with pytest.raises(KnowledgeError, match=error):
        project(c)


def test_prompt_excludes_labels_and_uses_only_card_relevant_facts():
    c = case("D05")
    c["entity"]["id"] = "SYN-ENTITY"
    card = next(c for c in read(DATA / "knowledge.json") if c["id"] == "K05")
    prompt = json.dumps(messages(card, project(c)), ensure_ascii=False)
    for forbidden in (
        "semantic_annotations",
        "relevant_cards",
        "D05",
        "group_id",
        "split",
        "stratum",
        "expected_checks",
    ):
        assert forbidden not in prompt
    assert c["fields"]["note"]["value"] in prompt
    assert '"planned"' not in prompt
    assert '"approved_at"' not in prompt


def test_inference_input_loader_does_not_open_gold(monkeypatch):
    import ai_knowledge

    original = ai_knowledge.read
    paths = []

    def guarded(path):
        paths.append(path.name)
        assert "gold" not in path.name
        return original(path)

    monkeypatch.setattr(ai_knowledge, "read", guarded)
    assert len(ai_knowledge.inputs("development")) == 32
    assert paths == ["development.json"]


def test_output_contract_rejects_invented_or_duplicated_evidence():
    card = read(DATA / "knowledge.json")[0]
    schema = response_schema(factual_slice(card, project(case())))
    validator = Draft202012Validator(schema)
    valid = {"status": "supported", "evidence_ids": ["F01"], "missing_fields": []}
    assert validator.is_valid(valid)
    assert not validator.is_valid({**valid, "evidence_ids": ["F99"]})
    assert not validator.is_valid({**valid, "evidence_ids": ["F01", "F01"]})
    assert not validator.is_valid({**valid, "release": True})


def test_current_contract_profile_does_not_assume_uningested_flags_false():
    c = case("D19")
    assert all(
        item["state"] == "not_exposed"
        for field, item in c["fields"].items()
        if field in {"long_hold", "ship_block", "note", "approved_at"}
    )
    assert values(project(c))["scope_relation"] is None


def test_fixture_changes_and_group_cross_split_are_detected(tmp_path):
    root = tmp_path / "fixtures"
    shutil.copytree(DATA, root)
    rows = read(root / "evaluation.json")
    rows[0]["group_id"] = inputs("development")[0]["group_id"]
    (root / "evaluation.json").write_text(json.dumps(rows))
    with pytest.raises(KnowledgeError, match="fixture_hash_mismatch"):
        verify_bundle(root)
    rehash(root)
    with pytest.raises(KnowledgeError, match="group_split_leakage"):
        validate_corpus(root)


def test_persistence_never_overwrites_an_existing_result(tmp_path):
    path = tmp_path / "output.json"
    write_new(path, {"failed": True})
    with pytest.raises(FileExistsError):
        write_new(path, {"failed": False})
    assert read(path) == {"failed": True}


def test_protocol_budget_and_authorization_are_explicit():
    protocol = read(ROOT / "docs/ai-knowledge-poc-protocol.json")
    assert protocol["authorization"]["current_blocks"] == [1, 2]
    assert protocol["authorization"]["require_user_approval_before_block"] == 3
    assert sum(protocol["budget"]["generative_calls"].values()) == 992
    assert protocol["budget"]["hard_call_limit"] == 1000


def test_readable_cards_match_the_single_json_source():
    assert (ROOT / "docs/ai-knowledge-poc-cards.md").read_text() == render_cards(
        read(DATA / "knowledge.json")
    )
