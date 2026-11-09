"""Offline selection and freeze; builds hashes, never invokes a model."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from ai_knowledge import (
    DATA,
    ROOT,
    KnowledgeError,
    digest,
    factual_slice,
    inputs,
    project,
    read,
    verify_bundle,
    write_new,
)
from ai_knowledge_reader import reader_messages, reader_schema
from ai_knowledge_retrieval import queries
from run_ai_knowledge_development import BASE, DEVELOPMENT, source_hashes


def selection_key(task, seconds=0):
    return (
        -task["high_errors_exposed"],
        task["complete_case_accuracy"] or 0,
        task["coverage"] or 0,
        task["precision"] or 0,
        -seconds,
    )


def choose(report):
    if report["kind"] != "validation" or report["split"] != "validation":
        raise KnowledgeError("completed_validation_scores_required")
    configs = {}
    for key, group in report["groups"].items():
        model, profile, variant = key.split("/")
        if model in configs:
            raise KnowledgeError("one_prefrozen_configuration_per_model_required")
        policy = max(group["tasks"], key=lambda p: selection_key(group["tasks"][p]))
        configs[model] = {
            "profile": profile,
            "variant": variant,
            "policy": policy,
            "validation": group["tasks"][policy],
            "mean_reader_call_seconds": group["mean_seconds"],
        }
    if set(configs) != set(read(BASE)["models"]):
        raise KnowledgeError("both_models_required")
    best = max(
        configs,
        key=lambda m: selection_key(
            configs[m]["validation"], configs[m]["mean_reader_call_seconds"]
        ),
    )
    return configs, best


def reader_body(model, config, card, envelope, seed):
    protocol = read(BASE)
    profile = protocol["profiles"][config["profile"]]
    options = {k: v for k, v in profile.items() if k != "think"}
    options.update(num_ctx=4096, num_predict=512, num_thread=6, seed=seed)
    return {
        "model": model,
        "messages": reader_messages(card, envelope, config["variant"]),
        "format": reader_schema(card, envelope, config["variant"]),
        "stream": False,
        "think": profile["think"],
        "keep_alive": 600,
        "options": options,
    }


def generation_body(model, config, card, envelope, selected, seed):
    body = reader_body(model, config, card, envelope, seed)
    body.pop("format")
    body["messages"] = [
        {"role": "system", "content": read(DEVELOPMENT)["generation"]["prompt"]},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "experimental_card": {
                        k: v for k, v in card.items() if k != "examples"
                    },
                    "selected": selected,
                    "facts": factual_slice(card, envelope),
                    "immutable_verification": card["verification"],
                    "limits": (
                        "Data and documents are fictional. Never authorize release."
                    ),
                },
                ensure_ascii=False,
            ),
        },
    ]
    return body


def matrix(configs):
    """Freeze every possible reader payload before retrieval picks candidates.

    Reads reserved INPUTS for serialization only; never labels or model outputs.
    Future inference may use only the two candidates selected by the frozen rule.
    """
    cases = inputs("evaluation")
    cards = [c for c in read(DATA / "knowledge.json") if c["status"] == "current"]
    protocol = read(BASE)
    task = protocol["retrieval"]["query_instruction"]
    seeds = protocol["evaluation"]["seeds"]
    result = {"split": "evaluation", "inference_executed": False, "cases": {}}
    for case in cases:
        envelope = project(case)
        result["cases"][case["case_id"]] = {
            "queries": [f"Instruct: {task}\nQuery: {q}" for q in queries(envelope)],
            "reader_bodies_sha256": {
                f"{model}/{card['id']}/{seed}": digest(
                    reader_body(model, cfg, card, envelope, seed)
                )
                for model, cfg in configs.items()
                for card in cards
                for seed in seeds
            },
        }
    ids = [c["case_id"] for c in cases]
    result["execution_order"] = {}
    for index, seed in enumerate(seeds):
        order = ids.copy()
        random.Random(183000 + seed).shuffle(order)
        models = list(protocol["models"])
        if index % 2:
            models.reverse()
        result["execution_order"][str(seed)] = {"models": models, "cases": order}
    # Alternating variant within each group; 3 cases/stratum and 12 A/12 B.
    result["generation_preselected_cases"] = [
        f"E{2 * group + (1 if group % 2 == 0 else 2):02d}" for group in range(24)
    ]
    return result


def freeze(run, budget_root, config_path, matrix_path):
    verify_bundle()
    if not (run / "complete.json").exists():
        raise KnowledgeError("completed_validation_required")
    report, plan = read(run / "scores.json"), read(run / "plan.json")
    configs, best = choose(report)
    frozen_matrix = matrix(configs)
    files = source_hashes()
    files[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    files.update(
        {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in DATA.iterdir()
            if p.is_file()
        }
    )
    ledger = read(budget_root / "budget.json")
    if any(r["state"] != "completed" for r in ledger["receipts"]):
        raise KnowledgeError("unresolved_inference")
    config = {
        "version": "1.0.0-final-frozen",
        "issue": 183,
        "authorized_completed_blocks": [1, 2, 3, 4],
        "blocks_5_6_authorized": False,
        "reserved_inference_executed": False,
        "require_new_approval_before_inference": True,
        "files": files,
        "validation_scores_sha256": digest(report),
        "validation_requests_sha256": plan["requests_sha256"],
        "matrix_path": str(matrix_path.resolve().relative_to(ROOT)),
        "matrix_sha256": digest(frozen_matrix),
        "models": configs,
        "model_pins": plan["protocol"]["models"],
        "runtime": plan["protocol"]["runtime"],
        "model_configuration_snapshot": read(sorted(run.glob("batch-*.json"))[0])[
            "inventory"
        ]["configuration"],
        "retrieval_parameters": plan["protocol"]["retrieval"],
        "generation_model": best,
        "retriever": plan["selection"]["retriever"],
        "reader_max_cards": 2,
        "seeds": read(BASE)["evaluation"]["seeds"],
        "generation": read(DEVELOPMENT)["generation"],
        "rubric": "docs/ai-knowledge-poc-rubric.json",
        "operational_batch_rule": (
            "One model per batch, at most 32 calls/550 seconds; same resource stops. "
            "Verify memory/paging and runtime empty after any resource stop before "
            "resuming pending requests."
        ),
        "budget_at_freeze": {k: v for k, v in ledger.items() if k != "receipts"},
        "measurement_limits": (
            "Warm reader timings have prepared context/embeddings; cold interactive "
            "embedding-to-reader switching is not a measured product SLA. Fictional "
            "assistant-authored corpus, correlated variants/seeds, no user utility "
            "measurement."
        ),
    }
    write_new(matrix_path, frozen_matrix)
    write_new(config_path, config)
    return config


def verify(config_path):
    config = read(config_path)
    for name, sha in config["files"].items():
        path = (ROOT / name).resolve()
        if (
            not path.is_relative_to(ROOT)
            or hashlib.sha256(path.read_bytes()).hexdigest() != sha
        ):
            raise KnowledgeError(f"frozen_file_changed:{name}")
    if digest(read(ROOT / config["matrix_path"])) != config["matrix_sha256"]:
        raise KnowledgeError("frozen_matrix_changed")
    if digest(matrix(config["models"])) != config["matrix_sha256"]:
        raise KnowledgeError("frozen_serialization_changed")
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-run", type=Path, required=True)
    parser.add_argument("--budget-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    args = parser.parse_args()
    result = freeze(args.validation_run, args.budget_root, args.config, args.matrix)
    print(
        f"Frozen; selected writing model: {result['generation_model']}; no inference."
    )


if __name__ == "__main__":
    main()
