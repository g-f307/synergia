"""Small in-memory lexical/dense/hybrid retrieval, independent of the gold."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

from ai_knowledge import KnowledgeError, values


def tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Preserve negatives, numbers and domain words; no corpus-derived stopwords.
    return re.findall(r"\w+", text)


def document(card: dict) -> str:
    return "\n".join(
        [
            card["title"],
            card["scope"],
            card["situation"],
            ", ".join(card["vocabulary"]),
            *card["criteria"].values(),
            card["verification"]["text"],
            card["limits"],
        ]
    )


def queries(envelope: dict) -> list[str]:
    v = values(envelope)
    labels = {
        "approval": "Inspeção aprovada",
        "hold": "Retenção OQC comum",
        "long_hold": "Retenção de longo prazo",
        "ship_block": "Bloqueio de embarque",
        "scope_relation": "Relação entre lotes da aprovação e retenção",
        "hold_after_pass": "Retenção posterior à aprovação",
        "release_record": "Registro explícito de encerramento",
        "loading": "Situação de carregamento",
        "planned": "Quantidade planejada",
        "loaded": "Quantidade carregada",
        "oqc_pending": "Indicador OQC Pending",
    }
    rendered = []
    for field, label in labels.items():
        value = v[field]
        if value is None:
            text = "desconhecido, não equivale a não"
        elif value is True:
            text = "sim"
        elif value is False:
            text = "não"
        elif value == "same":
            text = "mesmo lote"
        elif value == "different":
            text = "lotes distintos"
        else:
            text = str(value)
        rendered.append(f"{label}: {text}.")
    reason = next(f for f in envelope["facts"] if f["field"] == "reason")
    states = {
        "observed": "justificativa preenchida",
        "confirmed_absent": "ausência de motivo confirmada neste extrato",
        "unknown": "presença do motivo desconhecida",
        "not_exposed": "justificativa não disponibilizada pela projeção",
    }
    rendered.append(states[reason["state"]])
    result = [" ".join(rendered)]
    if v["note"]:
        result.append("Observação do registro: " + v["note"])
    return result


def bm25(documents: list[str], query: str) -> list[float]:
    corpus = [tokens(d) for d in documents]
    if not corpus:
        return []
    counts = [Counter(d) for d in corpus]
    average = sum(map(len, corpus)) / len(corpus) or 1
    df = Counter(term for d in corpus for term in set(d))
    scores = []
    for doc, count in zip(corpus, counts, strict=True):
        score = 0.0
        for term in set(tokens(query)):
            frequency = count[term]
            if frequency:
                idf = math.log(1 + (len(corpus) - df[term] + 0.5) / (df[term] + 0.5))
                score += (
                    idf
                    * frequency
                    * 2.5
                    / (frequency + 1.5 * (0.25 + 0.75 * len(doc) / average))
                )
        scores.append(score)
    return scores


def cosine(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        raise KnowledgeError("incompatible_embedding_dimensions")
    if any(not math.isfinite(x) for x in a + b):
        raise KnowledgeError("non_finite_embedding")
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    if norm == 0:
        raise KnowledgeError("zero_embedding")
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm


def order(ids: list[str], scores: list[float]) -> list[str]:
    return sorted(ids, key=lambda cid: (-scores[ids.index(cid)], cid))


def fusion(rankings: list[list[str]], ids: list[str], constant=60) -> list[str]:
    scores = {cid: 0.0 for cid in ids}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, 1):
            scores[cid] += 1 / (constant + rank)
    return sorted(ids, key=lambda cid: (-scores[cid], cid))


def retrieve(
    cards: list[dict],
    envelope: dict,
    vectors: dict[str, list[float]] | None = None,
    query_vectors: list[list[float]] | None = None,
) -> dict:
    active = [c for c in cards if c["status"] == "current"]
    ids = [c["id"] for c in active]
    texts = [document(c) for c in active]
    views = queries(envelope)
    lexical = fusion([order(ids, bm25(texts, q)) for q in views], ids)
    result = {"bm25": lexical}
    if vectors is not None:
        if query_vectors is None or len(query_vectors) != len(views):
            raise KnowledgeError("missing_query_embeddings")
        semantic = fusion(
            [
                order(ids, [cosine(q, vectors[cid]) for cid in ids])
                for q in query_vectors
            ],
            ids,
        )
        result.update(dense=semantic, hybrid=fusion([lexical, semantic], ids))
    return result


def metrics(records: list[dict], gold: dict) -> dict:
    """Score every case; empty references do not become perfect recall."""
    result = {}
    for arm in records[0]["rankings"] if records else []:
        positive = [r for r in records if gold[r["case_id"]]["relevant_cards"]]
        ks = {}
        for k in [1, 2, 3, 5]:
            recalls, precisions = [], []
            for row in records:
                expected = set(gold[row["case_id"]]["relevant_cards"])
                top = row["rankings"][arm][:k]
                hits = len(expected & set(top))
                if expected:
                    recalls.append(hits / len(expected))
                precisions.append(hits / len(top) if top else 0)
            ks[str(k)] = {
                "recall_answerable_macro": sum(recalls) / len(recalls)
                if recalls
                else None,
                "precision_all_cases_macro": sum(precisions) / len(precisions)
                if precisions
                else None,
            }
        reciprocal = []
        for row in positive:
            expected = set(gold[row["case_id"]]["relevant_cards"])
            reciprocal.append(
                next(
                    (
                        1 / i
                        for i, cid in enumerate(row["rankings"][arm], 1)
                        if cid in expected
                    ),
                    0,
                )
            )
        ceilings = [
            min(2, len(gold[r["case_id"]]["relevant_cards"]))
            / len(gold[r["case_id"]]["relevant_cards"])
            for r in positive
        ]
        negative = [r for r in records if not gold[r["case_id"]]["relevant_cards"]]
        result[arm] = {
            "cases": len(records),
            "answerable": len(positive),
            "without_applicable_card": len(negative),
            "k": ks,
            "mrr_answerable": sum(reciprocal) / len(reciprocal) if reciprocal else None,
            "two_card_oracle_ceiling": sum(ceilings) / len(ceilings)
            if ceilings
            else None,
            "negative_cases_with_suggestions": sum(
                bool(r["rankings"][arm]) for r in negative
            ),
            "threshold": "not_calibrated; ranking is not an applicability decision",
        }
    return result
