"""Run a synthetic operational case, preserving failed-attempt telemetry."""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import replace
from pathlib import Path

from ai_operational_summary import (
    PROMPT,
    SCHEMA,
    baseline,
    case_hash,
    collect_agent_attempt,
    load_case,
    validate_output,
)
from ai_poc_foundation import LocalModelConfig, OllamaRuntime
from evaluate_ai_operational import MANIFEST, OPTIONS, ROOT, fingerprint


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=("baseline", "agent", "both"), default="baseline"
    )
    parser.add_argument("--repetitions", type=int, choices=range(1, 11), default=3)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(MANIFEST.read_text())
    listed = {
        (ROOT / manifest["source"] / c["input"]).resolve() for c in manifest["cases"]
    }
    if args.input.resolve() not in listed:
        parser.error("input must belong to the synthetic manifest")
    case = load_case(args.input)
    directory = args.output_dir / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    reports = []
    frozen = fingerprint()
    config = replace(LocalModelConfig.from_environment(), timeout_seconds=300)
    runtime = OllamaRuntime(
        config, options=OPTIONS, output_schema=json.loads(SCHEMA.read_text())
    )
    modes = ("baseline", "agent") if args.mode == "both" else (args.mode,)
    for mode in modes:
        for repetition in range(args.repetitions if mode == "agent" else 1):
            if fingerprint() != frozen:
                raise RuntimeError("inputs changed")
            if mode == "agent":
                attempt = collect_agent_attempt(case, runtime, config.model)
            else:
                output = baseline(case)
                validate_output(case, output)
                attempt = {"output": output, "failure": None, "schema_valid": True}
            output = attempt.pop("output")
            if output is not None:
                (directory / f"{mode}-{repetition + 1}.json").write_text(
                    json.dumps(output, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            reports.append({**attempt, "mode": mode, "repetition": repetition + 1})
            (directory / "run-report.json").write_text(
                json.dumps(
                    {
                        "case_id": case["case_id"],
                        "input_sha256": case_hash(case),
                        "hashes": frozen,
                        "model": config.model,
                        "options": OPTIONS,
                        "prompt": PROMPT.name,
                        "reports": reports,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
    return int(any(r["failure"] for r in reports))


if __name__ == "__main__":
    raise SystemExit(main())
