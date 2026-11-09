"""Static, local comparison of every final case/seed, including incorrect outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_knowledge import DATA, ROOT, inputs, project, read, write_new
from evaluate_ai_knowledge_final import validate_completion

TEMPLATE = ROOT / "scripts/templates/ai_knowledge_final.html"


def displayed(row, policy="supported_and_possible"):
    allowed = (
        {"supported", "possible"}
        if policy == "supported_and_possible"
        else {"supported"}
    )
    return row["guard_accepted"] and row["parsed"]["status"] in allowed


def panel_item(row, cards):
    card = cards[row["card_id"]]
    return {
        "card_id": card["id"],
        "title": card["title"],
        "status": row["parsed"]["status"],
        "evidence_ids": row["parsed"]["evidence_ids"],
        "missing_fields": row["parsed"]["missing_fields"],
        "verification": card["verification"],
        "limits": card["limits"],
        "correct": row["complete_raw"],
        "high_error": row["high_error_raw"],
    }


def build_data(root, run):
    config, _, _, plan, rankings = validate_completion(root, run)
    scores = read(run / "scores.json")
    cards = {c["id"]: c for c in read(DATA / "knowledge.json")}
    ranking = {r["case_id"]: r["rankings"] for r in rankings["rows"]}
    cases = []
    for case in inputs("evaluation"):
        cid = case["case_id"]
        panels = [
            {
                "name": "B0 · mensagem genérica",
                "seed": None,
                "items": [],
                "message": (
                    "Confira os fatos e seus registros de origem antes de "
                    "concluir a investigação."
                ),
            }
        ]
        for key, name in [
            ("B1_bm25", "B1 · BM25 e regras"),
            ("paired_lexical", "Controle lexical · mesmos candidatos do LLM"),
        ]:
            rows = [r for r in scores["baselines"][key]["rows"] if r["case_id"] == cid]
            panels.append(
                {
                    "name": name,
                    "seed": None,
                    "items": [panel_item(r, cards) for r in rows if displayed(r)],
                    "blocked": sum(not r["guard_accepted"] for r in rows),
                }
            )
        panels.append(
            {
                "name": "B2 · busca densa documental",
                "seed": None,
                "items": [
                    {
                        "card_id": kid,
                        "title": cards[kid]["title"],
                        "status": "candidate",
                        "verification": cards[kid]["verification"],
                        "limits": cards[kid]["limits"],
                        "evidence_ids": [],
                        "missing_fields": [],
                    }
                    for kid in ranking[cid]["focused/dense"][:2]
                ],
                "message": (
                    "Candidatos recuperados. Esta busca não confirma a "
                    "aplicabilidade da ficha."
                ),
            }
        )
        for model, setting in config["models"].items():
            for seed in config["seeds"]:
                rows = [
                    r
                    for r in scores["attempts"]
                    if (r["case_id"], r["model"], r["seed"]) == (cid, model, seed)
                ]
                panels.append(
                    {
                        "name": model,
                        "seed": seed,
                        "policy": setting["policy"],
                        "items": [
                            panel_item(r, cards)
                            for r in rows
                            if displayed(r, setting["policy"])
                        ],
                        "blocked": sum(not r["guard_accepted"] for r in rows),
                        "raw": [
                            {
                                "card_id": r["card_id"],
                                "content": r["raw_content"],
                                "rejection": r["rejection"],
                                "expected": r["expected_status"],
                            }
                            for r in rows
                        ],
                    }
                )
        cases.append(
            {
                "case_id": cid,
                "group_id": case["group_id"],
                "facts": project(case)["facts"],
                "panels": panels,
            }
        )
    return {
        "issue": 183,
        "seeds": config["seeds"],
        "cases": cases,
        "generation_status": (
            "See checkpoint/generation decision; this viewer preserves the "
            "extractive classification panels."
        ),
    }


def render_html(data):
    payload = (
        json.dumps(data, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return TEMPLATE.read_text().replace("__POC_DATA__", payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = build_data(args.budget_root.resolve(), args.run_dir.resolve())
    write_new(args.output.with_suffix(".json"), data)
    with args.output.open("x") as f:
        f.write(render_html(data))
    print(
        f"Static local comparison: {len(data['cases'])} cases, all seeds; "
        "no external assets."
    )


if __name__ == "__main__":
    main()
