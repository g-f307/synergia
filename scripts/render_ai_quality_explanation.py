"""Build a standalone offline replay: no server, requests, product routes or DB."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from ai_quality_explanation import (
    ROOT,
    baseline,
    explain,
    read,
    sha,
    validate_text,
)
from run_ai_quality_explanation import UnavailableRuntime


class RejectedRuntime:
    def generate(self, prompt, *, model):
        return json.dumps(
            {
                "explanation": (
                    "O serial é B porque o operador o omitiu intencionalmente."
                ),
                "human_checks": ["Conferir os registros relacionados na fonte."],
            }
        ), 0


class TimeoutRuntime:
    def generate(self, prompt, *, model):
        raise TimeoutError


def build(snapshot: dict, report: dict) -> str:
    if report["snapshot_sha256"] != sha(snapshot) or not report["complete"]:
        raise ValueError("incomplete_or_mismatched_evidence")
    expected = len(snapshot["cases"]) * snapshot["configuration"]["repetitions"] * 2
    if len(report["attempts"]) != expected:
        raise ValueError("missing_attempts")
    scenarios = []
    for case in snapshot["cases"]:
        attempts = [a for a in report["attempts"] if a["case"] == case["key"]]
        for attempt in attempts:
            if [g["group"] for g in attempt["groups"]] != case["envelope"]["groups"]:
                raise ValueError("pipeline_facts_changed")
            for group in attempt["groups"]:
                validate_text(group["group"], group["text"])
        groups = case["envelope"]["groups"]
        scenarios.append(
            {
                "id": Path(case["key"]).name,
                "label": case["label"],
                "provenance": case["provenance"],
                "attempts": attempts,
                "controls": {
                    key: [explain(g, runtime) for g in groups]
                    for key, runtime in (
                        ("rejected", RejectedRuntime()),
                        ("timeout", TimeoutRuntime()),
                        ("unavailable", UnavailableRuntime()),
                    )
                },
                "baseline": [baseline(g) for g in groups],
            }
        )
    payload = (
        json.dumps(
            {
                "scenarios": scenarios,
                "metrics": report["metrics"],
                "manifest_sha256": report["snapshot_sha256"],
                "started_at": report["started_at"],
            },
            ensure_ascii=False,
        )
        .replace("<", "\\u003c")
        .replace("&", "\\u0026")
    )
    shared = (ROOT / "web/src/styles.css").read_text(encoding="utf-8")
    tokens = "\n".join(
        re.findall(r":root\{[^}]+\}|\[data-theme=dark\]\{[^}]+\}", shared)
    )
    template = (ROOT / "scripts/ai_quality_explanation_demo.html").read_text(
        encoding="utf-8"
    )
    return template.replace("/* SHARED_TOKENS */", tokens).replace(
        "__EVIDENCE__", payload
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    document = build(
        read(args.run_directory / "manifest.json"),
        read(args.run_directory / "results.json"),
    )
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(document)


if __name__ == "__main__":
    main()
