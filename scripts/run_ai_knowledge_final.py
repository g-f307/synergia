"""Block-5 inference only: frozen payloads, shared budget, one model per batch.

No gold loader, scoring, retries or semantic repair. Frozen files stay unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
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
from ai_knowledge_reader import assess, focused_retrieve
from ai_knowledge_retrieval import cosine, document, queries, retrieve
from ai_knowledge_runtime import Budget, Runtime
from ai_reevaluation_telemetry import Sampler, hardware
from freeze_ai_knowledge import generation_body, reader_body, verify
from run_ai_knowledge_development import BASE, allowed_path, resource_limits

AUTH = ROOT / "docs/ai-knowledge-poc-block5.json"
FINAL = ROOT / "docs/ai-knowledge-poc-final-config.json"
SOURCES = [
    Path(__file__),
    ROOT / "scripts/evaluate_ai_knowledge_final.py",
    ROOT / "scripts/render_ai_knowledge_final.py",
    ROOT / "scripts/templates/ai_knowledge_final.html",
    AUTH,
]


def source_hashes():
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in SOURCES
    }


def context(root):
    authorization = read(AUTH)
    if authorization["approved_blocks"] != [5] or authorization["block6_authorized"]:
        raise KnowledgeError("block5_specific_authorization_required")
    if (
        hashlib.sha256(FINAL.read_bytes()).hexdigest()
        != authorization["frozen_config_sha256"]
    ):
        raise KnowledgeError("final_configuration_changed")
    if root.resolve() != (ROOT / authorization["budget_root"]).resolve():
        raise KnowledgeError("original_shared_budget_required")
    config = verify(FINAL)
    ledger = read(root / "budget.json")
    prefix = ledger["receipts"][: authorization["existing_receipts_count"]]
    if digest(prefix) != authorization["existing_receipts_sha256"]:
        raise KnowledgeError("historical_receipts_changed")
    return config, read(BASE), read(ROOT / config["matrix_path"])


def inventory(runtime, protocol, config):
    result = runtime.inventory(protocol)
    if result["loaded"]["models"]:
        raise KnowledgeError("runtime_not_initially_empty")
    if result["configuration"] != config["model_configuration_snapshot"]:
        raise KnowledgeError("runtime_parameters_or_template_changed")
    return result


def frozen_plan(root, output):
    config, protocol, matrix = context(root)
    plan = read(output / "plan.json")
    if digest(plan) != read(output / "plan-lock.json")["sha256"]:
        raise KnowledgeError("execution_plan_changed")
    for name, sha in plan["sources"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha:
            raise KnowledgeError(f"executor_source_changed:{name}")
    if plan["config_sha256"] != hashlib.sha256(FINAL.read_bytes()).hexdigest():
        raise KnowledgeError("execution_freeze_changed")
    if plan["requests_sha256"] != digest(plan["requests"]):
        raise KnowledgeError("frozen_requests_changed")
    return config, protocol, matrix, plan


def save_plan(output, plan):
    write_new(output / "plan.json", plan)
    write_new(output / "plan-lock.json", {"sha256": digest(plan)})


def base_plan(kind, requests, **metadata):
    return {
        "kind": kind,
        "split": "evaluation",
        "sources": source_hashes(),
        "config_sha256": hashlib.sha256(FINAL.read_bytes()).hexdigest(),
        "requests": requests,
        "requests_sha256": digest(requests),
        **metadata,
    }


def retrieval(root, output):
    config, protocol, matrix = context(root)
    runtime = Runtime()
    runtime_inventory = inventory(runtime, protocol, config)
    cards = [c for c in read(DATA / "knowledge.json") if c["status"] == "current"]
    cases = inputs("evaluation")
    model = protocol["retrieval"]["embedding_model"]
    pin = protocol["retrieval"]["embedding_digest"]
    texts = list(
        dict.fromkeys(
            [document(c) for c in cards]
            + [q for c in matrix["cases"].values() for q in c["queries"]]
        )
    )
    cache_root = root / "embedding-cache"
    cache, missing, used = {}, [], {}
    for text in texts:
        key = digest({"model": pin, "text": text, "context": 4096})
        path = cache_root / f"{key}.json"
        if path.exists():
            cached = read(path)
            if cached["key"] != key:
                raise KnowledgeError("cache_key_mismatch")
            cosine(cached["vector"], cached["vector"])
            cache[text] = cached["vector"]
            used[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            missing.append(text)
    output.mkdir(parents=True, exist_ok=False)
    payloads = [
        {
            "model": model,
            "input": missing[i : i + 8],
            "truncate": False,
            "keep_alive": 600,
            "options": {"num_ctx": 4096},
        }
        for i in range(0, len(missing), 8)
    ]
    save_plan(
        output, base_plan("retrieval", payloads, phase="evaluation", cached_files=used)
    )
    sampler = Sampler(resource_limits(protocol), root)
    safe_unload = True
    with Budget(root, protocol, "evaluation") as budget:
        try:
            with sampler:
                for i, body in enumerate(payloads):
                    if sampler.failure:
                        raise KnowledgeError(f"resource_stop:{sampler.failure}")
                    safe_unload = False
                    raw = budget.call(
                        runtime,
                        "embed",
                        body,
                        output / f"embed-{i:02d}.json",
                        45,
                        len(body["input"]),
                    )
                    safe_unload = True
                    vectors = raw["response"].get("embeddings", [])
                    if len(vectors) != len(body["input"]):
                        raise KnowledgeError("embedding_count_mismatch")
                    for text, vector in zip(body["input"], vectors, strict=True):
                        cosine(vector, vector)
                        key = digest({"model": pin, "text": text, "context": 4096})
                        write_new(
                            cache_root / f"{key}.json", {"key": key, "vector": vector}
                        )
                        cache[text] = vector
        finally:
            if payloads and safe_unload:
                runtime.unload(model)
            write_new(
                output / "telemetry.json",
                {
                    "inventory": runtime_inventory,
                    "hardware": hardware(),
                    "telemetry": sampler.report(),
                    "models_unloaded": runtime.request("ps") if safe_unload else None,
                },
            )
    if sampler.failure:
        raise KnowledgeError(f"resource_stop:{sampler.failure}")
    vectors = {c["id"]: cache[document(c)] for c in cards}
    rows = []
    for case in cases:
        cid, envelope = case["case_id"], project(case)
        task = protocol["retrieval"]["query_instruction"]
        expected_queries = [f"Instruct: {task}\nQuery: {q}" for q in queries(envelope)]
        if expected_queries != matrix["cases"][cid]["queries"]:
            raise KnowledgeError("reserved_query_changed")
        query_vectors = [cache[q] for q in expected_queries]
        started = time.monotonic()
        focused = focused_retrieve(cards, envelope, vectors, query_vectors)
        initial = retrieve(cards, envelope, vectors, query_vectors)
        rows.append(
            {
                "case_id": cid,
                "rankings": {
                    **{f"initial/{k}": v for k, v in initial.items()},
                    **{f"focused/{k}": v for k, v in focused.items()},
                },
                "ranking_seconds": time.monotonic() - started,
            }
        )
    write_new(
        output / "rankings.json",
        {
            "split": "evaluation",
            "rows": rows,
            "new_embedding_texts": len(missing),
            "sources": source_hashes(),
            "gold_accessed": False,
            "config_sha256": hashlib.sha256(FINAL.read_bytes()).hexdigest(),
        },
    )
    print(
        json.dumps({"retrieved_cases": len(rows), "new_embedding_texts": len(missing)})
    )


def prepare(root, retrieval_dir, output):
    config, _, matrix = context(root)
    frozen_plan(root, retrieval_dir)
    ranking = read(retrieval_dir / "rankings.json")
    rankings = {
        r["case_id"]: r["rankings"][config["retriever"]][:2] for r in ranking["rows"]
    }
    cases = {c["case_id"]: c for c in inputs("evaluation")}
    cards = {
        c["id"]: c for c in read(DATA / "knowledge.json") if c["status"] == "current"
    }
    requests = []
    for seed in config["seeds"]:
        order = matrix["execution_order"][str(seed)]
        for model in order["models"]:
            for cid in order["cases"]:
                for kid in rankings[cid]:
                    body = reader_body(
                        model,
                        config["models"][model],
                        cards[kid],
                        project(cases[cid]),
                        seed,
                    )
                    if (
                        digest(body)
                        != matrix["cases"][cid]["reader_bodies_sha256"][
                            f"{model}/{kid}/{seed}"
                        ]
                    ):
                        raise KnowledgeError("reserved_payload_changed")
                    requests.append(
                        {
                            "case_id": cid,
                            "card_id": kid,
                            "model": model,
                            "seed": seed,
                            "body": body,
                        }
                    )
    if len(requests) > 576:
        raise KnowledgeError("final_call_quota_exceeded")
    registry = root / "evaluation-lock.json"
    write_new(
        registry,
        {"run": str(output.relative_to(root)), "requests_sha256": digest(requests)},
    )
    output.mkdir(parents=True, exist_ok=False)
    save_plan(
        output,
        base_plan(
            "classification",
            requests,
            phase="evaluation",
            rankings=rankings,
            retrieval_dir=str(retrieval_dir.relative_to(ROOT)),
            retrieval_sha256=digest(ranking),
        ),
    )
    print(
        json.dumps(
            {"prepared": len(requests), "cases": len(cases), "seeds": config["seeds"]}
        )
    )


def completed(output, plan):
    done = []
    for i, item in enumerate(plan["requests"]):
        path = output / f"attempt-{i:03d}.json"
        if path.exists():
            previous = read(path)
            if previous["error"] or digest(previous["request"]) != digest(item["body"]):
                raise KnowledgeError("attempt_requires_reconciliation")
            done.append(i)
    return done


def execute(root, output, max_calls):
    _, protocol, _, plan = frozen_plan(root, output)
    if plan["kind"] not in {"classification", "generation"}:
        raise KnowledgeError("inference_plan_required")
    runtime = Runtime()
    config = read(FINAL)
    runtime_inventory = inventory(runtime, protocol, config)
    done = completed(output, plan)
    batch = len(list(output.glob("batch-*.json"))) + 1
    sampler = Sampler(resource_limits(protocol), root)
    started, executed, model, safe_unload = time.monotonic(), 0, None, True
    with Budget(root, protocol, plan["phase"]) as budget:
        try:
            with sampler:
                for i, item in enumerate(plan["requests"]):
                    if i in done:
                        continue
                    if executed >= max_calls or time.monotonic() - started > 550:
                        break
                    if model and item["model"] != model:
                        break
                    if sampler.failure:
                        raise KnowledgeError(f"resource_stop:{sampler.failure}")
                    model = item["model"]
                    safe_unload = False
                    raw = budget.call(
                        runtime,
                        "chat",
                        item["body"],
                        output / f"attempt-{i:03d}.json",
                        45,
                    )
                    safe_unload = True
                    done.append(i)
                    executed += 1
                    print(
                        f"{plan['kind']} {len(done)}/{len(plan['requests'])} "
                        f"{model} seed={item['seed']} "
                        f"{item['case_id']}/{item['card_id']} "
                        f"{raw['elapsed_seconds']:.2f}s",
                        flush=True,
                    )
        finally:
            if model and safe_unload:
                runtime.unload(model)
            write_new(
                output / f"batch-{batch:03d}.json",
                {
                    "calls": executed,
                    "completed": len(done),
                    "model": model,
                    "inventory": runtime_inventory,
                    "hardware": hardware(),
                    "telemetry": sampler.report(),
                    "models_unloaded": runtime.request("ps") if safe_unload else None,
                },
            )
    if sampler.failure:
        raise KnowledgeError(f"resource_stop:{sampler.failure}")
    if len(done) == len(plan["requests"]) and not (output / "complete.json").exists():
        hashes = [
            hashlib.sha256((output / f"attempt-{i:03d}.json").read_bytes()).hexdigest()
            for i in sorted(done)
        ]
        write_new(
            output / "complete.json",
            {
                "calls": len(done),
                "raw_sha256": hashes,
                "requests_sha256": plan["requests_sha256"],
            },
        )
    print(
        json.dumps({"done": len(done), "complete": len(done) == len(plan["requests"])})
    )


def prepare_generation(root, classification, output):
    config, _, matrix = context(root)
    _, _, _, plan = frozen_plan(root, classification)
    if not (classification / "complete.json").exists():
        raise KnowledgeError("classification_must_be_complete")
    gate = read(classification / "generation-gate.json")
    scores = read(classification / "scores.json")
    if gate["scores_sha256"] != digest(scores):
        raise KnowledgeError("gate_scores_changed")
    from evaluate_ai_knowledge_final import generation_gate

    if gate != generation_gate(scores, config):
        raise KnowledgeError("gate_decision_changed")
    output.mkdir(parents=True, exist_ok=False)
    if not gate["passed"]:
        write_new(
            output / "decision.json",
            {
                "status": "not_run_gate_failed",
                "gate": gate,
                "preselected_cases": matrix["generation_preselected_cases"],
                "calls": 0,
                "scheduled_case_seed_slots": 72,
                "generation_quality_claim": False,
            },
        )
        print("Generation not run: frozen gate failed; zero calls.")
        return
    cards = {c["id"]: c for c in read(DATA / "knowledge.json")}
    cases = {c["case_id"]: c for c in inputs("evaluation")}
    model = config["generation_model"]
    allowed = (
        {"supported", "possible"}
        if config["models"][model]["policy"] == "supported_and_possible"
        else {"supported"}
    )
    requests, abstentions = [], []
    for seed in config["seeds"]:
        for cid in matrix["generation_preselected_cases"]:
            accepted = []
            for i, item in enumerate(plan["requests"]):
                if (item["seed"], item["model"], item["case_id"]) != (seed, model, cid):
                    continue
                raw = read(classification / f"attempt-{i:03d}.json")
                response = raw["response"] or {}
                card = cards[item["card_id"]]
                assessment = assess(
                    card,
                    project(cases[cid]),
                    response.get("message", {}).get("content", ""),
                    response.get("done_reason"),
                )
                if (
                    assessment["guard_accepted"]
                    and assessment["parsed"]["status"] in allowed
                ):
                    accepted.append((card, assessment["parsed"]))
            if not accepted:
                abstentions.append(
                    {"case_id": cid, "seed": seed, "reason": "not_eligible_selection"}
                )
                continue
            card, selected = accepted[0]
            requests.append(
                {
                    "case_id": cid,
                    "card_id": card["id"],
                    "seed": seed,
                    "model": model,
                    "body": generation_body(
                        model,
                        config["models"][model],
                        card,
                        project(cases[cid]),
                        selected,
                        seed,
                    ),
                }
            )
    save_plan(
        output,
        base_plan(
            "generation",
            requests,
            phase="conditional_generation",
            abstentions=abstentions,
            gate=gate,
        ),
    )
    print(
        json.dumps({"generation_calls": len(requests), "abstentions": len(abstentions)})
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["retrieval", "prepare", "execute", "generation"]
    )
    parser.add_argument("--budget-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--retrieval-dir", type=Path)
    parser.add_argument("--classification-dir", type=Path)
    parser.add_argument("--max-calls", type=int, default=32)
    parser.add_argument("--allow-inference", action="store_true")
    args = parser.parse_args(argv)
    root, output = allowed_path(args.budget_root, args.run_dir)
    if args.command in {"retrieval", "execute"} and not args.allow_inference:
        parser.error("Explicit --allow-inference required")
    if not 1 <= args.max_calls <= 32:
        parser.error("Batch must contain 1 to 32 calls")
    if args.command == "retrieval":
        retrieval(root, output)
    elif args.command == "prepare":
        if not args.retrieval_dir:
            parser.error("--retrieval-dir required")
        prepare(root, allowed_path(root, args.retrieval_dir)[1], output)
    elif args.command == "execute":
        execute(root, output, args.max_calls)
    else:
        if not args.classification_dir:
            parser.error("--classification-dir required")
        prepare_generation(root, allowed_path(root, args.classification_dir)[1], output)


if __name__ == "__main__":
    main()
