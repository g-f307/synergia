"""Reproducible operational PoC evaluation; rejected attempts remain measured."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
import tracemalloc
from dataclasses import replace
from pathlib import Path

try:
    from ai_operational_summary import (
        PROMPT,
        SCHEMA,
        baseline,
        case_hash,
        collect_agent_attempt,
        interaction_schema,
        load_case,
        validate_output,
    )
    from ai_poc_foundation import LocalModelConfig, OllamaRuntime
except ModuleNotFoundError:
    from scripts.ai_operational_summary import (
        PROMPT,
        SCHEMA,
        baseline,
        case_hash,
        collect_agent_attempt,
        interaction_schema,
        load_case,
        validate_output,
    )
    from scripts.ai_poc_foundation import LocalModelConfig, OllamaRuntime

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/synthetic/ai-operational-v2/manifest.json"
OPTIONS = {
    "temperature": 0,
    "seed": 126,
    "num_ctx": 4096,
    "num_predict": 2048,
    "num_thread": 6,
}


def _nearest_rank(values):
    if not values:
        raise ValueError("percentil sem observações")
    return sorted(values)[math.ceil(len(values) * 0.95) - 1]


def _score(output, gold):
    # Exact-reference scoring is conservative, NOT semantic factual verification.
    predicted = {item["finding_id"]: item for item in output["findings"]}
    expected = {item["finding_id"]: item for item in gold["findings"]}
    ids = set(predicted) & set(expected)
    fields = ("severity", "evidence_ids", "statement")
    factual = {
        key
        for key in ids
        if all(predicted[key][field] == expected[key][field] for field in fields)
    }
    precision = len(factual) / len(predicted) if predicted else float(not expected)
    recall = len(factual) / len(expected) if expected else float(not predicted)
    checks = [
        key in predicted
        and key in expected
        and predicted[key][field] == expected[key][field]
        for key in set(expected) | set(predicted)
        for field in fields
    ]
    summary_match = output["summary"] == gold["summary"]
    steps_match = output["human_next_steps"] == gold["human_next_steps"]
    status_match = output["status"] == gold["status"]
    questions_match = output["open_questions"] == gold["open_questions"]
    return {
        "schema_valid": True,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall)
        if precision + recall
        else 0,
        "identifier_precision": len(ids) / len(predicted)
        if predicted
        else float(not expected),
        "factual_finding_count": len(factual),
        "finding_field_accuracy": statistics.mean(checks) if checks else 1.0,
        "summary_exact_match": summary_match,
        "next_steps_exact_match": steps_match,
        "status_correct": status_match,
        "questions_exact_match": questions_match,
        "field_accuracy": statistics.mean(
            checks + [summary_match, steps_match, status_match, questions_match]
        ),
        "case_exact_match": set(predicted) == set(expected) == factual
        and summary_match
        and steps_match
        and status_match
        and questions_match,
    }


def fingerprint():
    paths = [
        Path(__file__),
        ROOT / "scripts/ai_operational_summary.py",
        ROOT / "scripts/ai_poc_foundation.py",
        ROOT / "scripts/evaluate_ai_quality.py",
        PROMPT,
        SCHEMA,
        MANIFEST,
        ROOT / "docs/schemas/ai-operational-summary-input.schema.json",
        *sorted(MANIFEST.parent.glob("OP-*.json")),
    ]
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
    }


def mean_known(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def max_known(values):
    values = [v for v in values if v is not None]
    return max(values) if values else None


def score_tool_calls(case, required_tools, calls):
    """Gold is used ONLY after execution; extra, denied and missing calls count."""
    collections = {
        "list_pending": "pending_items",
        "list_events": "events",
        "list_classifications": "classifications",
    }
    expected = {
        name: {"execution"}
        if name == "get_execution"
        else {item["evidence_id"] for item in case[collections[name]]}
        for name in required_tools
    }
    covered = set()
    correct = 0
    for call in calls:
        name = call["name"]
        if (
            call["outcome"] == "succeeded"
            and name in expected
            and name not in covered
            and expected[name] <= set(call.get("evidence_ids", []))
        ):
            covered.add(name)
            correct += 1
    missing = len(expected) - len(covered)
    return {
        "correct": correct,
        "attempted": len(calls),
        "missing": missing,
        "incorrect": len(calls) - correct,
        "denied": sum(c["outcome"] != "succeeded" for c in calls),
        "accuracy": correct / (len(calls) + missing),
        "precision": correct / len(calls) if calls else 0.0,
        "recall": correct / len(expected),
    }


def summarize(records):
    summary = {}
    for mode in sorted({r["mode"] for r in records}):
        group = [r for r in records if r["mode"] == mode]
        repeated = []
        for case_id in {r["case_id"] for r in group}:
            items = [r for r in group if r["case_id"] == case_id]
            if len(items) >= 2:
                repeated.append(
                    all(r["failure"] is None and r["output_sha256"] for r in items)
                    and len({r["output_sha256"] for r in items}) == 1
                )
        metrics = {
            key: statistics.mean(r["score"][key] for r in group)
            for key in (
                "schema_valid",
                "precision",
                "recall",
                "f1",
                "field_accuracy",
                "finding_field_accuracy",
                "summary_exact_match",
                "next_steps_exact_match",
                "status_correct",
                "questions_exact_match",
                "case_exact_match",
            )
        }
        metrics["schema_valid_rate"] = metrics.pop("schema_valid")
        calls = [call for r in group for call in r["tool_calls"]]
        metrics.update(
            attempts=len(group),
            accepted_rate=statistics.mean(r["failure"] is None for r in group),
            consistency_rate=statistics.mean(repeated) if repeated else None,
            consistency_cases=len(repeated),
            mean_latency_ms=statistics.mean(r["elapsed_ms"] for r in group),
            p95_latency_ms=_nearest_rank([r["elapsed_ms"] for r in group]),
            mean_tokens_per_second=mean_known([r["tokens_per_second"] for r in group]),
            python_peak_memory_bytes=max_known(
                [r["python_peak_memory_bytes"] for r in group]
            ),
            model_process_rss_peak_bytes=max_known(
                [r["model_process_rss_peak_bytes"] for r in group]
            ),
            # Calls are selected by the model and executed by the read-only registry.
            controlled_query_success_rate=statistics.mean(
                c["outcome"] == "succeeded" for c in calls
            )
            if calls
            else None,
            controlled_query_count=len(calls),
            agent_tool_choice_accuracy=mean_known(
                [
                    r["tool_score"]["accuracy"] if r["tool_score"] else None
                    for r in group
                ]
            ),
            tool_call_precision=mean_known(
                [
                    r["tool_score"]["precision"] if r["tool_score"] else None
                    for r in group
                ]
            ),
            tool_call_recall=mean_known(
                [r["tool_score"]["recall"] if r["tool_score"] else None for r in group]
            ),
            incorrect_tool_calls=sum(
                r["tool_score"]["incorrect"] for r in group if r["tool_score"]
            ),
            missing_tool_calls=sum(
                r["tool_score"]["missing"] for r in group if r["tool_score"]
            ),
        )
        summary[mode] = metrics
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("baseline", "agent", "both"), default="baseline"
    )
    parser.add_argument("--repetitions", type=int, choices=range(1, 11), default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-metadata", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output already exists; preserve prior evidence with a new path")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    root = ROOT / manifest["source"]
    config = replace(LocalModelConfig.from_environment(), timeout_seconds=300)
    runtime = (
        OllamaRuntime(config, options=OPTIONS, output_schema=interaction_schema())
        if args.mode != "baseline"
        else None
    )
    frozen = {
        "hashes": fingerprint(),
        "model": config.model if runtime else None,
        "options": OPTIONS if runtime else {},
        "timeout_seconds": 300,
        "repetitions": args.repetitions,
    }
    if args.runtime_metadata and runtime:
        try:
            from evaluate_ai_quality import local_metadata
        except ModuleNotFoundError:
            from scripts.evaluate_ai_quality import local_metadata
        frozen["runtime"] = local_metadata(config)
    records = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for entry in manifest["cases"]:
        case = load_case(root / entry["input"])
        gold = json.loads((root / entry["gold"]).read_text(encoding="utf-8"))
        modes = ("baseline", "agent") if args.mode == "both" else (args.mode,)
        for mode in modes:
            for repetition in range(1 if mode == "baseline" else args.repetitions):
                if fingerprint() != frozen["hashes"]:
                    raise RuntimeError("evaluation inputs changed")
                if mode == "baseline":
                    started = time.perf_counter()
                    tracemalloc.start()
                    try:
                        output = baseline(case)
                        validate_output(case, output)
                        peak = tracemalloc.get_traced_memory()[1]
                    finally:
                        tracemalloc.stop()
                    attempt = {
                        "output": output,
                        "failure": None,
                        "schema_valid": True,
                        "elapsed_ms": (time.perf_counter() - started) * 1000,
                        "generated_tokens": None,
                        "python_peak_memory_bytes": peak,
                        "model_process_rss_peak_bytes": None,
                        "tool_calls": [],
                        "response_sha256": None,
                    }
                else:
                    attempt = collect_agent_attempt(case, runtime, config.model)
                output = attempt.pop("output")
                if output is not None:
                    score = _score(output, gold)
                else:
                    score = {key: 0 for key in _score(gold, gold)}
                    score["schema_valid"] = attempt["schema_valid"]
                records.append(
                    {
                        **attempt,
                        "case_id": case["case_id"],
                        "mode": mode,
                        "repetition": repetition + 1,
                        "input_sha256": case_hash(case),
                        "output_sha256": case_hash(output)
                        if output is not None
                        else None,
                        # Accepted synthetic outputs support qualitative auditing.
                        "output": output,
                        "score": score,
                        "tool_score": score_tool_calls(
                            case, entry["required_tools"], attempt["tool_calls"]
                        )
                        if mode == "agent"
                        else None,
                        "tokens_per_second": attempt["generated_tokens"]
                        / (attempt["elapsed_ms"] / 1000)
                        if attempt["generated_tokens"] is not None
                        and attempt["elapsed_ms"]
                        else None,
                    }
                )
                document = {
                    "dataset_version": manifest["dataset_version"],
                    "frozen": frozen,
                    "summary": summarize(records),
                    "records": records,
                }
                temporary = args.output.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(args.output)
                print(
                    f"{case['case_id']} {mode} r{repetition + 1}: "
                    f"{attempt['failure'] or 'accepted'}",
                    flush=True,
                )
    return int(any(r["failure"] for r in records))


if __name__ == "__main__":
    raise SystemExit(main())
