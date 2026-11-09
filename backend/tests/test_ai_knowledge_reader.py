"""Isolated PoC controls and honest task denominators, without inference."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ai_knowledge import DATA, KnowledgeError, inputs, project, read  # noqa: E402
from ai_knowledge_reader import (  # noqa: E402
    STRUCTURED,
    assess,
    baseline_item,
    focused_retrieve,
    lexical_status,
    objective_status,
    reader_messages,
    reader_schema,
    score_attempt,
    task_metrics,
)
from run_ai_knowledge_development import main, prepare  # noqa: E402


def assets(cid="D05", kid="K05"):
    case = copy.deepcopy(next(c for c in inputs("development") if c["case_id"] == cid))
    card = next(c for c in read(DATA / "knowledge.json") if c["id"] == kid)
    return case, card


def test_documented_objective_rules_match_development_reference_only():
    gold = read(DATA / "development-gold.json")
    for case in inputs("development"):
        for kid in STRUCTURED:
            assert (
                objective_status(kid, project(case))
                == gold[case["case_id"]]["expected"][kid]
            )


def test_focused_retrieval_excludes_archived_and_objective_contradictions():
    case, _ = assets()
    cards = read(DATA / "knowledge.json")
    ranking = focused_retrieve(cards, project(case))["bm25"]
    assert "K05" in ranking[:2]
    assert not set(ranking) & {"K11", "K12", "K01", "K02", "K08"}
    case["case_id"] = "ARBITRARY"
    assert focused_retrieve(cards, project(case))["bm25"] == ranking


def test_unknown_reason_is_not_absent_and_scope_controls_do_not_infer_text():
    case, card = assets("D10", "K04")
    env = project(case)
    assert objective_status("K04", env) == "possible"
    raw = baseline_item(card, env)
    raw["status"] = "supported"
    result = assess(card, env, json.dumps(raw))
    assert not result["guard_accepted"]
    assert result["rejection"] == "documented_objective_condition"
    case, _ = assets()
    assert objective_status("K05", project(case)) is None


def test_references_need_decisive_facts_and_missing_cannot_be_known():
    case, card = assets()
    env = project(case)
    raw = baseline_item(card, env)
    assert assess(card, env, json.dumps(raw))["guard_accepted"]
    raw["evidence_ids"] = [f["id"] for f in env["facts"] if f["field"] == "hold"]
    assert not assess(card, env, json.dumps(raw))["reference_valid"]
    raw = baseline_item(card, env)
    raw["missing_fields"] = ["note"]
    assert not assess(card, env, json.dumps(raw))["missing_valid"]


def test_duplicate_json_truncation_and_unsupported_ids_are_rejected():
    case, card = assets()
    env = project(case)
    raw = json.dumps(baseline_item(card, env))
    assert not assess(card, env, raw, "length")["schema_valid"]
    duplicate = '{"status":"supported",' + raw[1:]
    assert assess(card, env, duplicate)["rejection"] == "invalid_or_duplicate_json"
    item = baseline_item(card, env)
    item["evidence_ids"] = ["F999"]
    assert not assess(card, env, json.dumps(item))["schema_valid"]


@pytest.mark.parametrize(
    "note,expected",
    [
        ("O ensaio extra foi encerrado.", "rejected"),
        ("Há dúvida se outro ensaio será necessário.", "possible"),
        ("A amostra aguarda confirmação.", "supported"),
        ("A etiqueta está ilegível.", "not_applicable"),
    ],
)
def test_lexical_control_handles_explicit_negation_and_uncertainty(note, expected):
    case, _ = assets()
    case["fields"]["note"]["value"] = note
    assert lexical_status("K05", project(case)) == expected


def test_no_orientation_does_not_fake_full_task_coverage():
    case, card = assets()
    gold = read(DATA / "development-gold.json")
    empty = task_metrics([case], [], gold)
    assert empty["precision"] is None
    assert empty["coverage"] == 0
    assert empty["complete_case_accuracy"] == 0
    item = baseline_item(card, project(case))
    row = score_attempt(
        {
            "case_id": case["case_id"],
            "card_id": card["id"],
            **assess(card, project(case), json.dumps(item)),
        },
        gold[case["case_id"]]["expected"][card["id"]],
    )
    result = task_metrics([case], [row], gold)
    assert result["precision"] == result["coverage"] == 1
    wrong_extra = {**row, "card_id": "K06", "complete_raw": False}
    mixed = task_metrics([case], [row, wrong_extra], gold)
    assert mixed["coverage"] == 1
    assert mixed["next_check_relevance"] == 0


def test_messages_exclude_gold_and_refinement_is_explicit():
    case, card = assets()
    for variant in ["minimal", "checklist", "contrastive"]:
        prompt = json.dumps(reader_messages(card, project(case), variant))
        for forbidden in ["semantic_annotations", "relevant_cards", "expected_checks"]:
            assert forbidden not in prompt
    assert (
        "Exemplos"
        not in reader_messages(card, project(case), "checklist")[0]["content"]
    )
    assert (
        "Exemplos" in reader_messages(card, project(case), "contrastive")[0]["content"]
    )


def test_typed_schema_prevents_known_missing_without_deciding_semantic_status():
    case, card = assets()
    env = project(case)
    schema = reader_schema(card, env, "typed_checklist")
    unavailable = {f["field"] for f in env["facts"] if f["state"] != "observed"}
    missing = schema["properties"]["missing_fields"]
    assert missing["maxItems"] <= len(unavailable)
    if missing["maxItems"]:
        assert set(missing["items"]["enum"]) <= unavailable
    assert set(schema["properties"]["status"]["enum"]) == {
        "supported",
        "possible",
        "rejected",
        "not_applicable",
    }
    prompt = reader_messages(card, env, "typed_checklist")[1]["content"]
    assert json.dumps(schema, ensure_ascii=False) in prompt


def test_reserved_execution_and_validation_without_confirmation_are_refused(tmp_path):
    with pytest.raises(KnowledgeError, match="reserved_or_unknown"):
        prepare("evaluation", tmp_path / "forbidden")
    with pytest.raises(KnowledgeError, match="confirm_development"):
        prepare("validation", tmp_path / "premature", {"models": {}})
    with pytest.raises(SystemExit):
        main(
            [
                "retrieval",
                "--split",
                "evaluation",
                "--budget-root",
                "/tmp/x",
                "--output-dir",
                "/tmp/x/run",
                "--allow-inference",
            ]
        )
