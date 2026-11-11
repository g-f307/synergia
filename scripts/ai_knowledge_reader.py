"""Document-derived scope controls, lexical comparator and reader evaluation."""

from __future__ import annotations

import json
import re

from ai_knowledge import factual_slice, messages, response_schema, values
from ai_knowledge_retrieval import (
    bm25,
    cosine,
    document,
    fusion,
    order,
    queries,
    tokens,
)
from jsonschema import Draft202012Validator

STRUCTURED = {"K01", "K02", "K03", "K04", "K08", "K09"}
SEMANTIC = {"K05", "K06", "K07", "K10"}


def objective_status(cid: str, envelope: dict) -> str | None:
    """Execute explicit documented conditions, not the evaluation reference."""
    v = values(envelope)
    if cid in {"K01", "K02", "K08"}:
        if v["approval"] is not True or v["hold"] is not True:
            return "not_applicable"
        relation, after = v["scope_relation"], v["hold_after_pass"]
        if cid == "K01":
            return {"same": "rejected", "different": "supported", None: "possible"}[
                relation
            ]
        if cid == "K02":
            if relation == "different" or (relation == "same" and after is False):
                return "rejected"
            return "supported" if relation == "same" and after is True else "possible"
        if relation == "different" or after is True or v["release_record"] is True:
            return "rejected"
        return "supported" if relation == "same" and after is False else "possible"
    if cid == "K03":
        return (
            "supported"
            if v["long_hold"] is True
            else "possible"
            if v["long_hold"] is None
            else "not_applicable"
        )
    if cid == "K04":
        if v["any_hold"] is not True:
            return "not_applicable"
        reason = next(f for f in envelope["facts"] if f["field"] == "reason")
        return {
            "observed": "rejected",
            "confirmed_absent": "supported",
            "unknown": "possible",
            "not_exposed": "possible",
        }[reason["state"]]
    if cid == "K09":
        if v["loading"] is not True:
            return "not_applicable"
        complete = (
            v["planned"] is not None
            and v["loaded"] is not None
            and v["loaded"] >= v["planned"]
        )
        return "rejected" if complete or v["oqc_pending"] == 0 else "possible"
    if cid in {"K05", "K06", "K07"} and (v["any_hold"] is not True or not v["note"]):
        return "not_applicable"
    if cid == "K10" and not v["note"]:
        return "not_applicable"
    return None


def focused_retrieve(cards, envelope, vectors=None, query_vectors=None):
    """Remove objective contradictions; rank text with the note, not generic flags.

    Code-derived candidates are explicit and identically available to B1/C4/C8.
    No case IDs, gold annotations, learned thresholds or per-case overrides.
    """
    active = [c for c in cards if c["status"] == "current"]
    states = {c["id"]: objective_status(c["id"], envelope) for c in active}
    note = values(envelope)["note"] or ""
    # This card explicitly requires a technical import occurrence; no lot inference.
    import_topic = bool(
        re.search(
            r"\b(arquiv\w*|upload\w*|import\w*|processamento)\b", " ".join(tokens(note))
        )
    )
    eligible = [
        c
        for c in active
        if states[c["id"]] not in {"rejected", "not_applicable"}
        and (c["id"] != "K10" or import_topic)
    ]
    ids = [c["id"] for c in eligible]
    views = queries(envelope)
    view = len(views) - 1 if note else 0
    lexical = order(ids, bm25([document(c) for c in eligible], views[view]))
    rankings = {"bm25": lexical}
    if vectors is not None:
        dense = order(ids, [cosine(query_vectors[view], vectors[cid]) for cid in ids])
        rankings.update(dense=dense, hybrid=fusion([lexical, dense], ids))
    for arm, ranking in rankings.items():
        known = [cid for cid in ranking if states[cid] in {"supported", "possible"}]
        known.sort(key=lambda cid: (states[cid] != "supported", ranking.index(cid)))
        rankings[arm] = known + [cid for cid in ranking if cid not in known]
    return rankings


def reader_schema(card, envelope, variant):
    sliced = factual_slice(card, envelope)
    schema = response_schema(sliced)
    if variant == "typed_checklist":
        unavailable = [f["field"] for f in sliced["facts"] if f["state"] != "observed"]
        missing = schema["properties"]["missing_fields"]
        missing["maxItems"] = min(missing["maxItems"], len(unavailable))
        if unavailable:
            missing["items"]["enum"] = unavailable
    return schema


