"""Reproducible command-line runner for the local AI PoC foundation."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

try:
    from ai_poc_foundation import (
        DatasetSpec,
        ExecutionMetrics,
        LocalModelConfig,
        OllamaRuntime,
        PoCFoundationError,
        execute_case,
        ingest,
        normalized_input_hash,
        run_baseline,
        summarize_metrics,
        validate_output,
    )
except ModuleNotFoundError:
    from scripts.ai_poc_foundation import (
        DatasetSpec,
        ExecutionMetrics,
        LocalModelConfig,
        OllamaRuntime,
        PoCFoundationError,
        execute_case,
        ingest,
        normalized_input_hash,
        run_baseline,
        summarize_metrics,
        validate_output,
    )

SPEC = DatasetSpec(
    required_columns=("record_id", "status", "amount"),
    column_types={"record_id": "string", "status": "string", "amount": "number"},
    domains={"status": frozenset({"valid", "warning", "error"})},
)


def _write_baseline(
    kind: str, records: list[dict], schema: Path, output_dir: Path
) -> ExecutionMetrics:
    started = time.perf_counter()
    output = run_baseline(kind, records)
    validate_output(output, schema)
    elapsed_ms = (time.perf_counter() - started) * 1000
    execution_id = uuid.uuid4().hex
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"baseline-{execution_id}.json").write_text(
        json.dumps(
            {"execution_id": execution_id, "output": output},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    metrics = ExecutionMetrics(
        execution_id,
        "deterministic-baseline",
        normalized_input_hash(records),
        round(elapsed_ms, 3),
        0,
        0,
        0,
    )
    (output_dir / f"baseline-{execution_id}.metrics.json").write_text(
        json.dumps(metrics.__dict__, indent=2) + "\n", encoding="utf-8"
    )
    return metrics


def _metric_group(metrics: list[ExecutionMetrics]) -> dict:
    return {
        "executions": [item.__dict__ for item in metrics],
        "summary": summarize_metrics(metrics) if metrics else None,
    }


def build_report(
    *,
    kind: str,
    input_name: str,
    requested_repetitions: int,
    baseline_metrics: list[ExecutionMetrics],
    agent_metrics: list[ExecutionMetrics],
) -> dict:
    effective_model = (
        agent_metrics[0].model
        if agent_metrics
        else "deterministic-baseline"
        if baseline_metrics
        else None
    )
    return {
        "run_id": uuid.uuid4().hex,
        "kind": kind,
        "input": input_name,
        "requested_repetitions": requested_repetitions,
        "repetitions": len(agent_metrics) if agent_metrics else len(baseline_metrics),
        "model": effective_model,
        "baseline": _metric_group(baseline_metrics),
        "agent": _metric_group(agent_metrics),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("quality", "operational"), default="quality")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("baseline", "agent", "both"), default="both")
    args = parser.parse_args()
    if args.repetitions < 1 or args.repetitions > 20:
        raise SystemExit("--repetitions deve estar entre 1 e 20")

    records = ingest(args.input, SPEC)
    baseline_metrics: list[ExecutionMetrics] = []
    agent_metrics: list[ExecutionMetrics] = []
    if args.mode in {"baseline", "both"}:
        baseline_metrics.append(
            _write_baseline(args.kind, records, args.schema, args.output_dir)
        )
    if args.mode in {"agent", "both"}:
        config = LocalModelConfig.from_environment()
        if args.model:
            config = LocalModelConfig(
                args.model, config.endpoint, config.timeout_seconds
            )
        runtime = OllamaRuntime(config)
        for _ in range(args.repetitions):
            _, item = execute_case(
                records,
                args.prompt,
                args.schema,
                runtime,
                config,
                output_dir=args.output_dir,
            )
            agent_metrics.append(item)
    report = build_report(
        kind=args.kind,
        input_name=args.input.name,
        requested_repetitions=args.repetitions,
        baseline_metrics=baseline_metrics,
        agent_metrics=agent_metrics,
    )
    (args.output_dir / "run-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PoCFoundationError as exc:
        raise SystemExit(f"Erro controlado: {exc}") from exc
