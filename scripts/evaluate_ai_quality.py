"""Evaluate frozen synthetic files locally. Failures remain in all denominators."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import threading
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from ai_poc_foundation import LocalModelConfig, OllamaRuntime, _NoRedirectHandler
from ai_quality_diagnosis import (
    PROMPT,
    ROOT,
    build_context,
    digest,
    run_attempt,
    schema,
)
from build_ai_quality_dataset import DATASET, verify

OPTIONS = {
    "temperature": 0,
    "seed": 125,
    "num_predict": 2048,
    "num_ctx": 4096,
    "num_thread": 6,
}


def save(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def fingerprint() -> dict:
    paths = [
        PROMPT,
        Path(__file__),
        ROOT / "scripts/ai_quality_diagnosis.py",
        ROOT / "scripts/ai_poc_foundation.py",
        ROOT / "backend/app/validation.py",
        ROOT / "backend/app/normalization.py",
        ROOT / "backend/app/model/normalization_rules.json",
        DATASET / "manifest.json",
        DATASET / "scenarios.json",
        ROOT / "docs/schemas/ai-quality-diagnosis-v2-input.schema.json",
        ROOT / "docs/schemas/ai-quality-diagnosis-v2-output.schema.json",
    ]
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
    }


def local_metadata(config: LocalModelConfig) -> dict:
    parts = urlsplit(config.endpoint)
    opener = urllib.request.build_opener(_NoRedirectHandler())

    def get(route):
        with opener.open(
            f"{parts.scheme}://{parts.netloc}/api/{route}", timeout=10
        ) as response:
            return json.load(response)

    model = next(item for item in get("tags")["models"] if item["name"] == config.model)
    return {
        "runtime_version": get("version")["version"],
        "model": model["name"],
        "digest": model["digest"],
        "details": model["details"],
    }


class MemorySampler:
    """Observed peak of summed Linux server/runner RSS, sampled every 0.5s.

    Requires dedicated Ollama. Shared pages may be counted twice; not VRAM.
    Python allocation peak is recorded independently by run_attempt.
    """

    def __init__(self):
        self.peak = None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        while not self.stop_event.is_set():
            try:
                result = subprocess.run(
                    ["ps", "-C", "ollama,llama-server", "-o", "rss="],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                values = [int(value) * 1024 for value in result.stdout.split()]
                if values:
                    self.peak = max(self.peak or 0, sum(values))
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
            self.stop_event.wait(0.5)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop_event.set()
        self.thread.join(timeout=3)


def score(context: dict, gold: dict, report: dict) -> dict:
    projection = report.get("diagnostic_projection") or {}
    diagnoses = projection.get("diagnoses", [])
    expected = {(code, category) for code, category, _, _ in gold["expected"]}
    predicted = {(item["occurrence_code"], item["category"]) for item in diagnoses}
    evidence = {item["evidence_id"]: item for item in context["occurrences"]}
    references = [
        (item["occurrence_code"], ref)
        for item in diagnoses
        for ref in item["evidence_ids"]
    ]
    correct = {
        (code, ref)
        for code, ref in references
        if ref in evidence and evidence[ref]["code"] == code
    }
    categories = {code: category for code, category in expected}
    confusion = [
        [categories.get(code, "__spurious__"), category] for code, category in predicted
    ]
    confusion += [
        [category, "__missing__"]
        for code, category in expected
        if not any(item[0] == code for item in predicted)
    ]
    return {
        "tp": len(expected & predicted),
        "fp": len(predicted - expected),
        "fn": len(expected - predicted),
        "confusion": confusion,
        "classification_exact": bool(report["schema_valid"] and expected == predicted),
        "case_correct": bool(
            report["outcome"] == "succeeded"
            and expected == predicted
            and projection.get("status") == gold["status"]
        ),
        "abstention_correct": projection.get("status") == gold["status"],
        "reference_count": len(references),
        "correct_references": sum(
            ref in evidence and evidence[ref]["code"] == code
            for code, ref in references
        ),
        "covered_evidence": len(correct),
        "expected_evidence": len(evidence),
        "semantic_signature": digest(projection) if projection else None,
    }


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def summarize(records: list[dict]) -> dict:
    summary = {}
    for mode in ("baseline", "agent"):
        group = [item for item in records if item["report"]["mode"] == mode]
        if not group:
            continue
        n = len(group)
        tp, fp, fn = (
            sum(item["score"][key] for item in group) for key in ("tp", "fp", "fn")
        )
        times = sorted(item["report"]["elapsed_ms"] for item in group)
        memory = [
            item["model_process_rss_peak_bytes"]
            for item in group
            if item["model_process_rss_peak_bytes"] is not None
        ]
        by_file = defaultdict(list)
        confusion = Counter()
        for item in group:
            by_file[item["file"]].append(item)
            confusion.update(tuple(pair) for pair in item["score"]["confusion"])
        repeated = [items for items in by_file.values() if len(items) >= 3]
        consistent = sum(
            all(item["report"]["outcome"] == "succeeded" for item in items)
            and len({item["score"]["semantic_signature"] for item in items}) == 1
            for items in repeated
        )
        summary[mode] = {
            "attempts": n,
            "schema_valid_rate": sum(item["report"]["schema_valid"] for item in group)
            / n,
            "accepted_rate": sum(
                item["report"]["outcome"] == "succeeded" for item in group
            )
            / n,
            "classification_exact_rate": sum(
                item["score"]["classification_exact"] for item in group
            )
            / n,
            "case_correct_rate": sum(item["score"]["case_correct"] for item in group)
            / n,
            "precision_micro": ratio(tp, tp + fp),
            "recall_micro": ratio(tp, tp + fn),
            "f1_micro": ratio(2 * tp, 2 * tp + fp + fn),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "abstention_accuracy": sum(
                item["score"]["abstention_correct"] for item in group
            )
            / n,
            "structured_reference_precision": ratio(
                sum(item["score"]["correct_references"] for item in group),
                sum(item["score"]["reference_count"] for item in group),
            ),
            "structured_evidence_recall": ratio(
                sum(item["score"]["covered_evidence"] for item in group),
                sum(item["score"]["expected_evidence"] for item in group),
            ),
            "valid_semantic_consistency": ratio(consistent, len(repeated)),
            "repeated_files": len(repeated),
            "mean_latency_ms": statistics.mean(times),
            "p95_latency_ms": times[math.ceil(0.95 * len(times)) - 1],
            "sampled_model_process_rss_peak_bytes": max(memory) if memory else None,
            "python_peak_memory_bytes": max(
                item["report"]["python_peak_memory_bytes"] for item in group
            ),
            "failures": dict(
                Counter(
                    item["report"]["failure"]
                    for item in group
                    if item["report"]["failure"]
                )
            ),
            "confusion_matrix": [
                {"expected": a, "predicted": b, "count": count}
                for (a, b), count in sorted(confusion.items())
            ],
        }
    unique = {item["file"]: item["counts"] for item in records}
    values = list(unique.values())
    summary["ingestion"] = {
        "files": len(values),
        "read_success_rate": ratio(
            sum(item["read_success"] for item in values), len(values)
        ),
        "layout_valid_rate": ratio(
            sum(item["layout_valid"] for item in values), len(values)
        ),
        "valid_row_rate": ratio(
            sum(item["rows_valid"] for item in values),
            sum(item["rows_read"] for item in values),
        ),
    }
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["development", "evaluation"], required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.repetitions <= 10:
        parser.error("repetitions must be 1..10")
    if args.split == "evaluation" and args.repetitions < 3:
        parser.error("evaluation requires at least three repetitions")
    if verify():
        parser.error("dataset integrity failure")
    gold = json.loads((DATASET / "scenarios.json").read_text(encoding="utf-8"))
    if gold["gold_review"]["status"] != "approved_by_user":
        parser.error("human gold review required")
    config = replace(LocalModelConfig.from_environment(), timeout_seconds=300)
    frozen = {
        "fingerprint": fingerprint(),
        "runtime": local_metadata(config),
        "options": OPTIONS,
        "timeout_seconds": 300,
        "split": args.split,
        "repetitions": args.repetitions,
        "python": platform.python_version(),
        "machine": platform.machine(),
        "platform": platform.system(),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frozen_path = args.output_dir / "frozen.json"
    records_path = args.output_dir / "records.json"
    if frozen_path.exists():
        if not args.resume or json.loads(frozen_path.read_text()) != frozen:
            parser.error("run differs or --resume missing; use a new directory")
    else:
        if any(args.output_dir.iterdir()):
            parser.error("new run requires empty directory")
        save(frozen_path, frozen)
    records = (
        json.loads(records_path.read_text())["records"] if records_path.exists() else []
    )
    completed = {
        (item["file"], item["repetition"], item["report"]["mode"]) for item in records
    }
    manifest = json.loads((DATASET / "manifest.json").read_text())
    cases = {item["case_id"]: item for item in gold["cases"]}
    runtime = OllamaRuntime(config, options=OPTIONS, output_schema=schema("output"))
    entries = [item for item in manifest["files"] if item["split"] == args.split]
    total = len(entries) * args.repetitions * 2
    for entry in entries:
        started = time.perf_counter()
        context = build_context(
            DATASET / entry["file"],
            source=entry["source"],
            case_id=entry["case_id"],
            references_available=entry["references_available"],
        )
        ingestion_ms = (time.perf_counter() - started) * 1000
        case = cases[entry["case_id"]]
        actual = [
            (item["code"], item["row"], item["column"])
            for item in context["occurrences"]
        ]
        expected = [(code, row, column) for code, _, row, column in case["expected"]]
        if actual != expected:
            raise RuntimeError("ingestion differs from approved gold")
        for repetition in range(args.repetitions):
            for mode in ("baseline", "agent"):
                if (entry["file"], repetition, mode) in completed:
                    continue
                if fingerprint() != frozen["fingerprint"] or verify():
                    raise RuntimeError("frozen inputs changed during evaluation")
                with MemorySampler() as memory:
                    report = run_attempt(
                        context,
                        runtime=runtime if mode == "agent" else None,
                        model=config.model if mode == "agent" else "rules-v2",
                        parameters={**OPTIONS, "request_timeout_seconds": 300}
                        if mode == "agent"
                        else {},
                        output_dir=args.output_dir / "attempts",
                    )
                records.append(
                    {
                        "file": entry["file"],
                        "case_id": entry["case_id"],
                        "repetition": repetition,
                        "counts": context["counts"],
                        "ingestion_ms": ingestion_ms,
                        "report": report,
                        "model_process_rss_peak_bytes": memory.peak
                        if mode == "agent"
                        else None,
                        "score": score(context, case, report),
                    }
                )
                save(records_path, {"records": records})
                save(args.output_dir / "summary.json", summarize(records))
                print(
                    f"{len(records)}/{total} {entry['file']} {mode} "
                    f"r{repetition + 1}: {report['outcome']} {report['failure']}",
                    flush=True,
                )
    print(
        "Evaluation complete; inspect metrics, not just process exit status.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
