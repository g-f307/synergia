"""Frozen, batched development/validation only. No reserved execution command."""

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
    verify_bundle,
    write_new,
)
from ai_knowledge_reader import (
    assess,
    baseline_item,
    focused_retrieve,
    reader_messages,
    reader_schema,
    score_attempt,
    summarize_attempts,
    task_metrics,
)
from ai_knowledge_retrieval import document, metrics, queries, retrieve
from ai_knowledge_runtime import Budget, Runtime
from ai_reevaluation_telemetry import Sampler, hardware

BASE = ROOT / "docs/ai-knowledge-poc-protocol.json"
DEVELOPMENT = ROOT / "docs/ai-knowledge-poc-development.json"
SOURCES = [
    Path(__file__),
    ROOT / "scripts/ai_knowledge.py",
    ROOT / "scripts/ai_knowledge_reader.py",
    ROOT / "scripts/ai_knowledge_runtime.py",
    ROOT / "scripts/ai_knowledge_retrieval.py",
    ROOT / "scripts/ai_reevaluation_telemetry.py",
    BASE,
    DEVELOPMENT,
    ROOT / "docs/ai-knowledge-poc-rubric.json",
    DATA / "manifest.json",
]


def allowed_path(root, target):
    root, target = root.resolve(), target.resolve()
    if (
        not root.is_relative_to(ROOT / ".test-tmp")
        or not target.is_relative_to(root)
        or target == root
    ):
        raise KnowledgeError("campaign_path_required")
    return root, target


def source_hashes():
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in SOURCES
    }


