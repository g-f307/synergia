"""Isolated development-case resource probe; never a full quality evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_poc_foundation import PoCFoundationError
from ai_reevaluation import (
    MeteredRuntime,
    configuration,
    corpus,
    execute_case,
    freeze,
    make_runtime,
    request_json,
    save,
)
from ai_reevaluation_telemetry import Sampler


def probe(config: dict, case_key: str, output: Path):
    if config["split"] != "development" or config["mode"] != "agent":
        raise PoCFoundationError("probe_requires_development_agent")
    cases, _ = corpus(config["kind"])
    item = next(
        (c for c in cases if c["split"] == "development" and c["key"] == case_key), None
    )
    if item is None:
        raise PoCFoundationError("probe_requires_known_development_case")
    snapshot = freeze(config)
    output.mkdir(parents=True, exist_ok=False)
    state = {
        "kind": "single_development_case_capacity_probe_not_corpus_evaluation",
        "snapshot": snapshot,
        "case": case_key,
        "attempts": [],
        "complete": False,
    }
    path = output / "probe.json"
    save(path, state)
    reference = None
    for index in range(config["warmup_attempts"] + config["repetitions"]):
        with Sampler(snapshot["protocol"]["resources"], output, reference) as sampler:
            reference = reference or sampler.before
            if sampler.failure:
                state["stop_reason"] = sampler.failure
                save(path, state)
                break
            before = request_json(config, "ps")["models"]
            if any(
                m["name"] != config["model"] or m["digest"] != config["model_digest"]
                for m in before
            ):
                raise PoCFoundationError("dedicated_runtime_required")
            record = {
                "index": index,
                "phase": "warmup" if index == 0 else "measured",
                "state": "started",
                "loaded_before": before,
            }
            state["attempts"].append(record)
            save(path, state)
            runtime = MeteredRuntime(make_runtime(config), config, sampler)
            try:
                result = execute_case(config, item, output / str(index), runtime)
                record["result"] = result
                record["failure"] = runtime.failure or result["report"].get("failure")
            except Exception:
                record["failure"] = "unexpected_attempt_failure"
            record["generation"] = runtime.calls
            if not record.get("failure") and any(c["truncated"] for c in runtime.calls):
                record["failure"] = "generation_truncated"
            record["loaded_after"] = request_json(config, "ps")["models"]
            record["state"] = "finished"
        record["resources"] = sampler.report()
        if sampler.failure:
            record["failure"] = "resource_limit"
            state["stop_reason"] = sampler.failure
        save(path, state)
        if sampler.failure:
            break
    state["complete"] = (
        len(state["attempts"]) == config["warmup_attempts"] + config["repetitions"]
    )
    save(path, state)
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-inference", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        state = probe(configuration(args.config), args.case, args.output_dir)
        print(
            json.dumps(
                {
                    "case": state["case"],
                    "complete": state["complete"],
                    "stop_reason": state.get("stop_reason"),
                }
            )
        )
        return 0 if state["complete"] else 2
    except PoCFoundationError as exc:
        parser.exit(2, f"{exc}\n")
    except (OSError, ValueError, KeyError):
        parser.exit(2, "Local probe unavailable; preserve any recorded evidence.\n")


if __name__ == "__main__":
    raise SystemExit(main())
