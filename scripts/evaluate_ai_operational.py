"""Evaluate baseline and optional local agent on the same frozen cases."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path

try:
    from ai_operational_summary import (
        AgentExecution,
        baseline,
        case_hash,
        execute_agent,
        load_case,
        validate_output,
    )
    from ai_poc_foundation import LocalModelConfig, OllamaRuntime, PoCFoundationError
except ModuleNotFoundError:
    from scripts.ai_operational_summary import (
        AgentExecution,
        baseline,
        case_hash,
        execute_agent,
        load_case,
        validate_output,
    )
    from scripts.ai_poc_foundation import (
        LocalModelConfig,
        OllamaRuntime,
        PoCFoundationError,
    )

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/synthetic/ai-operational-v2/manifest.json"


def _nearest_rank(values: list[float]) -> float:
    if not values:
        raise ValueError("percentil sem observações")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * 0.95) - 1))
    return ordered[index]


def _score(output: dict, gold: dict) -> dict[str, float | int | bool]:
    predicted = {item["finding_id"]: item for item in output["findings"]}
    expected = {item["finding_id"]: item for item in gold["findings"]}
    ids = set(predicted) & set(expected)
    factual = {
        finding_id
        for finding_id in ids
        if predicted[finding_id]["severity"] == expected[finding_id]["severity"]
        and predicted[finding_id]["evidence_ids"]
        == expected[finding_id]["evidence_ids"]
        and predicted[finding_id]["statement"] == expected[finding_id]["statement"]
    }
    precision = len(factual) / len(predicted) if predicted else float(not expected)
    recall = len(factual) / len(expected) if expected else float(not predicted)
    field_checks = []
    for finding_id in ids:
        field_checks.extend(
            [
                predicted[finding_id]["severity"] == expected[finding_id]["severity"],
                predicted[finding_id]["evidence_ids"]
                == expected[finding_id]["evidence_ids"],
                predicted[finding_id]["statement"] == expected[finding_id]["statement"],
            ]
        )
    return {
        "schema_valid": True,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4)
        if precision + recall
        else 0.0,
        "status_correct": output["status"] == gold["status"],
        "identifier_precision": round(
            len(ids) / len(predicted) if predicted else float(not expected), 4
        ),
        "factual_finding_count": len(factual),
        "field_accuracy": round(statistics.mean(field_checks), 4)
        if field_checks
        else float(not expected and not predicted),
        "grounded": all(
            set(item["evidence_ids"]) for item in output["findings"]
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("baseline", "agent", "both"), default="baseline"
    )
    parser.add_argument("--repetitions", type=int, choices=range(1, 11), default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    root = ROOT / manifest["source"]
    config = (
        LocalModelConfig.from_environment() if args.mode in {"agent", "both"} else None
    )
    runtime = OllamaRuntime(config) if config else None
    records: list[dict] = []
    for entry in manifest["cases"]:
        case = load_case(root / entry["input"])
        gold = json.loads((root / entry["gold"]).read_text(encoding="utf-8"))
        modes = ("baseline", "agent") if args.mode == "both" else (args.mode,)
        for mode in modes:
            for repetition in range(1 if mode == "baseline" else args.repetitions):
                started = time.perf_counter()
                agent_run: AgentExecution | None = None
                try:
                    if mode == "baseline":
                        output = baseline(case)
                        elapsed_ms = (time.perf_counter() - started) * 1000
                        generated_tokens = 0
                        peak_memory_bytes = 0
                        tool_calls = ("baseline",)
                    else:
                        agent_run = execute_agent(case, runtime, config.model)
                        output = agent_run.output
                        elapsed_ms = agent_run.elapsed_ms
                        generated_tokens = agent_run.generated_tokens
                        peak_memory_bytes = agent_run.peak_memory_bytes
                        tool_calls = agent_run.tool_calls
                    validate_output(case, output)
                    score = _score(output, gold)
                    failure = None
                except (PoCFoundationError, KeyError, json.JSONDecodeError) as exc:
                    score = {
                        "schema_valid": False,
                        "precision": 0.0,
                        "recall": 0.0,
                        "f1": 0.0,
                        "status_correct": False,
                        "identifier_precision": 0.0,
                        "factual_finding_count": 0,
                        "field_accuracy": 0.0,
                        "grounded": False,
                    }
                    failure = type(exc).__name__
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    generated_tokens = 0
                    peak_memory_bytes = 0
                    tool_calls = ()
                records.append(
                    {
                        "case_id": case["case_id"],
                        "mode": mode,
                        "repetition": repetition + 1,
                        "input_sha256": case_hash(case),
                        "elapsed_ms": round(elapsed_ms, 3),
                        "generated_tokens": generated_tokens,
                        "tokens_per_second": round(
                            generated_tokens / (elapsed_ms / 1000), 3
                        )
                        if elapsed_ms and generated_tokens
                        else 0.0,
                        "peak_memory_bytes": peak_memory_bytes,
                        "score": score,
                        "tool_calls": list(tool_calls),
                        "tool_call_accuracy": 1.0
                        if mode == "baseline"
                        or tool_calls
                        == (
                            "get_execution",
                            "list_pending",
                            "list_classifications",
                            "list_events",
                        )
                        else None,
                        "failure": failure,
                    }
                )
    summary = {}
    for mode in {item["mode"] for item in records}:
        items = [item for item in records if item["mode"] == mode]
        by_case = {}
        for case_id in {item["case_id"] for item in items}:
            case_items = [item for item in items if item["case_id"] == case_id]
            first = json.dumps(case_items[0]["score"], sort_keys=True)
            by_case[case_id] = statistics.mean(
                json.dumps(item["score"], sort_keys=True) == first
                for item in case_items
            )
        latencies = [item["elapsed_ms"] for item in items]
        summary[mode] = {
            "attempts": len(items),
            "schema_valid_rate": statistics.mean(
                item["score"]["schema_valid"] for item in items
            ),
            "precision": statistics.mean(item["score"]["precision"] for item in items),
            "recall": statistics.mean(item["score"]["recall"] for item in items),
            "f1": statistics.mean(item["score"]["f1"] for item in items),
            "field_accuracy": statistics.mean(
                item["score"]["field_accuracy"] for item in items
            ),
            "consistency_rate": statistics.mean(by_case.values()),
            "mean_latency_ms": statistics.mean(item["elapsed_ms"] for item in items),
            "p95_latency_ms": _nearest_rank(latencies),
            "mean_tokens_per_second": statistics.mean(
                item["tokens_per_second"] for item in items
            ),
            "peak_memory_bytes": max(item["peak_memory_bytes"] for item in items),
            "tool_call_accuracy": statistics.mean(
                item["tool_call_accuracy"]
                for item in items
                if item["tool_call_accuracy"] is not None
            )
            if any(item["tool_call_accuracy"] is not None for item in items)
            else None,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "dataset_version": manifest["dataset_version"],
                "summary": summary,
                "records": records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return int(any(item["failure"] for item in records))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PoCFoundationError as exc:
        raise SystemExit(f"Erro controlado: {exc}") from exc
