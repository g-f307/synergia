"""Offline final audit of #183: no runtime, inference or mutation of frozen data."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import re
from collections import Counter
from pathlib import Path

from ai_knowledge import (
    DATA,
    ROOT,
    KnowledgeError,
    digest,
    inputs,
    project,
    read,
    validate_corpus,
    values,
    write_new,
)
from ai_knowledge_reader import STRUCTURED, assess, focused_retrieve, objective_status
from ai_knowledge_retrieval import document, retrieve
from freeze_ai_knowledge import reader_body, verify
from render_ai_knowledge_final import render_html

DESIGN = ROOT / "docs/ai-knowledge-poc-audit-design.json"
COUNTS = (
    "cases",
    "answerable",
    "displayed_items",
    "correct_displayed_items",
    "high_errors_exposed",
    "covered_cases",
    "complete_cases",
    "correct_check_cases",
)
RATIOS = {
    "precision": ("correct_displayed_items", "displayed_items"),
    "coverage": ("covered_cases", "answerable"),
    "complete_case_accuracy": ("complete_cases", "cases"),
    "next_check_relevance": ("correct_check_cases", "answerable"),
}


def require(condition, code):
    if not condition:
        raise KnowledgeError(code)


def label_free_messages(body):
    # Inspect decoded content, not a second JSON encoding that escapes its quotes.
    content = "\n".join(m["content"] for m in body["messages"])
    for forbidden in [
        "relevant_cards",
        "semantic_annotations",
        "expected_checks",
        "group_id",
        "stratum",
        "case_id",
    ]:
        require(forbidden not in content, "reference_key_in_payload")


def ratios(counts):
    return {
        **counts,
        **{
            name: counts[num] / counts[den] if counts[den] else None
            for name, (num, den) in RATIOS.items()
        },
    }


def count_cases(cases, rows, gold, cards, policy="supported_and_possible"):
    """Independent integer recount, including check IDs and empty cases.

    Does not call the frozen task_metrics/pooling evaluator. Predicate/reference
    booleans are separately recomputed against the unchanged frozen reader.
    """
    allowed = (
        {"supported", "possible"}
        if policy == "supported_and_possible"
        else {"supported"}
    )
    total = {k: 0 for k in COUNTS}
    outcomes = []
    for case in cases:
        cid = case["case_id"]
        ref = gold[cid]
        shown = [
            r
            for r in rows
            if r["case_id"] == cid
            and r["guard_accepted"]
            and r["parsed"]["status"] in allowed
        ]
        correct = [
            r
            for r in shown
            if r["schema_valid"]
            and r["reference_valid"]
            and r["missing_valid"]
            and r["parsed"]["status"] == ref["expected"][r["card_id"]]
        ]
        correct_cards = {r["card_id"] for r in correct}
        expected = set(ref["relevant_cards"])
        covered = bool(expected & correct_cards)
        checks_ok = (
            covered
            and len(correct) == len(shown)
            and all(
                cards[r["card_id"]]["verification"]["id"] in ref["expected_checks"]
                for r in shown
            )
        )
        complete = correct_cards == expected and len(correct) == len(shown)
        current = {
            "cases": 1,
            "answerable": int(bool(expected)),
            "displayed_items": len(shown),
            "correct_displayed_items": len(correct),
            "high_errors_exposed": sum(
                r["parsed"]["status"] == "supported"
                and ref["expected"][r["card_id"]] != "supported"
                for r in shown
            ),
            "covered_cases": int(covered),
            "complete_cases": int(complete),
            "correct_check_cases": int(checks_ok),
        }
        for key in COUNTS:
            total[key] += current[key]
        outcomes.append({"case_id": cid, "group_id": case["group_id"], **current})
    return ratios(total), outcomes


def aggregate_groups(contributions, indices):
    # Keep draw multiplicity. A dictionary keyed by group would incorrectly drop it.
    return ratios({k: sum(contributions[i][k] for i in indices) for k in COUNTS})


def quantile(samples, probability):
    if not samples:
        return None
    data = sorted(samples)
    position = (len(data) - 1) * probability
    lo, hi = math.floor(position), math.ceil(position)
    return data[lo] + (data[hi] - data[lo]) * (position - lo)


def bootstrap(arms, draws=10000, seed=183006):
    """Paired group bootstrap, retaining variants/seeds and ratio denominators."""
    groups = len(next(iter(arms.values())))
    require(
        groups > 0 and all(len(a) == groups for a in arms.values()),
        "unequal_group_panels",
    )
    names = list(arms)
    estimates = {name: aggregate_groups(arms[name], range(groups)) for name in names}
    series = {name: {metric: [] for metric in RATIOS} for name in names}
    differences = {
        name: {metric: [] for metric in RATIOS} for name in names if name != "B1"
    }
    rng = random.Random(seed)
    for _ in range(draws):
        selected = [rng.randrange(groups) for _ in range(groups)]
        values_ = {name: aggregate_groups(arms[name], selected) for name in names}
        for name in names:
            for metric in RATIOS:
                value = values_[name][metric]
                if value is not None:
                    series[name][metric].append(value)
                baseline = values_["B1"][metric]
                if name != "B1" and value is not None and baseline is not None:
                    differences[name][metric].append(value - baseline)

    def interval(data, point):
        return {
            "estimate": point,
            "low": quantile(data, 0.025),
            "high": quantile(data, 0.975),
            "defined_draws": len(data),
            "undefined_draws": draws - len(data),
        }

    return {
        "groups": groups,
        "draws": draws,
        "seed": seed,
        "arms": {
            name: {m: interval(series[name][m], estimates[name][m]) for m in RATIOS}
            for name in names
        },
        "paired_differences_vs_B1": {
            name: {
                m: interval(
                    differences[name][m],
                    estimates[name][m] - estimates["B1"][m]
                    if estimates[name][m] is not None and estimates["B1"][m] is not None
                    else None,
                )
                for m in RATIOS
            }
            for name in differences
        },
    }


def wilson(successes, total, z=1.959963984540054):
    require(total > 0 and 0 <= successes <= total, "invalid_binomial_counts")
    p, d = successes / total, 1 + z * z / total
    center = (p + z * z / (2 * total)) / d
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return {
        "successes": successes,
        "total": total,
        "estimate": p,
        "low": 0.0 if successes == 0 else max(0.0, center - half),
        "high": 1.0 if successes == total else min(1.0, center + half),
    }


def ledger_audit(ledger):
    receipts = ledger["receipts"]
    require(all(r["state"] == "completed" for r in receipts), "unresolved_receipt")
    paths = [r["result"] for r in receipts]
    require(len(paths) == len(set(paths)), "duplicated_attempt_receipt")
    chats = sum(r["count"] for r in receipts if r["route"] == "chat")
    texts = sum(r["count"] for r in receipts if r["route"] == "embed")
    seconds = sum(r["elapsed_seconds"] for r in receipts)
    require(chats == ledger["generative_calls"], "generative_accounting_mismatch")
    require(texts == ledger["embedding_texts"], "embedding_accounting_mismatch")
    require(abs(seconds - ledger["active_seconds"]) < 1e-6, "time_accounting_mismatch")
    return {
        "receipts": len(receipts),
        "generative_calls": chats,
        "embedding_texts": texts,
        "active_seconds": seconds,
        "unique_results": len(set(paths)),
        "phase_calls": dict(
            Counter(r.get("phase", "probes") for r in receipts if r["route"] == "chat")
        ),
    }


def reconstruct(source, patch):
    """Apply the archived unified patch without modifying the workspace."""
    original, diff = source.splitlines(True), patch.splitlines(True)
    result, cursor, i = [], 0, 0
    while i < len(diff):
        if not diff[i].startswith("@@"):
            i += 1
            continue
        match = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", diff[i])
        require(match is not None, "invalid_historical_patch")
        start = max(0, int(match[1]) - 1)
        result.extend(original[cursor:start])
        cursor = start
        i += 1
        while i < len(diff) and not diff[i].startswith("@@"):
            line = diff[i]
            i += 1
            if line.startswith("\\"):
                continue
            require(line[:1] in {" ", "+", "-"}, "invalid_patch_operation")
            if line[:1] in {" ", "-"}:
                require(
                    cursor < len(original) and original[cursor] == line[1:],
                    "historical_patch_context_mismatch",
                )
                cursor += 1
            if line[:1] in {" ", "+"}:
                result.append(line[1:])
    result.extend(original[cursor:])
    return "".join(result)


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historic_sources(block12, block34):
    count = 0
    archived = read(ROOT / "docs/evidence/issue-183-historical-source-patches.json")
    for name, sha in block12["frozen_source_hashes"].items():
        source = (ROOT / name).read_bytes()
        if hashlib.sha256(source).hexdigest() != sha:
            patch = archived["patches"][name]
            require(patch["expected_sha256"] == sha, "historical_target_mismatch")
            source = reconstruct(source.decode(), patch["patch"]).encode()
        require(hashlib.sha256(source).hexdigest() == sha, "block2_source_mismatch")
        count += 1
    for entry in block34["runs"].values():
        for name, sha in entry["source_hashes"].items():
            raw = (ROOT / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != sha:
                patch = entry["historical_source_reconstruction_patches"].get(name)
                require(bool(patch), f"missing_historical_source:{name}")
                raw = reconstruct(raw.decode(), patch).encode()
            require(
                hashlib.sha256(raw).hexdigest() == sha,
                f"historical_source_mismatch:{name}",
            )
            count += 1
    return {
        "source_hash_comparisons": count,
        "original_block2_commit": "739d3fd",
        "requires_old_git_objects": False,
        "block3_4_patches_reconstruct": True,
    }


def historical_payloads(block12, block34, cards):
    checked = 0
    for entry in block34["runs"].values():
        by_id = {c["case_id"]: c for c in inputs(entry["split"])}
        for raw in entry["raw_synthetic_outputs"]:
            body = reader_body(
                raw["model"],
                raw,
                cards[raw["card_id"]],
                project(by_id[raw["case_id"]]),
                raw["seed"],
            )
            require(digest(body) == raw["request_sha256"], "historical_payload_changed")
            label_free_messages(body)
            checked += 1
    by_id = {c["case_id"]: c for c in inputs("development")}
    for raw in block12["probes"]:
        body = reader_body(
            raw["model"],
            {"profile": "historical", "variant": "minimal"},
            cards[raw["card_id"]],
            project(by_id[raw["case_id"]]),
            125,
        )
        require(digest(body) == raw["request_sha256"], "probe_payload_changed")
        label_free_messages(body)
        checked += 1
    return checked


def blindness_data(data, seed=183007):
    result = copy.deepcopy(data)
    mapping = {}
    rng = random.Random(seed)
    for case in result["cases"]:
        names = list(dict.fromkeys(p["name"] for p in case["panels"]))
        rng.shuffle(names)
        labels = {name: f"Painel {chr(65 + i)}" for i, name in enumerate(names)}
        mapping[case["case_id"]] = {label: name for name, label in labels.items()}
        for panel in case["panels"]:
            panel["name"] = labels[panel["name"]]
            for key in ["policy", "raw", "blocked"]:
                panel.pop(key, None)
            for item in panel["items"]:
                item.pop("correct", None)
                item.pop("high_error", None)
        case["panels"].sort(key=lambda p: (p["name"], p["seed"] or 0))
    return result, mapping


def final_audit():
    design = read(DESIGN)
    for name, sha in design["inputs_sha256"].items():
        require(file_sha(ROOT / name) == sha, f"audit_input_changed:{name}")
    config = verify(ROOT / "docs/ai-knowledge-poc-final-config.json")
    corpus = validate_corpus()
    b12 = read(ROOT / "docs/evidence/issue-183-blocks-1-2.json")
    b34 = read(ROOT / "docs/evidence/issue-183-blocks-3-4.json")
    final = read(ROOT / "docs/evidence/issue-183-block5.json")
    require(
        final["budget"]["receipts"][: len(b34["budget"]["receipts"])]
        == b34["budget"]["receipts"],
        "historical_budget_prefix_changed",
    )
    accounting = ledger_audit(final["budget"])
    cards = {c["id"]: c for c in read(DATA / "knowledge.json")}
    cases = inputs("evaluation")
    by_id = {c["case_id"]: c for c in cases}
    gold = read(DATA / "evaluation-gold.json")
    sources = historic_sources(b12, b34)
    sources["reconstructed_historical_payloads"] = historical_payloads(b12, b34, cards)
    structured_labels = 0
    for split in ["development", "validation", "evaluation"]:
        reference = read(DATA / f"{split}-gold.json")
        for case in inputs(split):
            envelope = project(case)
            for cid in STRUCTURED:
                require(
                    objective_status(cid, envelope)
                    == reference[case["case_id"]]["expected"][cid],
                    "documented_structured_reference_disagreement",
                )
                structured_labels += 1
    assessments, errors, original_bodies = 0, [], []
    for row, raw in zip(
        final["scores"]["attempts"], final["raw_synthetic_outputs"], strict=True
    ):
        require(
            (row["case_id"], row["card_id"], row["model"], row["seed"])
            == (raw["case_id"], raw["card_id"], raw["model"], raw["seed"]),
            "raw_row_identity_mismatch",
        )
        body = reader_body(
            row["model"],
            config["models"][row["model"]],
            cards[row["card_id"]],
            project(by_id[row["case_id"]]),
            row["seed"],
        )
        require(digest(body) == raw["request_sha256"], "raw_payload_mismatch")
        original_bodies.append(
            {
                "case_id": row["case_id"],
                "card_id": row["card_id"],
                "model": row["model"],
                "seed": row["seed"],
                "body": body,
            }
        )
        text = raw["response"]["message"]["content"]
        require(
            row["raw_content"] == text
            and row["error"] == raw["error"]
            and row["elapsed_seconds"] == raw["elapsed_seconds"],
            "raw_export_mismatch",
        )
        assessment = assess(
            cards[row["card_id"]],
            project(by_id[row["case_id"]]),
            text,
            raw["response"].get("done_reason"),
        )
        require(
            all(row[k] == v for k, v in assessment.items()), "raw_reassessment_mismatch"
        )
        require(
            row["expected_status"] == gold[row["case_id"]]["expected"][row["card_id"]],
            "reference_label_mismatch",
        )
        require(
            row["status_correct"]
            == (
                row["schema_valid"]
                and row["parsed"]["status"] == row["expected_status"]
            ),
            "status_count_mismatch",
        )
        require(
            row["complete_raw"]
            == bool(
                row["status_correct"]
                and row["reference_valid"]
                and row["missing_valid"]
            ),
            "complete_flag_mismatch",
        )
        require(
            row["high_error_raw"]
            == bool(
                row["schema_valid"]
                and row["parsed"]["status"] == "supported"
                and row["expected_status"] != "supported"
            ),
            "severity_flag_mismatch",
        )
        label_free_messages(body)
        assessments += 1
        if not row["complete_raw"]:
            errors.append(error_record(row, cards, by_id))
    require(
        digest(original_bodies) == final["classification_plan"]["requests_sha256"],
        "classification_sequence_changed",
    )
    require(
        len(
            {
                (r["model"], r["seed"], r["case_id"], r["card_id"])
                for r in final["scores"]["attempts"]
            }
        )
        == 438,
        "duplicated_final_attempt",
    )
    models, all_outcomes = {}, {}
    for model, setting in config["models"].items():
        outcomes, totals = [], []
        for seed in config["seeds"]:
            rows = [
                r
                for r in final["scores"]["attempts"]
                if r["model"] == model and r["seed"] == seed
            ]
            counts, sample = count_cases(cases, rows, gold, cards, setting["policy"])
            recorded = final["scores"]["models"][model]["seeds"][str(seed)]["tasks"]
            require(
                all(recorded[k] == counts[k] for k in [*COUNTS, *RATIOS]),
                "independent_case_recount_mismatch",
            )
            totals.append(counts)
            outcomes.extend({**o, "seed": seed} for o in sample)
        pooled = ratios({k: sum(t[k] for t in totals) for k in COUNTS})
        require(
            all(
                pooled[k] == final["scores"]["models"][model]["pooled_tasks"][k]
                for k in [*COUNTS, *RATIOS]
            ),
            "independent_pooling_mismatch",
        )
        models[model] = {
            "recount": pooled,
            "error_families": dict(
                Counter(e["family"] for e in errors if e["model"] == model)
            ),
        }
        all_outcomes[model] = outcomes
    baseline_rows = final["scores"]["baselines"]["B1_bm25"]["rows"]
    baseline, sample = count_cases(cases, baseline_rows, gold, cards)
    require(
        all(
            baseline[k] == final["scores"]["baselines"]["B1_bm25"]["tasks"][k]
            for k in [*COUNTS, *RATIOS]
        ),
        "baseline_recount_mismatch",
    )
    all_outcomes["B1"] = [
        {**o, "seed": seed} for seed in config["seeds"] for o in sample
    ]
    for row in baseline_rows:
        if not row["complete_raw"]:
            errors.append(
                error_record({**row, "model": "B1", "seed": None}, cards, by_id)
            )
    stats = {}
    group_diagnostic = {}
    for subset in ["all", "semantic"]:
        selected = {
            c["case_id"]
            for c in cases
            if subset == "all" or gold[c["case_id"]]["semantic_case"]
        }
        groups = sorted({c["group_id"] for c in cases if c["case_id"] in selected})
        arms = {}
        for arm, outcomes in all_outcomes.items():
            arms[arm] = [
                {
                    k: sum(
                        o[k]
                        for o in outcomes
                        if o["group_id"] == group and o["case_id"] in selected
                    )
                    for k in COUNTS
                }
                for group in groups
            ]
            if subset == "all":
                correct_groups = sum(
                    all(o["complete_cases"] for o in outcomes if o["group_id"] == group)
                    for group in groups
                )
                group_diagnostic[arm] = wilson(
                    correct_groups, len(groups), design["wilson"]["z"]
                )
        stats[subset] = bootstrap(
            arms, design["bootstrap"]["draws"], design["bootstrap"]["seed"]
        )
    sensitivity = calibration_sensitivity(b34, cards)
    strata = {}
    for stratum in sorted({g["stratum"] for g in gold.values()}):
        selected = [c for c in cases if gold[c["case_id"]]["stratum"] == stratum]
        ids = {c["case_id"] for c in selected}
        strata[stratum] = {"B1": count_cases(selected, baseline_rows, gold, cards)[0]}
        for model in models:
            strata[stratum][model] = ratios(
                {
                    k: sum(o[k] for o in all_outcomes[model] if o["case_id"] in ids)
                    for k in COUNTS
                }
            )
    card_coverage = {
        cid: {
            "reference_states": dict(
                Counter(g["expected"][cid] for g in gold.values())
            ),
            "candidate_cases": sum(
                cid in r for r in final["classification_plan"]["rankings"].values()
            ),
            "llm_calls": sum(r["card_id"] == cid for r in final["scores"]["attempts"]),
        }
        for cid in gold["E01"]["expected"]
    }
    for row in final["scores"]["attempts"]:
        require(
            not (
                row["card_id"] == "K03"
                and values(project(by_id[row["case_id"]]))["long_hold"] is False
            ),
            "K03_ambiguity_present_in_final",
        )
    checks = {
        "protected_freeze_valid": True,
        "corpus": corpus,
        "accounting": accounting,
        "sources": sources,
        "structured_reference_labels_checked": structured_labels,
        "reconstructed_final_payloads": assessments,
        "independent_case_counts_match": True,
        "baseline": baseline,
        "private_artifacts": private_audit(final),
        "generation_skipped": final["generation"]["status"] == "not_run_gate_failed",
        "no_new_inference": True,
    }
    return {
        "issue": 183,
        "block": 6,
        "client_date": design["client_date"],
        "analysis_design_sha256": file_sha(DESIGN),
        "checks": checks,
        "models": models,
        "uncertainty": stats,
        "strata": strata,
        "final_card_coverage": card_coverage,
        "baseline_replication_for_pairing_only": 3,
        "group_all_correct_wilson": group_diagnostic,
        "calibration_erratum_sensitivity": sensitivity,
        "final_K03_false_calls": 0,
        "case_outcomes": all_outcomes,
        "errors": errors,
        "error_count": len(errors),
        "limitations": [
            "Consistency audit, not independent operational/semantic judging.",
            "Assistant-authored corpus; intervals do not estimate real prevalence.",
            "Group bootstrap retains variants/seeds; only 24/10 groups.",
            "Calibration erratum disclosed; reference and outputs stay frozen.",
        ],
    }


def error_record(row, cards, by_id):
    high = row["high_error_raw"]
    family = (
        "unsupported_sustentation_" + row["expected_status"]
        if high
        else "wrong_state"
        if not row["status_correct"]
        else "missing_decisive_reference"
        if not row["reference_valid"]
        else "incorrect_missing_fields"
    )
    parsed = row["parsed"] or {}
    envelope = project(by_id[row["case_id"]])
    return {
        "model": row["model"],
        "seed": row.get("seed"),
        "case_id": row["case_id"],
        "card_id": row["card_id"],
        "family": family,
        "severity": "high" if high else "medium",
        "guard_accepted": row["guard_accepted"],
        "rejection": row["rejection"],
        "expected": row["expected_status"],
        "actual": parsed,
        "note": values(envelope)["note"],
        "cited_facts": [
            f for f in envelope["facts"] if f["id"] in parsed.get("evidence_ids", [])
        ],
        "document_reference": cards[row["card_id"]]["criteria"][row["expected_status"]],
    }


def calibration_sensitivity(block34, cards):
    entry = block34["runs"]["calibration"]
    cases = {c["case_id"]: c for c in inputs("development")}
    affected = [
        r
        for r in entry["scores"]["attempts"]
        if r["card_id"] == "K03"
        and values(project(cases[r["case_id"]]))["long_hold"] is False
    ]
    results = {}
    for key, original in entry["scores"]["groups"].items():
        model, profile, variant = key.split("/")
        rows = [
            r
            for r in affected
            if (r["model"], r["profile"], r["variant"]) == (model, profile, variant)
        ]
        credit = sum(
            r["parsed"]["status"] in {"rejected", "not_applicable"}
            and not r["status_correct"]
            for r in rows
        )
        complete_credit = sum(
            r["parsed"]["status"] in {"rejected", "not_applicable"}
            and r["reference_valid"]
            and r["missing_valid"]
            and not r["complete_raw"]
            for r in rows
        )
        results[key] = {
            "attempts": original["attempts"],
            "original_status_correct": original["status_correct"],
            "negative_equivalence_status_correct": original["status_correct"] + credit,
            "original_complete_raw": original["complete_raw"],
            "negative_equivalence_complete_raw": original["complete_raw"]
            + complete_credit,
        }
    return {
        "card": "K03",
        "case": "D18",
        "affected_calls": len(affected),
        "groups": results,
        "standing": (
            "Sensitivity only; original gold, guard decisions and metrics retained. "
            "No new call."
        ),
    }


def private_audit(final):
    root = ROOT / read(ROOT / "docs/ai-knowledge-poc-block5.json")["budget_root"]
    if not (root / "budget.json").exists():
        return {
            "available": False,
            "scope": "Public evidence only; raw files not installed.",
        }
    require(read(root / "budget.json") == final["budget"], "private_ledger_changed")
    checked, vectors_by_text = 0, {}
    pin = read(ROOT / "docs/ai-knowledge-poc-final-config.json")[
        "retrieval_parameters"
    ]["embedding_digest"]
    for receipt in final["budget"]["receipts"]:
        path = (root / receipt["result"]).resolve()
        require(
            path.is_relative_to(root.resolve()) and path.is_file(),
            "missing_private_attempt",
        )
        raw = read(path)
        require(
            raw["error"] is None
            and raw["elapsed_seconds"] == receipt["elapsed_seconds"],
            "private_receipt_mismatch",
        )
        if receipt["route"] == "embed":
            texts, vectors = raw["request"]["input"], raw["response"]["embeddings"]
            require(len(texts) == len(vectors), "private_embedding_count_mismatch")
            for text, vector in zip(texts, vectors, strict=True):
                key = digest({"model": pin, "text": text, "context": 4096})
                cached = read(root / "embedding-cache" / f"{key}.json")
                require(
                    cached["key"] == key and cached["vector"] == vector,
                    "private_embedding_cache_changed",
                )
                vectors_by_text[text] = vector
        checked += 1
    for i, sha in enumerate(final["completion"]["raw_sha256"]):
        require(
            file_sha(root / f"evaluation/classification/attempt-{i:03d}.json") == sha,
            "private_final_raw_changed",
        )
    require(not (root / "inference.lock").exists(), "inference_still_locked")
    cfg = read(ROOT / "docs/ai-knowledge-poc-final-config.json")
    matrix = read(ROOT / cfg["matrix_path"])
    cards = [c for c in read(DATA / "knowledge.json") if c["status"] == "current"]
    vectors = {c["id"]: vectors_by_text[document(c)] for c in cards}
    recorded = {
        r["case_id"]: r["rankings"] for r in final["retrieval"]["rankings"]["rows"]
    }
    for case in inputs("evaluation"):
        cid, envelope = case["case_id"], project(case)
        qs = [vectors_by_text[t] for t in matrix["cases"][cid]["queries"]]
        current = {
            **{
                f"initial/{k}": v
                for k, v in retrieve(cards, envelope, vectors, qs).items()
            },
            **{
                f"focused/{k}": v
                for k, v in focused_retrieve(cards, envelope, vectors, qs).items()
            },
        }
        require(current == recorded[cid], "private_retrieval_rankings_changed")
        require(
            recorded[cid][cfg["retriever"]][:2]
            == final["classification_plan"]["rankings"][cid],
            "reader_candidates_differ_from_retrieval",
        )
    return {
        "available": True,
        "raw_files_checked": checked,
        "final_raw_hashes_checked": 438,
        "embedding_texts_checked": len(vectors_by_text),
        "retrieval_cases_recomputed": 48,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blind-output", type=Path)
    args = parser.parse_args()
    result = final_audit()
    if args.blind_output:
        html = (ROOT / "docs/ai-knowledge-poc-comparison.html").read_text()
        payload = html.split('<script id="data" type="application/json">', 1)[1].split(
            "</script>", 1
        )[0]
        data, mapping = blindness_data(
            json.loads(payload), read(DESIGN)["blind_presentation"]["seed"]
        )
        blinded = render_html(data).replace(
            "PoC #183 · orientação investigativa",
            "PoC #183 · comparação sem identificação",
        )
        blinded = blinded.replace(
            '<label><input type="checkbox" id="audit">',
            '<label style="display:none"><input type="checkbox" id="audit">',
        )
        with args.blind_output.open("x") as stream:
            stream.write(blinded)
        write_new(args.blind_output.with_suffix(".mapping.json"), mapping)
        result["blind_presentation"] = {
            "path": str(args.blind_output),
            "sha256": file_sha(args.blind_output),
            "human_evaluation_executed": False,
        }
    result["audit_code_sha256"] = file_sha(Path(__file__))
    write_new(args.output, result)
    print(
        json.dumps(
            {
                "audited_calls": 438,
                "ledger": result["checks"]["accounting"],
                "errors_catalogued": result["error_count"],
                "sensitivity_calls": result["calibration_erratum_sensitivity"][
                    "affected_calls"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
