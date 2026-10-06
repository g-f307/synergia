"""Reproduce the operational summary PoC for one frozen synthetic case."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import uuid
from pathlib import Path

from ai_operational_summary import (
    baseline,
    case_hash,
    execute_agent,
    load_case,
    validate_output,
)
from ai_poc_foundation import LocalModelConfig, OllamaRuntime, PoCFoundationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=("baseline", "agent", "both"), default="baseline"
    )
    parser.add_argument("--repetitions", type=int, choices=range(1, 11), default=3)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    case = load_case(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    if args.mode in {"baseline", "both"}:
        started = time.perf_counter()
        output = baseline(case)
        validate_output(case, output)
        reports.append(
            {
                "mode": "baseline",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "model": "rules-v2",
            }
        )
        (args.output_dir / f"baseline-{uuid.uuid4().hex}.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if args.mode in {"agent", "both"}:
        config = LocalModelConfig.from_environment()
        runtime = OllamaRuntime(config)
        for _ in range(args.repetitions):
            started = time.perf_counter()
            execution = execute_agent(case, runtime, config.model)
            output = execution.output
            reports.append(
                {
                    "mode": "agent",
                    "elapsed_ms": execution.elapsed_ms,
                    "generated_tokens": execution.generated_tokens,
                    "tokens_per_second": round(
                        execution.generated_tokens / (execution.elapsed_ms / 1000), 3
                    )
                    if execution.elapsed_ms and execution.generated_tokens
                    else 0.0,
                    "peak_memory_bytes": execution.peak_memory_bytes,
                    "model": config.model,
                    "schema_valid": True,
                    "tool_calls": list(execution.tool_calls),
                }
            )
            (args.output_dir / f"agent-{uuid.uuid4().hex}.json").write_text(
                json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    latencies = sorted(item["elapsed_ms"] for item in reports)
    p95_index = min(len(latencies) - 1, max(0, math.ceil(len(latencies) * 0.95) - 1))
    report = {
        "run_id": uuid.uuid4().hex,
        "case_id": case["case_id"],
        "input_sha256": case_hash(case),
        "requested_repetitions": args.repetitions,
        "summary": {
            "mean_latency_ms": round(statistics.mean(latencies), 3),
            "p95_latency_ms": round(latencies[p95_index], 3),
            "mean_tokens_per_second": round(
                statistics.mean(item.get("tokens_per_second", 0.0) for item in reports),
                3,
            ),
            "peak_memory_bytes": max(
                item.get("peak_memory_bytes", 0) for item in reports
            ),
        },
        "reports": reports,
    }
    (args.output_dir / "run-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PoCFoundationError as exc:
        raise SystemExit(f"Erro controlado: {exc}") from exc