def check_sources(snapshot):
    for name, sha in snapshot["files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha:
            raise KnowledgeError(f"source_changed_since_freeze:{name}")


def resource_limits(protocol):
    return {
        "minimum_available_ram_bytes": 2 * 1024**3,
        "max_swap_growth_bytes": protocol["budget"]["swap_growth_stop_bytes"],
        "reserved_gpu_headroom_bytes": 128 * 1024**2,
        "minimum_available_disk_bytes_before_run": protocol["budget"][
            "minimum_disk_free_bytes"
        ],
        "rss_sampling_interval_seconds": 0.5,
    }


def prepare(kind, output, selection=None, variants=None):
    verify_bundle()
    protocol, design = read(BASE), read(DEVELOPMENT)
    if design["authorization"]["blocks"] != [3, 4]:
        raise KnowledgeError("development_authorization_required")
    split = "validation" if kind == "validation" else "development"
    cases = {c["case_id"]: c for c in inputs(split)}
    cards = {
        c["id"]: c for c in read(DATA / "knowledge.json") if c["status"] == "current"
    }
    if kind == "calibration":
        phase = "calibration"
        pairs = design["calibration_pairs"]
    elif kind == "triage":
        phase = "refinement"
        pairs = design["refinement_pairs"]
        if not selection or not variants or len(variants) != 2:
            raise KnowledgeError("paired_triage_configuration_required")
    elif kind in {"confirm", "validation"}:
        phase = "validation" if kind == "validation" else "refinement"
        if not selection:
            raise KnowledgeError("selection_required")
        if kind == "validation" and not selection.get("development_confirmed"):
            raise KnowledgeError("confirm_development_before_validation")
        ranking = selection["rankings"]
        pairs = [(cid, card_id) for cid in cases for card_id in ranking[cid][:2]]
    else:
        raise KnowledgeError("reserved_or_unknown_kind_refused")
    requests = []
    for model in protocol["models"]:
        profiles = (
            design["calibration_profiles"]
            if kind == "calibration"
            else [selection["models"][model]["profile"]]
        )
        for profile in profiles:
            seeds = design["calibration_seeds"] if kind == "calibration" else [125]
            for seed in seeds:
                choices = (
                    ["minimal"]
                    if kind == "calibration"
                    else variants
                    if kind == "triage"
                    else [selection["models"][model]["variant"]]
                )
                for variant in choices:
                    for cid, card_id in pairs:
                        envelope = project(cases[cid])
                        card = cards[card_id]
                        options = {
                            k: v
                            for k, v in protocol["profiles"][profile].items()
                            if k != "think"
                        }
                        options.update(
                            num_ctx=4096, num_predict=512, num_thread=6, seed=seed
                        )
                        requests.append(
                            {
                                "case_id": cid,
                                "card_id": card_id,
                                "profile": profile,
                                "variant": variant,
                                "seed": seed,
                                "body": {
                                    "model": model,
                                    "messages": reader_messages(
                                        card, envelope, variant
                                    ),
                                    "format": reader_schema(card, envelope, variant),
                                    "stream": False,
                                    "think": False,
                                    "keep_alive": 600,
                                    "options": options,
                                },
                            }
                        )
    if len(requests) > protocol["budget"]["generative_calls"][phase]:
        raise KnowledgeError("plan_exceeds_phase_quota")
    output.mkdir(parents=True, exist_ok=False)
    if kind == "validation":
        relative = output.resolve().relative_to(ROOT / ".test-tmp")
        registry = ROOT / ".test-tmp" / relative.parts[0] / "validation-lock.json"
        write_new(
            registry,
            {
                "run": str(output.resolve().relative_to(ROOT)),
                "selection_sha256": digest(selection),
                "rule": "One validation campaign; no refit after observing labels.",
            },
        )
    plan = {
        "kind": kind,
        "phase": phase,
        "split": split,
        "selection": selection,
        "requests": requests,
        "requests_sha256": digest(requests),
        "protocol": protocol,
        "files": source_hashes(),
        "reserved_allowed": False,
    }
    write_new(output / "plan.json", plan)
    print(json.dumps({"prepared": kind, "calls": len(requests), "split": split}))


def execute(root, output, max_calls):
    plan = read(output / "plan.json")
    check_sources(plan)
    if plan["reserved_allowed"] or plan["split"] not in {"development", "validation"}:
        raise KnowledgeError("reserved_execution_not_authorized")
    if digest(plan["requests"]) != plan["requests_sha256"]:
        raise KnowledgeError("frozen_requests_changed")
    protocol = plan["protocol"]
    runtime = Runtime()
    inventory = runtime.inventory(protocol)
    if inventory["loaded"]["models"]:
        raise KnowledgeError("runtime_not_initially_empty")
    done = []
    for i, item in enumerate(plan["requests"]):
        path = output / f"attempt-{i:03d}.json"
        if path.exists():
            previous = read(path)
            if previous["error"] or digest(previous["request"]) != digest(item["body"]):
                raise KnowledgeError("attempt_requires_reconciliation")
            done.append(i)
    batch = len(list(output.glob("batch-*.json"))) + 1
    sampler = Sampler(resource_limits(protocol), root)
    started, executed, previous, safe_unload = time.monotonic(), 0, None, True
    with Budget(root, protocol, plan["phase"]) as budget:
        try:
            with sampler:
                for index, item in enumerate(plan["requests"]):
                    if index in done:
                        continue
                    if executed >= max_calls or time.monotonic() - started > 550:
                        break
                    if sampler.failure:
                        raise KnowledgeError(f"resource_stop:{sampler.failure}")
                    model = item["body"]["model"]
                    if previous and previous != model:
                        runtime.unload(previous)
                    previous = model
                    safe_unload = False
                    result = budget.call(
                        runtime,
                        "chat",
                        item["body"],
                        output / f"attempt-{index:03d}.json",
                        45,
                    )
                    safe_unload = True
                    done.append(index)
                    executed += 1
                    print(
                        f"{plan['kind']} {len(done)}/{len(plan['requests'])} "
                        f"{model} {item['case_id']}/{item['card_id']} "
                        f"{result['elapsed_seconds']:.2f}s",
                        flush=True,
                    )
        finally:
            if previous and safe_unload:
                runtime.unload(previous)
            write_new(
                output / f"batch-{batch:03d}.json",
                {
                    "calls": executed,
                    "completed": len(done),
                    "inventory": inventory,
                    "hardware": hardware(),
                    "telemetry": sampler.report(),
                    "models_unloaded": runtime.request("ps") if safe_unload else None,
                },
            )
    if len(done) == len(plan["requests"]) and not (output / "complete.json").exists():
        write_new(output / "complete.json", {"complete": True, "calls": len(done)})
    print(
        json.dumps({"complete": len(done) == len(plan["requests"]), "done": len(done)})
    )


def score(output):
    plan = read(output / "plan.json")
    if not (output / "complete.json").exists():
        raise KnowledgeError("score_only_after_preplanned_run_is_complete")
    cases = inputs(plan["split"])
    by_id = {c["case_id"]: c for c in cases}
    cards = {c["id"]: c for c in read(DATA / "knowledge.json")}
    # This evaluator opens reference labels only after all frozen requests complete.
    gold = read(DATA / f"{plan['split']}-gold.json")
    rows = []
    for index, item in enumerate(plan["requests"]):
        raw = read(output / f"attempt-{index:03d}.json")
        response = raw["response"] or {}
        assessment = assess(
            cards[item["card_id"]],
            project(by_id[item["case_id"]]),
            response.get("message", {}).get("content", ""),
            response.get("done_reason"),
        )
        row = {
            **{k: v for k, v in item.items() if k != "body"},
            "model": item["body"]["model"],
            **assessment,
            "elapsed_seconds": raw["elapsed_seconds"],
            "done_reason": response.get("done_reason"),
            "prompt_eval_count": response.get("prompt_eval_count"),
            "eval_count": response.get("eval_count"),
        }
        rows.append(
            score_attempt(row, gold[item["case_id"]]["expected"][item["card_id"]])
        )
    groups = {}
    for model in plan["protocol"]["models"]:
        for profile, variant in sorted(
            {(r["profile"], r["variant"]) for r in rows if r["model"] == model}
        ):
            selected = [
                r
                for r in rows
                if (r["model"], r["profile"], r["variant"]) == (model, profile, variant)
            ]
            group = summarize_attempts(selected)
            if plan["kind"] in {"confirm", "validation"}:
                group["tasks"] = {
                    policy: task_metrics(cases, selected, gold, policy)
                    for policy in ["supported_and_possible", "supported_only"]
                }
                semantic_cases = [
                    c for c in cases if gold[c["case_id"]]["semantic_case"]
                ]
                group["semantic_tasks"] = task_metrics(semantic_cases, selected, gold)
            groups[f"{model}/{profile}/{variant}"] = group
    report = {
        "kind": plan["kind"],
        "split": plan["split"],
        "evaluation_files": source_hashes(),
        "groups": groups,
        "attempts": rows,
    }
    if plan["kind"] in {"confirm", "validation"}:
        baseline_rows = []
        for case in cases:
            envelope = project(case)
            for cid in plan["selection"]["rankings"][case["case_id"]][:2]:
                item = baseline_item(cards[cid], envelope)
                assessment = assess(cards[cid], envelope, json.dumps(item))
                baseline_rows.append(
                    score_attempt(
                        {"case_id": case["case_id"], "card_id": cid, **assessment},
                        gold[case["case_id"]]["expected"][cid],
                    )
                )
        report["baseline_tasks"] = task_metrics(cases, baseline_rows, gold)
        report["baseline_semantic_tasks"] = task_metrics(
            [c for c in cases if gold[c["case_id"]]["semantic_case"]],
            baseline_rows,
            gold,
        )
    write_new(output / "scores.json", report)
    print(json.dumps({"kind": plan["kind"], "groups": groups}, ensure_ascii=False))


def retrieval(root, output, split):
    if split not in {"development", "validation"}:
        raise KnowledgeError("reserved_retrieval_not_authorized")
    protocol = read(BASE)
    runtime = Runtime()
    inventory = runtime.inventory(protocol)
    if inventory["loaded"]["models"]:
        raise KnowledgeError("runtime_not_initially_empty")
    cards = [c for c in read(DATA / "knowledge.json") if c["status"] == "current"]
    cases = inputs(split)
    model = protocol["retrieval"]["embedding_model"]
    pin = protocol["retrieval"]["embedding_digest"]
    task = protocol["retrieval"]["query_instruction"]
    text_for_case = {
        c["case_id"]: [f"Instruct: {task}\nQuery: {q}" for q in queries(project(c))]
        for c in cases
    }
    texts = list(
        dict.fromkeys(
            [document(c) for c in cards]
            + [t for qs in text_for_case.values() for t in qs]
        )
    )
    cache_root = root / "embedding-cache"
    missing, cache = [], {}
    for text in texts:
        key = digest({"model": pin, "text": text, "context": 4096})
        path = cache_root / f"{key}.json"
        if path.exists():
            cached = read(path)
            if cached["key"] != key:
                raise KnowledgeError("cache_key_mismatch")
            cache[text] = cached["vector"]
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
    write_new(
        output / "snapshot.json",
        {
            "files": source_hashes(),
            "split": split,
            "requests": payloads,
            "inventory": inventory,
            "purpose": "focused retrieval, no reader inference",
        },
    )
    sampler = Sampler(resource_limits(protocol), root)
    safe_unload = True
    with Budget(
        root, protocol, "refinement" if split == "development" else "validation"
    ) as budget:
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
                        key = digest({"model": pin, "text": text, "context": 4096})
                        write_new(
                            cache_root / f"{key}.json", {"key": key, "vector": vector}
                        )
                        cache[text] = vector
        finally:
            if payloads and safe_unload:
                runtime.unload(model)
            write_new(output / "telemetry.json", sampler.report())
    vectors = {c["id"]: cache[document(c)] for c in cards}
    rows = []
    for case in cases:
        envelope = project(case)
        qs = [cache[t] for t in text_for_case[case["case_id"]]]
        focused = focused_retrieve(cards, envelope, vectors, qs)
        initial = retrieve(cards, envelope, vectors, qs)
        rows.append(
            {
                "case_id": case["case_id"],
                "rankings": {
                    **{f"initial/{k}": v for k, v in initial.items()},
                    **{f"focused/{k}": v for k, v in focused.items()},
                },
            }
        )
    gold = read(DATA / f"{split}-gold.json")
    report = {
        "split": split,
        "new_embedding_texts": len(missing),
        "rows": rows,
        "metrics": metrics(rows, gold),
        "semantic_metrics": metrics(
            [r for r in rows if gold[r["case_id"]]["semantic_case"]], gold
        ),
        "credits": "Structured candidate filtering is code-derived; semantic "
        "ranking is measured against the same lexical control.",
    }
    write_new(output / "rankings.json", report)
    print(
        json.dumps({"split": split, "metrics": report["metrics"]}, ensure_ascii=False)
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument(
        "--kind",
        choices=["calibration", "triage", "confirm", "validation"],
        required=True,
    )
    p.add_argument("--selection", type=Path)
    p.add_argument("--variants", nargs=2)
    p.add_argument("--output-dir", type=Path, required=True)
    e = sub.add_parser("execute")
    e.add_argument("--budget-root", type=Path, required=True)
    e.add_argument("--run-dir", type=Path, required=True)
    e.add_argument("--max-calls", type=int, default=16)
    e.add_argument("--allow-inference", action="store_true")
    s = sub.add_parser("score")
    s.add_argument("--run-dir", type=Path, required=True)
    r = sub.add_parser("retrieval")
    r.add_argument("--budget-root", type=Path, required=True)
    r.add_argument("--output-dir", type=Path, required=True)
    r.add_argument("--split", choices=["development", "validation"], required=True)
    r.add_argument("--allow-inference", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        if not args.output_dir.resolve().is_relative_to(ROOT / ".test-tmp"):
            parser.error("Ignored campaign directory required")
        prepare(
            args.kind,
            args.output_dir,
            read(args.selection) if args.selection else None,
            args.variants,
        )
    elif args.command == "score":
        score(args.run_dir)
    else:
        if not args.allow_inference:
            parser.error("Explicit --allow-inference required")
        root, output = allowed_path(
            args.budget_root,
            args.run_dir if args.command == "execute" else args.output_dir,
        )
        if args.command == "execute":
            if args.max_calls < 1 or args.max_calls > 32:
                parser.error("Batch must contain 1 to 32 calls")
            execute(root, output, args.max_calls)
        else:
            retrieval(root, output, args.split)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