def reader_messages(card, envelope, variant):
    result = messages(card, envelope)
    if variant == "typed_checklist":
        old = json.dumps(
            response_schema(factual_slice(card, envelope)), ensure_ascii=False
        )
        new = json.dumps(reader_schema(card, envelope, variant), ensure_ascii=False)
        result[1]["content"] = result[1]["content"].replace(
            "\nSCHEMA:\n" + old, "\nSCHEMA:\n" + new, 1
        )
    if variant == "minimal":
        return result
    result[0]["content"] += (
        " Checklist: não confunda frase da ficha com evento. Uma nota sem menção ao "
        "assunto torna a ficha textual not_applicable, não possible. Um critério "
        "explícito contrário exige rejected. Cite a evidência decisiva, e a nota "
        "com a restrição quando a decisão for textual. missing_fields só admite "
        "campos realmente não observados; não liste um valor conhecido como ausente. "
        "Não é obrigatório listar todo campo desconhecido se ele não muda a decisão."
    )
    if variant == "contrastive":
        result[0]["content"] += (
            " Exemplos de desenvolvimento: para a ficha de contraprova com retenção "
            "confirmada, 'o ensaio extra foi encerrado' é rejected; 'pergunta-se se "
            "será preciso outro ensaio' é possible; uma nota exclusivamente cadastral "
            "é not_applicable. Para motivo, não disponibilizado é possible, "
            "enquanto vazio confirmado sustenta a ausência apenas no recorte. "
            "Os exemplos não descrevem o caso atual. Em conflito sem precedência, "
            "não transforme uma das versões em fato definitivo."
        )
    elif variant not in {"checklist", "typed_checklist"}:
        raise ValueError("unknown_reader_variant")
    return result


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def decisive_fields(cid, envelope, status):
    v = values(envelope)
    if cid in {"K01", "K02", "K08"} and status == "not_applicable":
        return [{f} for f in ["approval", "hold"] if v[f] is not True]
    if cid == "K01":
        return [{"scope_relation"}, {"approval_lot", "hold_lot"}]
    if cid == "K02":
        if status == "supported":
            return [
                {"scope_relation", "hold_after_pass"},
                {"approval_lot", "hold_lot", "approved_at", "held_at"},
            ]
        if status == "rejected":
            return (
                [{"scope_relation"}]
                if v["scope_relation"] == "different"
                else [{"hold_after_pass"}, {"approved_at", "held_at"}]
            )
        return (
            [{"scope_relation"}]
            if v["scope_relation"] is None
            else [{"hold_after_pass"}]
        )
    if cid == "K03":
        return [{"long_hold"}]
    if cid == "K04":
        if status == "not_applicable":
            return [{"any_hold"}, {"hold", "long_hold", "ship_block"}]
        return [{"any_hold", "reason"}] + [
            {field, "reason"}
            for field in ["hold", "long_hold", "ship_block"]
            if v[field] is True
        ]
    if cid in {"K05", "K06", "K07"}:
        if status == "not_applicable" and v["any_hold"] is not True:
            return [{"any_hold"}, {"hold", "long_hold", "ship_block"}]
        alternatives = [{"note", "any_hold"}]
        alternatives += [
            {"note", f} for f in ["hold", "long_hold", "ship_block"] if v[f] is True
        ]
        return alternatives
    if cid == "K08":
        if status == "supported":
            return [
                {"scope_relation", "hold_after_pass", "release_record"},
                {"scope_relation", "approved_at", "held_at", "release_record"},
                {
                    "approval_lot",
                    "hold_lot",
                    "approved_at",
                    "held_at",
                    "release_record",
                },
            ]
        if status == "rejected":
            return [
                {f}
                for f in ["scope_relation", "hold_after_pass", "release_record"]
                if (f == "scope_relation" and v[f] == "different")
                or (f != "scope_relation" and v[f] is True)
            ]
        return (
            [{"scope_relation"}]
            if v["scope_relation"] is None
            else [{"hold_after_pass"}]
        )
    if cid == "K09":
        return (
            [{"loading"}]
            if status == "not_applicable"
            else [{"planned", "loaded", "oqc_pending"}]
        )
    return [{"note"}]


def assess(card, envelope, raw, done_reason="stop"):
    sliced = factual_slice(card, envelope)
    result = {
        "schema_valid": False,
        "reference_valid": False,
        "missing_valid": False,
        "guard_accepted": False,
        "parsed": None,
        "rejection": None,
    }
    try:
        candidate = json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, TypeError):
        result["rejection"] = "invalid_or_duplicate_json"
        return result
    if done_reason == "length" or not Draft202012Validator(
        response_schema(sliced)
    ).is_valid(candidate):
        result["rejection"] = "schema_or_truncation"
        return result
    result.update(schema_valid=True, parsed=candidate)
    fields = {f["id"]: f for f in sliced["facts"]}
    cited = {fields[i]["field"] for i in candidate["evidence_ids"]}
    result["reference_valid"] = any(
        s <= cited for s in decisive_fields(card["id"], envelope, candidate["status"])
    )
    unavailable = {f["field"] for f in sliced["facts"] if f["state"] != "observed"}
    result["missing_valid"] = set(candidate["missing_fields"]) <= unavailable
    critical = {
        "K01": {"scope_relation", "approval_lot", "hold_lot"},
        "K02": {
            "scope_relation",
            "approval_lot",
            "hold_lot",
            "hold_after_pass",
            "approved_at",
            "held_at",
        },
        "K03": {"long_hold"},
        "K04": {"reason"},
        "K08": {
            "scope_relation",
            "approval_lot",
            "hold_lot",
            "hold_after_pass",
            "approved_at",
            "held_at",
            "release_record",
        },
        "K09": {"planned", "loaded", "oqc_pending"},
    }.get(card["id"], set()) & unavailable
    if candidate["status"] == "possible" and critical:
        result["missing_valid"] &= bool(set(candidate["missing_fields"]) & critical)
    expected_objective = objective_status(card["id"], envelope)
    if expected_objective is not None and candidate["status"] != expected_objective:
        result["rejection"] = "documented_objective_condition"
    elif not result["reference_valid"]:
        result["rejection"] = "missing_decisive_reference"
    elif not result["missing_valid"]:
        result["rejection"] = "known_field_declared_missing"
    else:
        result["guard_accepted"] = True
    return result


