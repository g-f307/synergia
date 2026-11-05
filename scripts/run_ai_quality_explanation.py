"""Freeze and run every synthetic quality regression once per planned repetition."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

from ai_poc_foundation import LocalModelConfig, OllamaRuntime, PoCFoundationError
from ai_quality_diagnosis import build_context
from ai_quality_explanation import (
    ROOT,
    contract,
    explain,
    project,
    read,
    sha,
    validate_text,
)
from ai_reevaluation import corpus, request_json
from ai_reevaluation_telemetry import Sampler

CONFIG = ROOT / "scripts/ai_quality_explanation_config.json"
ADVERSARIAL = ROOT / "data/synthetic/ai-quality-explanation-v1/adversarial.json"


def save_new(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def cases() -> list[dict]:
    entries, _ = corpus("quality")
    result = []
    for entry in entries:
        if entry["split"] != "evaluation":
            continue
        context = build_context(
            entry["path"],
            source=entry["source"],
            case_id=entry["case_id"],
            references_available=entry["references_available"],
        )
        scenario = entry["gold"]
        result.append(
            {
                "key": entry["key"],
                "label": scenario["label"],
                "provenance": "known_regression_issue_148",
                "envelope": project(context, scenario["headers"], scenario["rows"]),
            }
        )
    for case in read(ADVERSARIAL)["cases"]:
        # Adversarial fixtures represent pure pipeline output, not raw workbooks.
        # They deliberately exercise mixed severities and missing serials.
        context = {
            "schema_version": "2.0.0",
            "case_id": case["case_id"],
            "source": case["source"],
            "file_sha256": sha(case),
            "normalized_records": [],
            "counts": {
                "rows_read": len(case["rows"]),
                "rows_valid": 0,
                "normalized_records": 0,
                "errors": sum(o["severity"] == "error" for o in case["occurrences"]),
                "warnings": sum(
                    o["severity"] == "warning" for o in case["occurrences"]
                ),
                "read_success": True,
                "layout_valid": True,
            },
            "occurrences": case["occurrences"],
        }
        result.append(
            {
                "key": case["case_id"],
                "label": case["label"],
                "provenance": "synthetic_adversarial_pipeline_fixture",
                "envelope": project(context, case["headers"], case["rows"]),
            }
        )
    return result


def freeze() -> dict:
    paths = {
        Path(__file__),
        CONFIG,
        ADVERSARIAL,
        ROOT / "scripts/render_ai_quality_explanation.py",
        ROOT / "scripts/ai_quality_explanation_demo.html",
        *ROOT.joinpath("scripts").glob("ai*.py"),
        *ROOT.joinpath("scripts/ai_poc_prompts").glob("quality-explanation-*.txt"),
        *ROOT.joinpath("backend/app").rglob("*.py"),
        *ROOT.joinpath("backend/app/ai_quality_assets").glob("*"),
        *ROOT.joinpath("docs/schemas").glob("ai-quality-*.json"),
        *ROOT.joinpath("data/synthetic/ai-quality-v3").rglob("*"),
        ROOT / "backend/app/business_rules.json",
        ROOT / "docs/ai-reevaluation-protocol.json",
        ROOT / "backend/tests/test_ai_quality_explanation.py",
    }
    files = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths)
        if p.is_file()
    }
    return {
        "schema_version": "1.0.0",
        "issue": 179,
        "scope": "known_regression_and_adversarial_not_holdout",
        "configuration": read(CONFIG),
        "files": files,
        "cases": cases(),
        "python": platform.python_version(),
        "packages": {
            p: importlib.metadata.version(p)
            for p in ("jsonschema", "openpyxl", "pydantic")
        },
    }


def runtime_status(config: dict) -> dict:
    try:
        version = request_json(config, "version")["version"]
        models = request_json(config, "tags")["models"]
        model = next((m for m in models if m["name"] == config["model"]), None)
        if (
            model is None
            or model["digest"] != config["model_digest"]
            or version != config["runtime_version"]
        ):
            return {
                "available": False,
                "rejection_code": "model_or_runtime_pin_mismatch",
            }
        return {
            "available": True,
            "model": model["name"],
            "digest": model["digest"],
            "runtime_version": version,
        }
    except (OSError, urllib.error.URLError, ValueError, KeyError):
        return {"available": False, "rejection_code": "runtime_unavailable"}


class UnavailableRuntime:
    def generate(self, prompt, *, model):
        raise PoCFoundationError("runtime_unavailable")


def metrics(attempts: list[dict], planned_cases: list[dict]) -> dict:
    from collections import Counter
    from statistics import mean

    planned = {c["key"]: c["envelope"] for c in planned_cases}
    result = {}
    for mode in ("baseline", "candidate"):
        selected = [a for a in attempts if a["mode"] == mode]
        groups = [g for a in selected for g in a["groups"]]
        latencies = sorted(sum(g["elapsed_ms"] for g in a["groups"]) for a in selected)
        expected_refs = covered_refs = duplicates = unsupported = 0
        for attempt in selected:
            expected = {
                o["evidence_id"]
                for g in planned[attempt["case"]]["groups"]
                for o in g["occurrences"]
            }
            observed = {
                o["evidence_id"]
                for item in attempt["groups"]
                for o in item["group"]["occurrences"]
            }
            expected_refs += len(expected)
            covered_refs += len(expected & observed)
            codes = [item["group"]["code"] for item in attempt["groups"]]
            duplicates += len(codes) - len(set(codes))
            for item in attempt["groups"]:
                try:
                    validate_text(item["group"], item["text"])
                except PoCFoundationError:
                    unsupported += 1
        result[mode] = {
            "case_attempts": len(selected),
            "group_attempts": len(groups),
            "accepted_model_groups": sum(g["origin"] == "model" for g in groups),
            "deterministic_groups": sum(g["origin"] == "deterministic" for g in groups),
            "fallback_groups": sum(g["origin"] == "deterministic" for g in groups)
            if mode == "candidate"
            else 0,
            "rejected_groups": sum(g["rejection_code"] is not None for g in groups),
            "rejection_codes": dict(
                Counter(g["rejection_code"] for g in groups if g["rejection_code"])
            ),
            "accepted_unsupported_claim_groups": unsupported,
            "claim_measurement": "closed_sentence_policy_not_independent_human_review",
            "expected_occurrences": expected_refs,
            "covered_occurrences": covered_refs,
            "occurrence_coverage": covered_refs / expected_refs
            if expected_refs
            else 1.0,
            "duplicate_diagnoses": duplicates,
            "latency_mean_ms": round(mean(latencies), 3) if latencies else None,
            "latency_p95_ms": latencies[
                min(len(latencies) - 1, int(len(latencies) * 0.95))
            ]
            if latencies
            else None,
            "python_peak_memory_bytes": max(
                (g["python_peak_memory_bytes"] for g in groups), default=0
            ),
        }
    return result


def run(snapshot: dict, output: Path, *, runtime_factory=None, sampler_factory=Sampler):
    if snapshot != freeze():
        raise PoCFoundationError("frozen_inputs_changed")
    output.mkdir(parents=True, exist_ok=False)
    config = snapshot["configuration"]
    status = runtime_status(config)
    runtime = (
        runtime_factory(config)
        if runtime_factory
        else (
            OllamaRuntime(
                LocalModelConfig(
                    config["model"],
                    config["endpoint"],
                    config["request_timeout_seconds"],
                ),
                options=config["options"],
                output_schema=contract("output"),
                think=config["think"],
                keep_alive=config["keep_alive_seconds"],
            )
            if status["available"]
            else UnavailableRuntime()
        )
    )
    report = {
        "schema_version": "1.0.0",
        "issue": 179,
        "started_at": datetime.now(UTC).isoformat(),
        "snapshot_sha256": sha(snapshot),
        "runtime": status,
        "complete": False,
        "attempts": [],
    }
    save_new(output / "manifest.json", snapshot)
    limits = read(ROOT / "docs/ai-reevaluation-protocol.json")["resources"]
    with sampler_factory(limits, output) as sampler:
        for repetition in range(config["repetitions"]):
            for case in snapshot["cases"]:
                for mode in ("baseline", "candidate"):
                    attempt = {
                        "case": case["key"],
                        "repetition": repetition,
                        "mode": mode,
                        "groups": [],
                        "empty_case": not case["envelope"]["groups"],
                    }
                    for group in case["envelope"]["groups"]:
                        # Resource failure switches remaining requests to fallback;
                        # every planned case remains in the denominator.
                        current = (
                            runtime if not sampler.failure else UnavailableRuntime()
                        )
                        item = explain(
                            group,
                            current if mode == "candidate" else None,
                            model=config["model"],
                        )
                        attempt["groups"].append(item)
                    report["attempts"].append(attempt)
                    save_new(
                        output / f"attempt-{len(report['attempts']):04d}.json", attempt
                    )
                    print(
                        f"{len(report['attempts'])}: {mode} {case['key']}", flush=True
                    )
    report["resources"] = sampler.report()
    report["complete"] = True
    report["metrics"] = metrics(report["attempts"], snapshot["cases"])
    save_new(output / "results.json", report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--freeze", type=Path)
    group.add_argument("--execute", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.freeze:
            save_new(args.freeze, freeze())
        else:
            if not args.output_dir:
                parser.error("--output-dir obrigatório para executar")
            run(read(args.execute), args.output_dir)
    except (PoCFoundationError, FileExistsError) as exc:
        print(f"Execução recusada: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
