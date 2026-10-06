"""Run advisory diagnosis against a frozen synthetic case, without loading gold."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from ai_poc_foundation import LocalModelConfig, OllamaRuntime, PoCFoundationError
from ai_quality_diagnosis import build_context, run_attempt, schema
from build_ai_quality_dataset import DATASET, verify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--mode", choices=["baseline", "agent", "both"], default="baseline"
    )
    parser.add_argument("--repetitions", type=int, choices=range(1, 21), default=1)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--synthetic-only", action="store_true", required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= 900:
        parser.error("timeout deve estar entre 1 e 900 segundos")
    # Only manifest-listed bytes may reach the model. No raw input path in artifacts.
    manifest = json.loads((DATASET / "manifest.json").read_text())
    listed = {(DATASET / item["file"]).resolve(): item for item in manifest["files"]}
    entry = listed.get(args.input.resolve())
    if verify() or entry is None or entry["case_id"] != args.case_id:
        parser.error("input deve corresponder ao manifesto sintético congelado")
    try:
        context = build_context(
            args.input,
            source=entry["source"],
            case_id=args.case_id,
            references_available=entry["references_available"],
        )
        reports = []
        if args.mode in {"baseline", "both"}:
            reports.append(
                run_attempt(
                    context, runtime=None, model="rules-v2", output_dir=args.output_dir
                )
            )
        if args.mode in {"agent", "both"}:
            config = replace(
                LocalModelConfig.from_environment(),
                timeout_seconds=args.timeout_seconds,
            )
            parameters = {
                "temperature": 0,
                "seed": 125,
                "num_predict": 2048,
                "num_ctx": 4096,
            }
            runtime = OllamaRuntime(
                config, options=parameters, output_schema=schema("output")
            )
            for _ in range(args.repetitions):
                reports.append(
                    run_attempt(
                        context,
                        runtime=runtime,
                        model=config.model,
                        parameters={
                            **parameters,
                            "request_timeout_seconds": args.timeout_seconds,
                        },
                        output_dir=args.output_dir,
                    )
                )
        print(json.dumps(reports, ensure_ascii=False))
        return int(any(item["outcome"] != "succeeded" for item in reports))
    except PoCFoundationError:
        parser.error("falha ao preparar contexto sintético; confira fonte e arquivo")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