def lexical_status(cid, envelope):
    fixed = objective_status(cid, envelope)
    if fixed is not None:
        return fixed
    note = " ".join(tokens(values(envelope)["note"] or ""))
    themes = {
        "K05": r"amostra|ensaio|medicao|contraprova|confirmacao",
        "K06": r"etiqueta|rotulo|codigo impresso|identificacao fisica|marcacao",
        "K07": r"document\w*|fiscal|cadastr\w*|administrativ\w*",
        "K10": r"arquiv\w*|upload|import\w*",
    }
    topic = themes[cid]
    clauses = re.split(r"\bmas\b|;|\.|\b e \b", note)
    relevant = [c for c in clauses if re.search(topic, c)]
    if not relevant:
        return "not_applicable"
    if cid == "K10":
        return (
            "supported"
            if "ja importado" in note
            and (
                "nenhum novo processamento" in note
                or "nao iniciou outro processamento" in note
            )
            else "rejected"
            if "importacao nova" in note
            else "possible"
        )
    uncertain = r"pergunta|questiona|duvida|divergem|mesma precedencia|mesma vigencia"
    if re.search(uncertain, note):
        return "possible"
    negative = (
        r"encerrou|encerrad\w*|terminou|concluid\w*|corresponde|"
        r"nenhuma divergencia|nao ha .*pendente|descarta"
    )
    negative_parts = [
        c
        for c in relevant
        if re.search(negative, c)
        and not re.search(r"nao corresponde|nao (?:foi )?concluid|nao encerrou", c)
    ]
    if negative_parts:
        return "possible" if len(negative_parts) < len(relevant) else "rejected"
    return "supported"


def baseline_item(card, envelope):
    status = lexical_status(card["id"], envelope)
    fields = decisive_fields(card["id"], envelope, status)[0]
    return {
        "status": status,
        "evidence_ids": [f["id"] for f in envelope["facts"] if f["field"] in fields],
        "missing_fields": [
            f["field"]
            for f in factual_slice(card, envelope)["facts"]
            if f["state"] != "observed"
        ],
    }


def score_attempt(row, expected):
    correct = row["schema_valid"] and row["parsed"]["status"] == expected
    return {
        **row,
        "expected_status": expected,
        "status_correct": bool(correct),
        "complete_raw": bool(
            correct and row["reference_valid"] and row["missing_valid"]
        ),
        "high_error_raw": bool(
            row["schema_valid"]
            and row["parsed"]["status"] == "supported"
            and expected != "supported"
        ),
    }


def summarize_attempts(rows):
    n = len(rows)
    return {
        "attempts": n,
        "schema_valid": sum(r["schema_valid"] for r in rows),
        "status_correct": sum(r["status_correct"] for r in rows),
        "complete_raw": sum(r["complete_raw"] for r in rows),
        "guard_accepted": sum(r["guard_accepted"] for r in rows),
        "high_errors_raw": sum(r["high_error_raw"] for r in rows),
        "high_errors_exposed": sum(
            r["high_error_raw"] and r["guard_accepted"] for r in rows
        ),
        "mean_seconds": sum(r.get("elapsed_seconds", 0) for r in rows) / n
        if n
        else None,
    }


def task_metrics(cases, rows, gold, policy="supported_and_possible"):
    allowed = (
        {"supported", "possible"}
        if policy == "supported_and_possible"
        else {"supported"}
    )
    displayed, correct_items, high, answerable, covered, complete, checks = (
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    for case in cases:
        cid = case["case_id"]
        relevant = set(gold[cid]["relevant_cards"])
        items = [
            r
            for r in rows
            if r["case_id"] == cid
            and r["guard_accepted"]
            and r["parsed"]["status"] in allowed
        ]
        correct = {r["card_id"] for r in items if r["complete_raw"]}
        displayed += len(items)
        correct_items += sum(r["complete_raw"] for r in items)
        high += sum(r["high_error_raw"] for r in items)
        if relevant:
            answerable += 1
            covered += bool(correct & relevant)
            checks += bool(correct & relevant) and all(r["complete_raw"] for r in items)
        complete += correct == relevant and len(correct) == len(items)
    return {
        "cases": len(cases),
        "answerable": answerable,
        "displayed_items": displayed,
        "correct_displayed_items": correct_items,
        "precision": correct_items / displayed if displayed else None,
        "coverage": covered / answerable if answerable else None,
        "complete_case_accuracy": complete / len(cases) if cases else None,
        "high_errors_exposed": high,
        "next_check_relevance": checks / answerable if answerable else None,
        "next_check_scope": "Documented ID attached by code, not a model "
        "procedure choice; missing answerable cases included.",
    }
