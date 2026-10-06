"""Evaluate baseline and optional local agent on the same frozen cases."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from ai_operational_summary import (
    baseline,
    case_hash,
    load_case,
    run_agent,
    validate_output,
)
from ai_poc_foundation import LocalModelConfig, OllamaRuntime, PoCFoundationError

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/synthetic/ai-operational-v2/manifest.json"


def _score(output: dict, gold: dict) -> dict[str, float | int | bool]:
    predicted = {item["finding_id"] for item in output["findings"]}
    expected = {item["finding_id"] for item in gold["findings"]}
    tp = len(predicted & expected)
    precision = tp / len(predicted) if predicted else float(not expected)
    recall = tp / len(expected) if expected else float(not predicted)
    return {
        "schema_valid": True,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4)
        if precision + recall
        else 0.0,
        "status_correct": output["status"] == gold["status"],
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
                try:
                    output = (
                        baseline(case)
                        if mode == "baseline"
                        else run_agent(case, runtime, config.model)
                    )
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
                    }
                    failure = type(exc).__name__
                records.append(
                    {
                        "case_id": case["case_id"],
                        "mode": mode,
                        "repetition": repetition + 1,
                        "input_sha256": case_hash(case),
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                        "score": score,
                        "tool_call_accuracy": 1.0 if mode == "baseline" else None,
                        "failure": failure,
                    }
                )
    summary = {}
    for mode in {item["mode"] for item in records}:
        items = [item for item in records if item["mode"] == mode]
        summary[mode] = {
            "attempts": len(items),
            "schema_valid_rate": statistics.mean(
                item["score"]["schema_valid"] for item in items
            ),
            "precision": statistics.mean(item["score"]["precision"] for item in items),
            "recall": statistics.mean(item["score"]["recall"] for item in items),
            "f1": statistics.mean(item["score"]["f1"] for item in items),
            "mean_latency_ms": statistics.mean(item["elapsed_ms"] for item in items),
            "p95_latency_ms": sorted(item["elapsed_ms"] for item in items)[
                max(0, int(len(items) * 0.95) - 1)
            ],
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
