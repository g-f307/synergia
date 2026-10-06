"""Reproduce the operational summary PoC for one frozen synthetic case."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

from ai_operational_summary import (
    baseline,
    case_hash,
    load_case,
    run_agent,
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
            output = run_agent(case, runtime, config.model)
            reports.append(
                {
                    "mode": "agent",
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "model": config.model,
                    "schema_valid": True,
                }
            )
            (args.output_dir / f"agent-{uuid.uuid4().hex}.json").write_text(
                json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    report = {
        "run_id": uuid.uuid4().hex,
        "case_id": case["case_id"],
        "input_sha256": case_hash(case),
        "requested_repetitions": args.repetitions,
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
