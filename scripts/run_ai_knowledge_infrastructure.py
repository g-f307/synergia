"""Issue #183 block 2 only: development retrieval or six infrastructure probes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

from ai_knowledge import (
    DATA,
    ROOT,
    KnowledgeError,
    digest,
    factual_slice,
    inputs,
    messages,
    project,
    read,
    response_schema,
    validate_corpus,
    write_new,
)
from ai_knowledge_retrieval import document, metrics, queries, retrieve
from ai_knowledge_runtime import Budget, Runtime
from ai_reevaluation_telemetry import Sampler, hardware
from jsonschema import Draft202012Validator

PROTOCOL = ROOT / "docs/ai-knowledge-poc-protocol.json"


def snapshot(output: Path, protocol: dict, inventory: dict, requests: list):
    files = [
        Path(__file__),
        ROOT / "scripts/ai_knowledge.py",
        ROOT / "scripts/ai_knowledge_retrieval.py",
        ROOT / "scripts/ai_knowledge_runtime.py",
        ROOT / "scripts/ai_reevaluation_telemetry.py",
        PROTOCOL,
        DATA / "manifest.json",
    ]
    write_new(
        output / "snapshot.json",
        {
            "protocol": protocol,
            "inventory": inventory,
            "hardware": hardware(),
            "files": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in files
            },
            "requests_sha256": digest(requests),
            "scope": "development only; no validation/reserved inference or tuning",
        },
    )
    write_new(output / "requests.json", requests)


def check_resources(sampler, started, protocol):
    if sampler.failure:
        raise KnowledgeError(f"resource_stop:{sampler.failure}")
    if time.monotonic() - started > protocol["budget"]["max_batch_seconds"]:
        raise KnowledgeError("batch_wall_limit")


def retrieval(runtime, budget, sampler, output, protocol, inventory):
    cards = read(DATA / "knowledge.json")
    active = [c for c in cards if c["status"] == "current"]
    cases = inputs("development")
    envelopes = {c["case_id"]: project(c) for c in cases}
    embed_model = protocol["retrieval"]["embedding_model"]
    model_digest = inventory["models"][embed_model]["digest"]
    task = protocol["retrieval"]["query_instruction"]
    doc_texts = [document(c) for c in active]
    views = {cid: queries(env) for cid, env in envelopes.items()}
    query_texts = {
        cid: [f"Instruct: {task}\nQuery: {q}" for q in qs] for cid, qs in views.items()
    }
    unique = list(
        dict.fromkeys(doc_texts + [t for qs in query_texts.values() for t in qs])
    )
    cache_root = budget.root / "embedding-cache"
    cache_root.mkdir(exist_ok=True)
    cache = {}
    missing = []
    for text in unique:
        key = digest({"model": model_digest, "text": text, "context": 4096})
        path = cache_root / f"{key}.json"
        if path.exists():
            cached = read(path)
            if cached["key"] != key:
                raise KnowledgeError("embedding_cache_key_mismatch")
            cache[text] = cached["vector"]
        else:
            missing.append(text)
    requests = [
        {
            "model": embed_model,
            "input": missing[i : i + 8],
            "truncate": False,
            "keep_alive": 600,
            "options": {"num_ctx": 4096},
        }
        for i in range(0, len(missing), 8)
    ]
    snapshot(output, protocol, inventory, requests)
    started = time.monotonic()
    for index, request in enumerate(requests):
        check_resources(sampler, started, protocol)
        result = budget.call(
            runtime,
            "embed",
            request,
            output / f"embed-{index:02d}.json",
            45,
            len(request["input"]),
        )
        vectors = result["response"].get("embeddings", [])
        if len(vectors) != len(request["input"]):
            raise KnowledgeError("wrong_embedding_count")
        for text, vector in zip(request["input"], vectors, strict=True):
            if not vector or any(not math.isfinite(x) for x in vector):
                raise KnowledgeError("invalid_embedding_vector")
            key = digest({"model": model_digest, "text": text, "context": 4096})
            write_new(cache_root / f"{key}.json", {"key": key, "vector": vector})
            cache[text] = vector
        print(
            f"Embeddings: lote {index + 1}/{len(requests)}, {len(vectors)} textos",
            flush=True,
        )
    runtime.unload(embed_model)
    vectors = {c["id"]: cache[text] for c, text in zip(active, doc_texts, strict=True)}
    rows = []
    for case in cases:
        cid = case["case_id"]
        before = time.perf_counter()
        ranking = retrieve(
            cards, envelopes[cid], vectors, [cache[t] for t in query_texts[cid]]
        )
        rows.append(
            {
                "case_id": cid,
                "queries": views[cid],
                "rankings": ranking,
                "ranking_seconds": time.perf_counter() - before,
            }
        )
    write_new(output / "rankings.json", rows)
    # Gold becomes visible only to the evaluator, after every ranking is fixed.
    gold = read(DATA / "development-gold.json")
    report = {
        "split": "development",
        "calibration": False,
        "cases": len(cases),
        "unique_embedding_texts": len(unique),
        "new_embedding_texts": len(missing),
        "metrics": metrics(rows, gold),
        "semantic_metrics": metrics(
            [r for r in rows if gold[r["case_id"]]["semantic_case"]], gold
        ),
        "limitations": [
            "Development challenge set, not final results or user benefit.",
            "No applicability threshold calibrated; "
            "ranked candidates are not recommendations.",
            "A/B variants clustered; no independent-sample claim.",
            "Some cases have more than two relevant cards; "
            "report architectural ceiling.",
        ],
    }
    write_new(output / "summary.json", report)
    return report


def probes(runtime, budget, sampler, output, protocol, inventory):
    if protocol["authorization"]["current_blocks"] != [1, 2]:
        raise KnowledgeError("review_phase_authorization_before_probes")
    cards = {
        c["id"]: c for c in read(DATA / "knowledge.json") if c["status"] == "current"
    }
    cases = {c["case_id"]: c for c in inputs("development")}
    config = protocol["runtime"]
    requests = []
    for model in protocol["models"]:
        for cid, card_id in zip(
            config["probe_cases"], config["probe_cards"], strict=True
        ):
            envelope = project(cases[cid])
            schema = response_schema(factual_slice(cards[card_id], envelope))
            profile = protocol["profiles"]["historical"]
            options = {k: v for k, v in profile.items() if k != "think"}
            options.update(num_ctx=4096, num_predict=512, num_thread=6, seed=125)
            requests.append(
                {
                    "case_id": cid,
                    "card_id": card_id,
                    "body": {
                        "model": model,
                        "messages": messages(cards[card_id], envelope),
                        "stream": False,
                        "think": False,
                        "format": schema,
                        "keep_alive": 600,
                        "options": options,
                    },
                }
            )
    snapshot(output, protocol, inventory, requests)
    rows = []
    started = time.monotonic()
    previous = None
    for index, item in enumerate(requests):
        check_resources(sampler, started, protocol)
        model = item["body"]["model"]
        if previous is not None and previous != model:
            runtime.unload(previous)
        cold = previous != model
        result = budget.call(
            runtime, "chat", item["body"], output / f"probe-{index:02d}.json", 45
        )
        response = result["response"]
        raw = response.get("message", {}).get("content", "")
        try:
            candidate = json.loads(raw)
        except (ValueError, TypeError):
            candidate = None
        valid = Draft202012Validator(item["body"]["format"]).is_valid(candidate)
        row = {
            "case_id": item["case_id"],
            "card_id": item["card_id"],
            "model": model,
            "cold_first_call": cold,
            "schema_valid": valid,
            "parsed": candidate,
            "done_reason": response.get("done_reason"),
            "prompt_eval_count": response.get("prompt_eval_count"),
            "eval_count": response.get("eval_count"),
            "load_seconds": response.get("load_duration", 0) / 1e9,
            "elapsed_seconds": result["elapsed_seconds"],
            "loaded_model": runtime.request("ps"),
        }
        if row["done_reason"] == "length":
            row["schema_valid"] = False
        write_new(output / f"probe-{index:02d}-evaluation.json", row)
        rows.append(row)
        previous = model
        print(
            f"Probe {index + 1}/{len(requests)} {model}: "
            f"{row['elapsed_seconds']:.2f}s, schema={row['schema_valid']}",
            flush=True,
        )
    if previous:
        runtime.unload(previous)
    # Descriptive oracle checks only; never a quality/generalization estimate.
    gold = read(DATA / "development-gold.json")
    for row in rows:
        expected = gold[row["case_id"]]["expected"][row["card_id"]]
        row["expected_status"] = expected
        row["status_matches_reference"] = (
            row["schema_valid"] and row["parsed"]["status"] == expected
        )
    report = {
        "attempts": rows,
        "purpose": "Infrastructure probes with manually supplied "
        "development cards; not evaluation.",
        "models_unloaded": runtime.request("ps"),
    }
    write_new(output / "summary.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["retrieval", "probe"])
    parser.add_argument("--budget-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-inference", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_inference:
        parser.error("Explicit --allow-inference is required")
    root, output = args.budget_root.resolve(), args.output_dir.resolve()
    if not root.is_relative_to(ROOT / ".test-tmp") or not output.is_relative_to(root):
        parser.error("Runs/cache must remain inside the ignored campaign directory")
    if output == root:
        parser.error("Use a new subdirectory for every run")
    protocol = read(PROTOCOL)
    validate_corpus()
    runtime = Runtime()
    inventory = runtime.inventory(protocol)
    if inventory["loaded"]["models"]:
        raise KnowledgeError("runtime_not_initially_empty")
    output.mkdir(parents=True, exist_ok=False)
    limits = {
        "minimum_available_ram_bytes": 2 * 1024**3,
        "max_swap_growth_bytes": protocol["budget"]["swap_growth_stop_bytes"],
        "reserved_gpu_headroom_bytes": 128 * 1024**2,
        "minimum_available_disk_bytes_before_run": protocol["budget"][
            "minimum_disk_free_bytes"
        ],
        "rss_sampling_interval_seconds": 0.5,
    }
    sampler = Sampler(limits, root)
    with Budget(root, protocol) as budget:
        try:
            with sampler:
                operation = retrieval if args.command == "retrieval" else probes
                operation(runtime, budget, sampler, output, protocol, inventory)
        finally:
            write_new(output / "telemetry.json", sampler.report())
    print(json.dumps({"complete": True, "output": str(output.relative_to(ROOT))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
