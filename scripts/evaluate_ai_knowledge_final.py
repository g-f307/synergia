"""Offline block-5 scoring, only after every frozen final request completes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from ai_knowledge import (
    DATA,
    ROOT,
    KnowledgeError,
    digest,
    inputs,
    project,
    read,
    write_new,
)
from ai_knowledge_reader import (
    assess,
    baseline_item,
    score_attempt,
    summarize_attempts,
    task_metrics,
)
from ai_knowledge_retrieval import metrics
from run_ai_knowledge_final import FINAL, frozen_plan, source_hashes


def counted_task(cases, rows, gold, policy="supported_and_possible"):
    result = task_metrics(cases, rows, gold, policy)
    n = result["answerable"]
    result["covered_cases"] = round(result["coverage"] * n) if n else 0
    result["complete_cases"] = (
        round(result["complete_case_accuracy"] * len(cases)) if cases else 0
    )
    result["correct_check_cases"] = (
        round(result["next_check_relevance"] * n) if n else 0
    )
    return result


def pool_tasks(tasks):
    keys = [
        "cases",
        "answerable",
        "displayed_items",
        "correct_displayed_items",
        "high_errors_exposed",
        "covered_cases",
        "complete_cases",
        "correct_check_cases",
    ]
    result = {k: sum(t[k] for t in tasks) for k in keys}
    for name, num, den in [
        ("precision", "correct_displayed_items", "displayed_items"),
        ("coverage", "covered_cases", "answerable"),
        ("complete_case_accuracy", "complete_cases", "cases"),
        ("next_check_relevance", "correct_check_cases", "answerable"),
    ]:
        result[name] = result[num] / result[den] if result[den] else None
    result["unit"] = "Case-seed slots; not independent cases. Also report each seed."
    return result


def generation_gate(scores, config):
    observed = scores["models"][config["generation_model"]]["pooled_tasks"]
    rule = read(ROOT / config["rubric"])["generation_gate"]["requirements"]
    checks = {
        "precision": observed["precision"] is not None
        and observed["precision"] >= rule["precision_at_least"],
        "coverage": observed["coverage"] is not None
        and observed["coverage"] >= rule["coverage_at_least"],
        "next_check_relevance": observed["next_check_relevance"] is not None
        and observed["next_check_relevance"] >= rule["next_check_relevance_at_least"],
        "high_errors_exposed": observed["high_errors_exposed"]
        == rule["high_errors_exposed"],
    }
    return {
        "model": config["generation_model"],
        "passed": all(checks.values()),
        "checks": checks,
        "observed": observed,
        "requirements": rule,
        "scores_sha256": digest(scores),
        "seed_selection": "All frozen seeds, no best-seed selection.",
    }


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)] if values else None


def diagnostics(rows):
    states = ["supported", "possible", "rejected", "not_applicable"]
    confusion = {s: {p: 0 for p in [*states, "invalid"]} for s in states}
    for r in rows:
        confusion[r["expected_status"]][
            r["parsed"]["status"] if r["schema_valid"] else "invalid"
        ] += 1
    f1 = []
    for label in states:
        tp = confusion[label][label]
        fn = sum(confusion[label].values()) - tp
        fp = sum(confusion[s][label] for s in states if s != label)
        if tp + fn:
            f1.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)
    totals = defaultdict(float)
    cold = set()
    for r in rows:
        key = (r.get("seed"), r["case_id"])
        totals[key] += r.get("elapsed_seconds", 0)
        if r.get("load_duration_ns", 0) > 0.5e9:
            cold.add(key)
    warm = [v for k, v in totals.items() if k not in cold]
    all_times = list(totals.values())
    return {
        "confusion_matrix": confusion,
        "macro_f1_present_classes": statistics.mean(f1) if f1 else None,
        "reference_valid": sum(r["reference_valid"] for r in rows),
        "missing_valid": sum(r["missing_valid"] for r in rows),
        "rejection_counts": dict(
            Counter(r["rejection"] for r in rows if r["rejection"])
        ),
        "severity_counts": {
            "high_raw": sum(r["high_error_raw"] for r in rows),
            "high_blocked": sum(
                r["high_error_raw"] and not r["guard_accepted"] for r in rows
            ),
            "medium_raw": sum(
                not r["complete_raw"] and not r["high_error_raw"] for r in rows
            ),
            "low_prose": "not_applicable_to_structured_reader",
        },
        "timing": {
            "attempted_case_seed_slots": len(totals),
            "cold_slots": len(cold),
            "mean_seconds": statistics.mean(all_times) if all_times else None,
            "p50_seconds": statistics.median(all_times) if all_times else None,
            "p95_seconds": percentile(all_times, 0.95),
            "warm_slots": len(warm),
            "warm_mean_seconds": statistics.mean(warm) if warm else None,
            "warm_p50_seconds": statistics.median(warm) if warm else None,
            "warm_p95_seconds": percentile(warm, 0.95),
            "scope": (
                "Sum of reader calls per attempted case/seed; excludes zero-call "
                "slots and precomputed embeddings, not cold interactive RAG SLA."
            ),
        },
    }


def validate_completion(root, run):
    config, protocol, matrix, plan = frozen_plan(root, run)
    if plan["kind"] != "classification" or not (run / "complete.json").exists():
        raise KnowledgeError("all_final_requests_must_complete_before_scoring")
    complete = read(run / "complete.json")
    if (
        complete["calls"] != len(plan["requests"])
        or complete["requests_sha256"] != plan["requests_sha256"]
    ):
        raise KnowledgeError("completion_manifest_mismatch")
    actual = []
    for i, item in enumerate(plan["requests"]):
        path = run / f"attempt-{i:03d}.json"
        actual.append(hashlib.sha256(path.read_bytes()).hexdigest())
        record = read(path)
        if digest(record["request"]) != digest(item["body"]):
            raise KnowledgeError("completed_request_changed")
    if actual != complete["raw_sha256"]:
        raise KnowledgeError("completed_raw_changed")
    ranking = read(ROOT / plan["retrieval_dir"] / "rankings.json")
    if digest(ranking) != plan["retrieval_sha256"]:
        raise KnowledgeError("final_retrieval_changed")
    return config, protocol, matrix, plan, ranking


def score(root, run):
    config, _, _, plan, ranking = validate_completion(root, run)
    cases = inputs("evaluation")
    by_id = {c["case_id"]: c for c in cases}
    cards = {c["id"]: c for c in read(DATA / "knowledge.json")}
    # The only reference-label loader in the final pipeline, after completion.
    gold = read(DATA / "evaluation-gold.json")
    semantic = [c for c in cases if gold[c["case_id"]]["semantic_case"]]
    strata = sorted({g["stratum"] for g in gold.values()})
    rows = []
    for i, item in enumerate(plan["requests"]):
        raw = read(run / f"attempt-{i:03d}.json")
        response = raw["response"] or {}
        row = {
            **{k: v for k, v in item.items() if k != "body"},
            "index": i,
            **assess(
                cards[item["card_id"]],
                project(by_id[item["case_id"]]),
                response.get("message", {}).get("content", ""),
                response.get("done_reason"),
            ),
            "elapsed_seconds": raw["elapsed_seconds"],
            "error": raw["error"],
            "raw_content": response.get("message", {}).get("content", ""),
            "done_reason": response.get("done_reason"),
            "load_duration_ns": response.get("load_duration", 0),
            "prompt_eval_count": response.get("prompt_eval_count"),
            "eval_count": response.get("eval_count"),
        }
        rows.append(
            score_attempt(row, gold[item["case_id"]]["expected"][item["card_id"]])
        )
    baselines = {}
    for name, arm in [("B1_bm25", "focused/bm25"), ("paired_lexical", "focused/dense")]:
        baseline = []
        for record in ranking["rows"]:
            cid = record["case_id"]
            env = project(by_id[cid])
            for kid in record["rankings"][arm][:2]:
                raw = baseline_item(cards[kid], env)
                row = {
                    "case_id": cid,
                    "card_id": kid,
                    **assess(cards[kid], env, json.dumps(raw)),
                }
                baseline.append(score_attempt(row, gold[cid]["expected"][kid]))
        baselines[name] = {
            "rows": baseline,
            "tasks": counted_task(cases, baseline, gold),
            "semantic_tasks": counted_task(semantic, baseline, gold),
        }
    baselines["B0_generic"] = {
        "tasks": counted_task(cases, [], gold),
        "semantic_tasks": counted_task(semantic, [], gold),
        "scope": (
            "Same facts, generic check message, no selected card/check. "
            "Measures this task, not human usefulness."
        ),
    }
    models = {}
    for model, setting in config["models"].items():
        selected = [r for r in rows if r["model"] == model]
        seeds = {}
        for seed in config["seeds"]:
            sample = [r for r in selected if r["seed"] == seed]
            seeds[str(seed)] = {
                "raw": summarize_attempts(sample),
                "tasks": counted_task(cases, sample, gold, setting["policy"]),
                "semantic_tasks": counted_task(
                    semantic, sample, gold, setting["policy"]
                ),
                "strata": {
                    s: counted_task(
                        [c for c in cases if gold[c["case_id"]]["stratum"] == s],
                        sample,
                        gold,
                        setting["policy"],
                    )
                    for s in strata
                },
            }
        pooled = pool_tasks([s["tasks"] for s in seeds.values()])
        semantic_pooled = pool_tasks([s["semantic_tasks"] for s in seeds.values()])
        models[model] = {
            "profile": setting["profile"],
            "policy": setting["policy"],
            "seeds": seeds,
            "raw": summarize_attempts(selected),
            "diagnostics": diagnostics(selected),
            "pooled_tasks": pooled,
            "pooled_semantic_tasks": semantic_pooled,
            "gain_vs_B1": {
                "semantic_complete_case_points": 100
                * (
                    semantic_pooled["complete_case_accuracy"]
                    - baselines["B1_bm25"]["semantic_tasks"]["complete_case_accuracy"]
                ),
                "overall_complete_case_points": 100
                * (
                    pooled["complete_case_accuracy"]
                    - baselines["B1_bm25"]["tasks"]["complete_case_accuracy"]
                ),
            },
        }
    report = {
        "issue": 183,
        "block": 5,
        "status": "complete_classification",
        "split": "evaluation",
        "frozen_config_sha256": hashlib.sha256(FINAL.read_bytes()).hexdigest(),
        "evaluation_sources": source_hashes(),
        "cases": len(cases),
        "groups": len({c["group_id"] for c in cases}),
        "semantic_cases": len(semantic),
        "retrieval": metrics(ranking["rows"], gold),
        "semantic_retrieval": metrics(
            [r for r in ranking["rows"] if gold[r["case_id"]]["semantic_case"]], gold
        ),
        "B2_scope": (
            "Dense candidates with literal documents; evaluated as retrieval, "
            "not confirmed applicability."
        ),
        "baselines": baselines,
        "models": models,
        "attempts": rows,
        "limitations": [
            "Fictional assistant-authored reference; no operational/user validation.",
            "Variants/seeds correlated; 24 groups, not 144 independent cases.",
            "Objective guards, schema and literal check IDs credited to code.",
            "Classification gates do not reliably detect semantic false positives.",
            "Block6 final audit, uncertainty and recommendation remain pending.",
        ],
    }
    write_new(run / "scores.json", report)
    gate = generation_gate(report, config)
    write_new(run / "generation-gate.json", gate)
    print(
        json.dumps(
            {
                "models": {m: r["pooled_tasks"] for m, r in models.items()},
                "generation_gate_passed": gate["passed"],
            },
            ensure_ascii=False,
        )
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    from run_ai_knowledge_development import allowed_path

    root, run = allowed_path(args.budget_root, args.run_dir)
    score(root, run)


if __name__ == "__main__":
    main()
