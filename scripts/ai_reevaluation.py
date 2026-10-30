"""Frozen, resumable comparisons for issue #148, separate from product code."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import time
import urllib.request
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

import ai_operational_summary as operational
import ai_quality_diagnosis as quality
from ai_poc_foundation import (
    LocalModelConfig,
    LocalRuntimeTimeout,
    OllamaRuntime,
    PoCFoundationError,
    _NoRedirectHandler,
)
from ai_reevaluation_telemetry import Sampler, hardware, stable_json
from ai_reevaluation_guidance import GUIDED_FIELDS, GuidedQualityRuntime
from ai_reevaluation_native import (
    NATIVE_ARCHITECTURES,
    NativeStructuredRuntime,
    NativeToolsRuntime,
    collect_native_attempt,
)
from evaluate_ai_operational import _score, score_tool_calls
from evaluate_ai_quality import score as quality_score

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/ai-reevaluation-protocol.json"
CONFIG_SCHEMA = ROOT / "docs/schemas/ai-reevaluation-config.schema.json"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    return hashlib.sha256(stable_json(value)).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(stable_json(value) + b"\n")
    temporary.replace(path)


def contained(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise PoCFoundationError("missing_or_escaping_input")
    return path


def configuration(path: Path) -> dict:
    config = read(path)
    validate_configuration(config)
    return config


def validate_configuration(config: dict):
    if not Draft202012Validator(read(CONFIG_SCHEMA)).is_valid(config):
        raise PoCFoundationError("invalid_configuration")
    contained(ROOT / "scripts/ai_poc_prompts", config["prompt"])
    LocalModelConfig(model=config["model"] or "baseline", endpoint=config["endpoint"])
    if (
        config.get("evidence_only_context")
        and config.get("architecture") != "quality_policy_guided"
    ):
        raise PoCFoundationError("evidence_projection_requires_guided_quality")
    if (
        config.get("context_contract_guard")
        and config.get("architecture") != "operational_native_staged"
    ):
        raise PoCFoundationError("context_guard_requires_staged_native_flow")
    if config.get("architecture") in NATIVE_ARCHITECTURES and (
        config["kind"] != "operational"
        or config["mode"] != "agent"
        or urlsplit(config["endpoint"]).path != "/api/chat"
    ):
        raise PoCFoundationError("native_tools_require_operational_chat_agent")
    if config.get("architecture") == "quality_policy_guided" and (
        config["kind"] != "quality" or config["mode"] != "agent"
    ):
        raise PoCFoundationError("guidance_requires_quality_agent")
    if config["mode"] == "agent" and not all(
        config[key] for key in ("model", "model_digest", "runtime_version")
    ):
        raise PoCFoundationError("agent_requires_pinned_model_and_runtime")
    if config["mode"] == "baseline" and any(
        config[key] is not None for key in ("model", "model_digest", "runtime_version")
    ):
        raise PoCFoundationError("baseline_has_no_model")


def corpus(kind: str) -> tuple[list[dict], dict]:
    root = ROOT / f"data/synthetic/ai-{kind}-v3"
    manifest = read(root / "manifest.json")
    if kind == "quality":
        annotations = read(root / "scenarios.json")
        if file_digest(root / "scenarios.json") != manifest["scenarios_sha256"]:
            raise PoCFoundationError("annotations_hash_mismatch")
        labels = {case["case_id"]: case for case in annotations["cases"]}
        entries = manifest["files"]
        for item in entries:
            path = contained(root, item["file"])
            if file_digest(path) != item["sha256"]:
                raise PoCFoundationError("input_hash_mismatch")
        review = annotations["gold_review"]
        cases = [
            {
                **item,
                "path": contained(root, item["file"]),
                "gold": labels[item["case_id"]],
                "key": item["file"],
            }
            for item in entries
        ]
    else:
        review = manifest["gold_review"]
        cases = []
        for item in manifest["cases"]:
            for key in ("input", "gold"):
                if file_digest(contained(root, item[key])) != item[key + "_sha256"]:
                    raise PoCFoundationError("operational_hash_mismatch")
            cases.append(
                {
                    **item,
                    "key": item["case_id"],
                    "path": contained(root, item["input"]),
                    "gold": read(contained(root, item["gold"])),
                }
            )
    if len({item["key"] for item in cases}) != len(cases):
        raise PoCFoundationError("duplicate_case")
    return cases, review


def check_gate(config: dict, protocol: dict, review: dict):
    if config["mode"] == "agent":
        candidate = next(
            (m for m in protocol["models"] if m["tag"] == config["model"]), None
        )
        if candidate is None or candidate["license"].startswith("pending"):
            raise PoCFoundationError("candidate_license_review_required")
    if (
        protocol["human_review"]["status"] != "approved"
        or review["status"] != "approved_by_user"
        or not all(review.get(key) for key in ("reviewer", "date", "decision"))
    ):
        raise PoCFoundationError("gold_review_required")
    if config["split"] == "evaluation":
        if config["mode"] == "agent" and config["think"] not in candidate.get(
            "supported_thinking_modes", [True, False]
        ):
            raise PoCFoundationError("candidate_mode_incompatible_with_upstream")
        selected = protocol["evaluation"]["final_configurations"]
        if (
            protocol["status"] != "frozen"
            or {"id": config["id"], "config_sha256": digest(config)} not in selected
            or config["repetitions"]
            != protocol["evaluation"]["repetitions_per_configuration"]
            or config["repetitions"] < 3
        ):
            raise PoCFoundationError("reserved_evaluation_requires_frozen_selection")
    if (
        config["warmup_attempts"]
        != protocol["evaluation"]["warmup_attempts_per_configuration"]
    ):
        raise PoCFoundationError("warmup_protocol_mismatch")


def request_json(config: dict, route: str, payload=None):
    parts = urlsplit(config["endpoint"])
    url = f"{parts.scheme}://{parts.netloc}/api/{route}"
    request = urllib.request.Request(
        url,
        data=stable_json(payload) if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    # Local requests must not pass through an environment-configured proxy.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirectHandler()
    )
    with opener.open(request, timeout=10) as response:
        return json.load(response)


def runtime_metadata(config: dict) -> dict:
    if config["mode"] == "baseline":
        return {"mode": "baseline"}
    version = request_json(config, "version")["version"]
    models = request_json(config, "tags")["models"]
    model = next((m for m in models if m["name"] == config["model"]), None)
    if (
        model is None
        or model["digest"] != config["model_digest"]
        or version != config["runtime_version"]
    ):
        raise PoCFoundationError("model_or_runtime_pin_mismatch")
    details = request_json(config, "show", {"model": config["model"]})
    protocol = read(PROTOCOL)
    candidate = next(m for m in protocol["models"] if m["tag"] == config["model"])
    if model["details"].get("quantization_level") != candidate["quantization"]:
        raise PoCFoundationError("quantization_pin_mismatch")
    if config["think"] and "thinking" not in details.get("capabilities", []):
        raise PoCFoundationError("thinking_not_supported")
    return {
        "runtime_version": version,
        "model": model["name"],
        "digest": model["digest"],
        "details": model["details"],
        "capabilities": details.get("capabilities", []),
        "license_sha256": digest(details.get("license", "")),
    }


def fingerprint() -> dict:
    roots = [
        "scripts",
        "backend/app",
        "docs/schemas",
        "data/synthetic/ai-quality-v3",
        "data/synthetic/ai-operational-v3",
    ]
    paths = [
        p
        for root in roots
        for p in (ROOT / root).rglob("*")
        if p.is_file()
        and p.suffix in {".py", ".json", ".txt", ".csv", ".xlsx"}
        and "__pycache__" not in p.parts
    ]
    paths += [PROTOCOL, ROOT / "backend/requirements.txt"]
    return {p.relative_to(ROOT).as_posix(): file_digest(p) for p in sorted(set(paths))}


def freeze(config: dict, *, metadata=runtime_metadata, identity=hardware) -> dict:
    validate_configuration(config)
    cases, review = corpus(config["kind"])
    protocol = read(PROTOCOL)
    check_gate(config, protocol, review)
    selected = [item["key"] for item in cases if item["split"] == config["split"]]
    if not selected:
        raise PoCFoundationError("empty_split")
    runtime = metadata(config)
    if config.get(
        "architecture"
    ) in NATIVE_ARCHITECTURES and "tools" not in runtime.get("capabilities", []):
        raise PoCFoundationError("native_tools_not_supported")
    return {
        "schema_version": 1,
        "configuration": config,
        "protocol": protocol,
        "config_sha256": digest(config),
        "hashes": fingerprint(),
        "runtime": runtime,
        "hardware": identity(),
        "cases": selected,
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("jsonschema", "openpyxl", "pydantic")
        },
    }


class MeteredRuntime:
    """Apply a remaining attempt budget on every tool-loop generation."""

    def __init__(self, runtime, config, sampler):
        self.runtime, self.config, self.sampler = runtime, config, sampler
        self.deadline = time.monotonic() + config["attempt_timeout_seconds"]
        self.calls = []
        self.failure = None

    def generate(self, prompt, *, model):
        if self.sampler.failure:
            self.failure = "resource_limit"
            raise PoCFoundationError("resource_limit")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self.failure = "attempt_time_limit"
            raise LocalRuntimeTimeout("attempt_time_limit")
        if isinstance(self.runtime, OllamaRuntime):
            self.runtime.config = replace(
                self.runtime.config,
                timeout_seconds=min(remaining, self.config["request_timeout_seconds"]),
            )
        try:
            response = self.runtime.generate(prompt, model=model)
            if time.monotonic() > self.deadline:
                self.failure = "attempt_time_limit"
                raise LocalRuntimeTimeout("attempt_time_limit")
            return response
        finally:
            metrics = dict(getattr(self.runtime, "response_metrics", {}))
            reason = getattr(self.runtime, "response_done_reason", None)
            self.calls.append(
                {
                    "metrics": metrics,
                    "done_reason": reason,
                    "truncated": reason == "length",
                    "request_sha256": getattr(self.runtime, "request_sha256", None),
                    "rejected_response_sha256": getattr(
                        self.runtime, "rejected_response_sha256", None
                    ),
                }
            )
            self.failure = self.failure or getattr(
                self.runtime, "guidance_failure", None
            )

    @property
    def response_metrics(self):
        return getattr(self.runtime, "response_metrics", {})

    @property
    def response_model(self):
        return getattr(self.runtime, "response_model", None)


def make_runtime(config: dict):
    options = dict(config["options"])
    if config["processor"] == "cpu_only":
        options["num_gpu"] = 0
    output = (
        quality.schema("output")
        if config["kind"] == "quality"
        else operational.interaction_schema()
    )
    runtime_class = (
        GuidedQualityRuntime
        if config.get("architecture") == "quality_policy_guided"
        else OllamaRuntime
    )
    if config.get("architecture") in NATIVE_ARCHITECTURES:
        runtime_class = (
            NativeStructuredRuntime
            if config.get("architecture")
            in {"operational_native_structured", "operational_native_staged"}
            else NativeToolsRuntime
        )
    runtime = runtime_class(
        LocalModelConfig(
            config["model"], config["endpoint"], config["request_timeout_seconds"]
        ),
        options=options,
        output_schema=output,
        think=config["think"],
        keep_alive=config["keep_alive_seconds"],
    )
    if isinstance(runtime, GuidedQualityRuntime):
        runtime.evidence_only_context = config.get("evidence_only_context", False)
    return runtime


def execute_case(config, item, directory, runtime):
    prompt = contained(ROOT / "scripts/ai_poc_prompts", config["prompt"])
    if config["kind"] == "quality":
        context = quality.build_context(
            item["path"],
            source=item["source"],
            case_id=item["case_id"],
            references_available=item["references_available"],
        )
        report = quality.run_attempt(
            context,
            runtime=runtime,
            model=config["model"] or "baseline",
            output_dir=directory,
            parameters=config["options"],
            prompt_path=prompt,
        )
        return {
            "report": report,
            "score": quality_score(context, item["gold"], report),
            "free_text_review": "pending",
            "metric_scope": "structured_not_semantic",
        }
    case = operational.load_case(item["path"])
    if runtime is None:
        started = time.perf_counter()
        output = operational.baseline(case)
        operational.validate_output(case, output)
        report = {
            "output": output,
            "schema_valid": True,
            "failure": None,
            "tool_calls": [],
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }
    else:
        collector = (
            collect_native_attempt
            if config.get("architecture") in NATIVE_ARCHITECTURES
            else operational.collect_agent_attempt
        )
        if config.get("architecture") in {
            "operational_native_structured",
            "operational_native_staged",
        }:
            report = collector(
                case,
                runtime,
                config["model"],
                prompt_path=prompt,
                structured_final=True,
                completion_tool=config.get("architecture")
                == "operational_native_staged",
                context_guard=config.get("context_contract_guard", False),
            )
        else:
            report = collector(case, runtime, config["model"], prompt_path=prompt)
    return {
        "report": report,
        "exact_reference_score": _score(report["output"], item["gold"])
        if report["output"]
        else None,
        "tool_score": score_tool_calls(
            case, item["required_tools"], report["tool_calls"]
        )
        if runtime
        else None,
        "free_text_review": "pending",
        "metric_scope": "exact_text_not_semantic_fidelity",
    }


def plan(snapshot: dict) -> list[dict]:
    config = snapshot["configuration"]
    # Warm-ups always use development cases, even for a reserved run.
    development, _ = corpus(config["kind"])
    first = next(item["key"] for item in development if item["split"] == "development")
    entries = [
        {"case": first, "repetition": n, "phase": "warmup"}
        for n in range(config["warmup_attempts"])
    ]
    entries += [
        {"case": key, "repetition": n, "phase": "measured"}
        for n in range(config["repetitions"])
        for key in snapshot["cases"]
    ]
    return [{**entry, "id": f"{index:04d}"} for index, entry in enumerate(entries)]


def run(
    snapshot: dict,
    output: Path,
    *,
    resume=False,
    allow_inference=False,
    freezer=freeze,
    runtime_factory=make_runtime,
    sampler_factory=Sampler,
    loaded_models=None,
):
    config = snapshot["configuration"]
    if config["mode"] == "agent" and not allow_inference:
        raise PoCFoundationError("explicit_inference_authorization_required")
    if freezer(config) != snapshot:
        raise PoCFoundationError("frozen_inputs_environment_or_runtime_changed")
    output.mkdir(parents=True, exist_ok=True)
    journal = output / "run.json"
    expected = plan(snapshot)
    if journal.exists():
        if not resume:
            raise PoCFoundationError("existing_run_requires_resume")
        state = read(journal)
        if state["snapshot"] != snapshot or state["plan"] != expected:
            raise PoCFoundationError("resume_fingerprint_mismatch")
        if len({a["id"] for a in state["attempts"]}) != len(state["attempts"]):
            raise PoCFoundationError("duplicate_attempt_in_journal")
        if [a["id"] for a in state["attempts"]] != [
            a["id"] for a in expected[: len(state["attempts"])]
        ] or any(
            any(a.get(key) != entry[key] for key in ("case", "repetition", "phase"))
            for a, entry in zip(state["attempts"], expected)
        ):
            raise PoCFoundationError("journal_plan_mismatch")
        for record in state["attempts"]:
            if record["state"] == "started":
                record.update(state="finished", failure="interrupted", result=None)
        save(journal, state)
    else:
        if resume or any(output.iterdir()):
            raise PoCFoundationError("resume_missing_journal_or_nonempty_directory")
        state = {
            "snapshot": snapshot,
            "plan": expected,
            "attempts": [],
            "complete": False,
        }
        save(journal, state)
    completed = {a["id"] for a in state["attempts"]}
    state.pop("stop_reason", None)
    cases, _ = corpus(config["kind"])
    by_key = {item["key"]: item for item in cases}
    for entry in expected:
        if entry["id"] in completed:
            continue
        with sampler_factory(
            snapshot["protocol"]["resources"], output, state.get("resource_reference")
        ) as sampler:
            if "resource_reference" not in state and hasattr(sampler, "before"):
                state["resource_reference"] = sampler.before
            if sampler.failure:
                state["stop_reason"] = sampler.failure
                save(journal, state)
                break
            runtime = None
            if config["mode"] == "agent":
                loaded = (
                    loaded_models or (lambda: request_json(config, "ps")["models"])
                )()
                if any(
                    m["name"] != config["model"]
                    or m.get("digest") != config["model_digest"]
                    for m in loaded
                ):
                    raise PoCFoundationError("dedicated_runtime_required")
                raw = runtime_factory(config)
                runtime = MeteredRuntime(raw, config, sampler)
            else:
                loaded = []
            record = {
                **entry,
                "state": "started",
                "result": None,
                "failure": None,
                "loaded_before": loaded,
            }
            state["attempts"].append(record)
            save(
                journal, state
            )  # Persist BEFORE the request; crashes cannot erase an attempt.
            try:
                result = execute_case(
                    config, by_key[entry["case"]], output / entry["id"], runtime
                )
                record.update(result=result, state="finished")
                report = result["report"]
                record["failure"] = report.get("failure")
                if runtime:
                    record["generation"] = runtime.calls
                    record["failure"] = runtime.failure or record["failure"]
                    if not record["failure"] and any(
                        c["truncated"] for c in runtime.calls
                    ):
                        record["failure"] = "generation_truncated"
            except Exception:
                record.update(state="finished", failure="unexpected_attempt_failure")
            if config["mode"] == "agent":
                try:
                    record["loaded_after"] = (
                        loaded_models or (lambda: request_json(config, "ps")["models"])
                    )()
                except Exception:
                    record["loaded_after"] = None
        record["resources"] = sampler.report()
        if sampler.failure:
            record["failure"] = "resource_limit"
            state["stop_reason"] = sampler.failure
        save(journal, state)
        if sampler.failure:
            break
    state["complete"] = len(state["attempts"]) == len(expected)
    state["quality_denominator"] = sum(
        a["phase"] == "measured" for a in state["attempts"]
    )
    state["planned_quality_denominator"] = sum(
        a["phase"] == "measured" for a in expected
    )
    state["failed_measured_attempts"] = sum(
        a["phase"] == "measured" and a["failure"] is not None for a in state["attempts"]
    )
    save(journal, state)
    return state


def summarize_run(state: dict) -> dict:
    """Structural metrics only. Incomplete runs cannot support a final decision."""
    import math
    import statistics
    from collections import Counter

    attempts = [a for a in state["attempts"] if a["phase"] == "measured"]
    n = len(attempts)
    reports = [(a.get("result") or {}).get("report", {}) for a in attempts]
    times = sorted(r["elapsed_ms"] for r in reports if "elapsed_ms" in r)
    calls = [call for a in attempts for call in a.get("generation", [])]
    resources = [a.get("resources", {}) for a in attempts]
    config = state["snapshot"]["configuration"]
    guided_fields = []
    case_scope = "original_output"
    if config.get("architecture") == "quality_policy_guided":
        guided_fields = GUIDED_FIELDS
        case_scope = "pipeline_with_deterministic_status"
    elif config.get("context_contract_guard"):
        guided_fields = [
            "status_when_retrieved_partial_without_data",
            "question_bounds",
        ]
        case_scope = "pipeline_with_context_contract_guard"

    def peak(key):
        known = [r[key] for r in resources if r.get(key) is not None]
        return max(known) if known else None

    summary = {
        "id": state["snapshot"]["configuration"]["id"],
        "complete": state["complete"],
        "planned_measured_attempts": state["planned_quality_denominator"],
        "measured_attempts": n,
        "warmup_attempts": len(state["attempts"]) - n,
        "failures": dict(Counter(a["failure"] for a in attempts if a["failure"])),
        "accepted_rate": sum(a["failure"] is None for a in attempts) / n if n else None,
        "schema_valid_rate": sum(bool(r.get("schema_valid")) for r in reports) / n
        if n
        else None,
        "mean_latency_ms": statistics.mean(times) if times else None,
        "p95_latency_ms": times[math.ceil(0.95 * len(times)) - 1] if times else None,
        "latency_known_attempts": len(times),
        "latency_unknown_attempts": n - len(times),
        "sampled_rss_peak_bytes": peak("sampled_rss_peak_bytes"),
        "sampled_total_gpu_used_peak_bytes": peak("sampled_total_gpu_used_peak_bytes"),
        "generation_calls": len(calls),
        "generated_tokens_known": sum(c["metrics"].get("eval_count", 0) for c in calls),
        "generation_calls_without_token_telemetry": sum(
            "eval_count" not in c["metrics"] for c in calls
        ),
        "load_duration_ns_known": sum(
            c["metrics"].get("load_duration", 0) for c in calls
        ),
        "generation_calls_without_load_telemetry": sum(
            "load_duration" not in c["metrics"] for c in calls
        ),
        "semantic_fidelity": "pending_human_review",
        "decision": "not_decided",
        "architecture": state["snapshot"]["configuration"].get(
            "architecture", "free_contract"
        ),
        "deterministic_guided_fields": guided_fields,
        "case_correct_scope": case_scope,
        "model_context_scope": "evidence_projection_v1"
        if config.get("evidence_only_context")
        else "original_context",
        "context_contract_guidance_applied_attempts": sum(
            bool(r.get("context_contract_guidance_applied")) for r in reports
        ),
    }
    groups = {
        key: [a for a in attempts if a["case"] == key]
        for key in state["snapshot"]["cases"]
    }
    consistent = 0
    repeated_groups = 0
    for group in groups.values():
        if len(group) < 3:
            continue
        repeated_groups += 1
        signatures = [
            digest(
                (a.get("result") or {}).get("score", {}).get("semantic_signature")
                if state["snapshot"]["configuration"]["kind"] == "quality"
                else (a.get("result") or {}).get("report", {}).get("output")
            )
            for a in group
        ]
        consistent += (
            len(group) >= 3
            and all(a["failure"] is None for a in group)
            and len(set(signatures)) == 1
        )
    summary["valid_structural_consistency"] = (
        consistent / repeated_groups if repeated_groups else None
    )
    summary["consistency_cases_with_three_repetitions"] = repeated_groups
    if state["snapshot"]["configuration"]["kind"] == "quality":
        summary["accepted_case_correct_rate"] = (
            sum(
                a["failure"] is None
                and bool((a.get("result") or {}).get("score", {}).get("case_correct"))
                for a in attempts
            )
            / n
            if n
            else None
        )
        summary["abstention_correct_rate"] = (
            sum(
                a["failure"] is None
                and bool(
                    (a.get("result") or {}).get("score", {}).get("abstention_correct")
                )
                for a in attempts
            )
            / n
            if n
            else None
        )
        tp = fp = fn = 0
        for attempt in attempts:
            score = (attempt.get("result") or {}).get("score")
            if score is None:
                # Missing score cannot improve F1: metric is unavailable until reconciled.
                summary["accepted_f1_micro"] = None
                break
            if attempt["failure"] is None:
                tp += score["tp"]
                fp += score["fp"]
                fn += score["fn"]
            else:
                fp += score["fp"]
                fn += score["tp"] + score["fn"]
        else:
            summary["accepted_f1_micro"] = (
                2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0
            )
    else:
        summary["diagnostic_status_accuracy"] = (
            sum(
                a["failure"] is None
                and bool(
                    (a.get("result") or {})
                    .get("exact_reference_score", {})
                    .get("status_correct")
                )
                for a in attempts
            )
            / n
            if n
            else None
        )
        summary["conservative_exact_reference_f1"] = (
            sum(
                (a["result"].get("exact_reference_score") or {}).get("f1", 0)
                if a["failure"] is None
                else 0
                for a in attempts
            )
            / n
            if n
            else None
        )
        scores = [(a.get("result") or {}).get("tool_score") for a in attempts]
        summary["tool_choice_accuracy"] = (
            sum(s["accuracy"] if s else 0 for s in scores) / n if n else None
        )
        summary["tool_metric_applies"] = (
            state["snapshot"]["configuration"]["mode"] == "agent"
        )
        if not summary["tool_metric_applies"]:
            summary["tool_choice_accuracy"] = None
    return summary


def compare(states: list[dict]) -> dict:
    if not states:
        raise PoCFoundationError("comparison_requires_runs")
    first = states[0]["snapshot"]
    identities = set()
    for state in states:
        current = state["snapshot"]
        identity = current["configuration"]["id"]
        if identity in identities:
            raise PoCFoundationError("duplicate_configuration_in_comparison")
        identities.add(identity)
        if any(
            current[key] != first[key]
            for key in ("cases", "hashes", "hardware", "packages")
        ) or any(
            current["configuration"][key] != first["configuration"][key]
            for key in ("kind", "split", "repetitions")
        ):
            raise PoCFoundationError(
                "comparison_requires_identical_cases_code_environment"
            )
    if not any(s["snapshot"]["configuration"]["mode"] == "baseline" for s in states):
        raise PoCFoundationError("comparison_requires_baseline")
    return {
        "schema_version": 1,
        "kind": first["configuration"]["kind"],
        "split": first["configuration"]["split"],
        "cases": first["cases"],
        "runs": [summarize_run(state) for state in states],
        "semantic_review": "pending",
        "decision": "not_decided",
    }
