"""Freeze or run local synthetic comparisons. Freezing never generates a response."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_poc_foundation import PoCFoundationError
from ai_reevaluation import compare, configuration, freeze, read, run, stable_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("freeze")
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    execute = sub.add_parser("run")
    execute.add_argument("--snapshot", type=Path, required=True)
    execute.add_argument("--output-dir", type=Path, required=True)
    execute.add_argument("--resume", action="store_true")
    execute.add_argument("--allow-inference", action="store_true")
    report = sub.add_parser("compare")
    report.add_argument("--runs", type=Path, nargs="+", required=True)
    report.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            result = compare([read(path) for path in args.runs])
            with args.output.open("xb") as stream:
                stream.write(stable_json(result) + b"\n")
            print(
                json.dumps(
                    {"compared_runs": len(result["runs"]), "decision": "not_decided"}
                )
            )
            return 0
        if args.command == "freeze":
            snapshot = freeze(configuration(args.config))
            with args.output.open("xb") as stream:
                stream.write(stable_json(snapshot) + b"\n")
            print(
                json.dumps(
                    {
                        "frozen": True,
                        "cases": len(snapshot["cases"]),
                        "inference": False,
                    }
                )
            )
            return 0
        state = run(
            read(args.snapshot),
            args.output_dir,
            resume=args.resume,
            allow_inference=args.allow_inference,
        )
        print(
            json.dumps(
                {
                    key: state.get(key)
                    for key in (
                        "complete",
                        "quality_denominator",
                        "planned_quality_denominator",
                        "failed_measured_attempts",
                        "stop_reason",
                    )
                }
            )
        )
        return 0 if state["complete"] else 2
    except PoCFoundationError as exc:
        parser.exit(2, f"{exc}\n")
    except (OSError, ValueError, KeyError):
        # Do not echo arbitrary HTTP/configuration content into logs.
        parser.exit(2, "Local configuration, artifact or runtime unavailable.\n")


if __name__ == "__main__":
    raise SystemExit(main())
