"""Retrieval quality controls without a network, weights, or application data."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ai_knowledge import DATA, KnowledgeError, inputs, project, read  # noqa: E402
from ai_knowledge_retrieval import (  # noqa: E402
    bm25,
    cosine,
    metrics,
    queries,
    retrieve,
    tokens,
)


def test_portuguese_normalization_preserves_negation():
    assert tokens("NÃO há retenção.") == ["nao", "ha", "retencao"]


def test_lexical_search_rewards_a_discriminating_term():
    scores = bm25(
        ["retenção no lote", "contraprova pendente no laboratório"], "contraprova"
    )
    assert scores[1] > scores[0] == 0


def test_queries_do_not_inject_identity_gold_or_assume_absence():
    c = copy.deepcopy(inputs("development")[9])
    assert c["fields"]["reason"]["state"] == "not_exposed"
    text = " ".join(queries(project(c)))
    assert "justificativa não disponibilizada" in text
    assert "ausência de motivo confirmada" not in text
    assert c["case_id"] not in text
    assert c["entity"]["id"] not in text
    assert c["fields"]["hold_lot"]["value"] not in text


def test_model_embeddings_and_query_vectors_are_required_together():
    cards = read(DATA / "knowledge.json")
    env = project(inputs("development")[0])
    with pytest.raises(KnowledgeError, match="missing_query_embeddings"):
        retrieve(cards, env, {"K01": [1, 0]})


def test_archived_cards_are_filtered_by_code_not_credited_to_the_model():
    cards = read(DATA / "knowledge.json")
    env = project(inputs("development")[0])
    vectors = {c["id"]: [1.0, 0.0] for c in cards}
    result = retrieve(cards, env, vectors, [[1.0, 0.0]] * len(queries(env)))
    for ranking in result.values():
        assert len(ranking) == 10
        assert set(ranking) == {f"K{i:02d}" for i in range(1, 11)}


@pytest.mark.parametrize(
    "a,b", [([0.0, 0], [1.0, 0]), ([1.0], [1.0, 0]), ([float("nan")], [1.0])]
)
def test_corrupt_embeddings_are_not_silently_scored(a, b):
    with pytest.raises(KnowledgeError):
        cosine(a, b)


def test_cosine_is_scale_invariant():
    assert cosine([2.0, 0], [20.0, 0]) == pytest.approx(1.0)


def test_recall_precision_and_architectural_ceiling_have_different_denominators():
    rows = [
        {"case_id": "A", "rankings": {"bm25": ["K01", "K09", "K02", "K03"]}},
        {"case_id": "B", "rankings": {"bm25": ["K09", "K01", "K02", "K03"]}},
    ]
    gold = {"A": {"relevant_cards": ["K01", "K02", "K03"]}, "B": {"relevant_cards": []}}
    score = metrics(rows, gold)["bm25"]
    assert score["cases"] == 2
    assert score["answerable"] == 1
    assert score["k"]["2"]["recall_answerable_macro"] == pytest.approx(1 / 3)
    assert score["k"]["2"]["precision_all_cases_macro"] == pytest.approx(0.25)
    assert score["two_card_oracle_ceiling"] == pytest.approx(2 / 3)
    assert score["negative_cases_with_suggestions"] == 1


def test_empty_reference_is_not_reported_as_perfect_recall():
    score = metrics(
        [{"case_id": "A", "rankings": {"bm25": ["K01"]}}], {"A": {"relevant_cards": []}}
    )["bm25"]
    assert score["k"]["2"]["recall_answerable_macro"] is None
    assert score["k"]["2"]["precision_all_cases_macro"] == 0
