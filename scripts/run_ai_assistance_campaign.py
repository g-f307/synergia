#!/usr/bin/env python3
"""Runner reproduzível de campanha (ci-fake ou real) e microbenchmark p95 da #192."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4, uuid5

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from generate_ai_assistance_corpus import (  # noqa: E402
    ACTOR_USER,
    NAMESPACE,
    SyntheticContextReader,
    _ts,
    build_case_context,
    freeze_metadata,
    verify_corpus,
)
from generate_ai_assistance_corpus import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_CORPUS_DIR,
)

from app.ai_assistance_config import AiAssistanceConfig  # noqa: E402
from app.ai_assistance_context import (  # noqa: E402
    ExecutionContextBuilder,
    serialize_snapshot,
)
from app.ai_assistance_context_models import ExecutionAssistanceContext  # noqa: E402
from app.ai_assistance_contract import AiAssistanceResponse  # noqa: E402
from app.ai_assistance_fallback import (  # noqa: E402
    deterministic_fallback,
    deterministic_triage_findings,
    required_limitations,
)
from app.ai_assistance_generator import (  # noqa: E402
    AiAssistanceGenerator,
    _decode,
    prepare_prompt,
    validate_language,
)
from app.ai_assistance_provider import LocalAiModelProvider, ProviderError  # noqa: E402
from app.authorization import ActorContext  # noqa: E402

MODEL = "qwen3:4b-instruct"
MODEL_DIGEST = (
    "sha256:0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
)
REF_PATTERN = re.compile(r"\b(?:DIV|PEN|CLA|EVI|HIS)-[a-f0-9]{32}\b")
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.I,
)


def validate_against_request_schema(
    instance, schema: dict, *, root: dict | None = None
) -> None:
    """Validate raw model JSON against the exact request_schema sent to the runtime."""
    root = root or schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise ValueError(f"unsupported $ref: {ref}")
        target = root["$defs"][ref.removeprefix("#/$defs/")]
        validate_against_request_schema(instance, target, root=root)
        return
    if "anyOf" in schema:
        errors = []
        for branch in schema["anyOf"]:
            try:
                validate_against_request_schema(instance, branch, root=root)
                return
            except ValueError as exc:
                errors.append(str(exc))
        raise ValueError(f"anyOf mismatch: {errors}")
    if "const" in schema and instance != schema["const"]:
        raise ValueError(f"{instance!r} != {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise ValueError(f"{instance!r} not in enum")
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(instance, dict):
            raise ValueError(f"expected object, got {type(instance).__name__}")
        props = schema.get("properties", {})
        for req_key in schema.get("required", []):
            if req_key not in instance:
                raise ValueError(f"missing required key {req_key!r}")
        if schema.get("additionalProperties") is False:
            extra = set(instance) - set(props)
            if extra:
                raise ValueError(f"unexpected keys {sorted(extra)!r}")
        for key, value in instance.items():
            if key in props:
                validate_against_request_schema(value, props[key], root=root)
    elif schema_type == "array":
        if not isinstance(instance, list):
            raise ValueError(f"expected array, got {type(instance).__name__}")
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise ValueError("array shorter than minItems")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise ValueError("array longer than maxItems")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(item, sort_keys=True) for item in instance]
            if len(encoded) != len(set(encoded)):
                raise ValueError("duplicate items in array")
        if "items" in schema:
            for item in instance:
                validate_against_request_schema(item, schema["items"], root=root)
    elif schema_type == "string":
        if not isinstance(instance, str):
            raise ValueError(f"expected string, got {type(instance).__name__}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise ValueError("string shorter than minLength")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise ValueError("string longer than maxLength")


class ControlledCampaignProvider:
    model = "controlled-ci-fake"
    digest = "sha256:" + "1" * 64

    def generate(self, system: str, prompt: str, schema: dict) -> bytes:
        data = json.loads(
            prompt.split("DADOS NÃO CONFIÁVEIS (JSON):\n", 1)[1].rsplit(
                "\nFIM DOS DADOS", 1
            )[0]
        )
        data.update(generated_at=datetime.now(UTC).isoformat(), context_sha256="0" * 64)
        context = ExecutionAssistanceContext.model_validate_json(json.dumps(data))
        props = schema.get("properties", {})
        summary_enum = props.get("summary", {}).get("enum") or []
        summary = (
            summary_enum[0]
            if summary_enum
            else (
                f"A execução registra {context.counts.errors} erros, "
                f"{context.counts.warnings} avisos e "
                f"{context.counts.pending_items} pendências."
            )
        )
        findings_schema = props.get("findings", {})
        max_findings = findings_schema.get("maxItems", 5)
        finding_def = schema.get("$defs", {}).get("Finding", {})
        if max_findings == 0:
            findings: list[dict] = []
        elif "anyOf" in finding_def:
            findings = [
                {
                    "title": branch["properties"]["title"]["const"],
                    "explanation": branch["properties"]["explanation"]["const"],
                    "evidence_refs": list(
                        branch["properties"]["evidence_refs"]["const"]
                    ),
                }
                for branch in finding_def["anyOf"][:max_findings]
            ]
        else:
            findings = deterministic_triage_findings(context)[:max_findings]
        checks_enum = props.get("human_checks", {}).get("items", {}).get("enum") or [
            "Conferência humana das referências disponíveis."
        ]
        limits_enum = props.get("limitations", {}).get("items", {}).get("enum")
        limitations = (
            list(limits_enum) if limits_enum else required_limitations(context)
        )
        return json.dumps(
            {
                "summary": summary,
                "findings": findings,
                "human_checks": [checks_enum[0]],
                "limitations": limitations,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")


class RecordingProvider:
    """Wraps a provider to count real calls and measure/preserve raw bytes."""

    def __init__(self, inner, raw_dir: Path):
        self.inner = inner
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0
        self.current_case_id = "unknown"
        self.last_raw_bytes: int | None = None
        self.last_raw: bytes | None = None
        self.last_schema: dict | None = None
        self.last_transport_error: str | None = None

    @property
    def model(self) -> str:
        return self.inner.model

    @property
    def digest(self) -> str:
        return self.inner.digest

    def begin_case(self, case_id: str) -> None:
        self.current_case_id = case_id
        self.last_raw_bytes = None
        self.last_raw = None
        self.last_schema = None
        self.last_transport_error = None

    def generate(self, system: str, prompt: str, schema: dict) -> bytes:
        self.calls += 1
        self.last_schema = schema
        try:
            raw = self.inner.generate(system, prompt, schema)
        except ProviderError as exc:
            self.last_transport_error = exc.code
            raise
        if isinstance(raw, bytes):
            self.last_raw = raw
            self.last_raw_bytes = len(raw)
            (self.raw_dir / f"{self.current_case_id}.bin").write_bytes(raw)
        return raw


def validate_delivered_output(
    *,
    result,
    context: ExecutionAssistanceContext,
    forbidden_org_ids: set[str],
    context_ms: int,
) -> tuple[bool, bool, str | None]:
    """Revalidate delivered response using the real contract and grounding rules."""
    authorized_refs = context.evidence_refs()
    exposed_refs = [
        ref for finding in result.findings for ref in finding.get("evidence_refs", [])
    ]
    refs_valid = all(ref in authorized_refs for ref in exposed_refs)

    total_ms = max(context_ms + result.elapsed_ms, 0)
    try:
        response = AiAssistanceResponse.model_validate(
            {
                "assistance_id": uuid4(),
                "execution_id": context.subject.execution_id,
                "state": result.state,
                "summary": result.summary,
                "findings": list(result.findings),
                "human_checks": list(result.human_checks),
                "limitations": list(result.limitations),
                "provenance": {
                    "contract_version": "1.0.0",
                    "model": result.model if result.origin == "model" else None,
                    "digest": result.digest if result.origin == "model" else None,
                    "context_hash": result.context_sha256,
                    "prompt_hash": result.prompt_sha256,
                    "origin": result.origin,
                    "timings": {
                        "context_ms": context_ms,
                        "generation_ms": result.elapsed_ms,
                        "total_ms": total_ms,
                    },
                },
                "created_at": datetime.now(UTC),
            },
            context={"evidence_refs": authorized_refs},
        )
        validate_language(response.summary)
        for finding in response.findings:
            validate_language(finding.title)
            validate_language(finding.explanation)
        for check in response.human_checks:
            validate_language(check)
        for lim in response.limitations:
            validate_language(lim)
    except Exception as exc:
        return False, False, f"contract_or_grounding_failed:{type(exc).__name__}"

    if result.origin == "model":
        try:
            raw_model_json = json.dumps(
                {
                    "summary": result.summary,
                    "findings": list(result.findings),
                    "human_checks": list(result.human_checks),
                    "limitations": list(result.limitations),
                },
                ensure_ascii=False,
            ).encode("utf-8")
            _decode(raw_model_json, context)
        except ProviderError as exc:
            return refs_valid, False, f"catalog_grounding_failed:{exc.code}"
    else:
        det_summary, det_limitations = deterministic_fallback(context)
        if result.summary != det_summary or list(result.limitations) != det_limitations:
            return refs_valid, False, "deterministic_fallback_mismatch"

    serialized_text = json.dumps(
        {
            "summary": result.summary,
            "findings": result.findings,
            "human_checks": result.human_checks,
            "limitations": result.limitations,
        },
        ensure_ascii=False,
    )
    found_refs = set(REF_PATTERN.findall(serialized_text))
    if not found_refs.issubset(authorized_refs):
        return False, False, "invented_ref_in_text"

    found_uuids = {u.lower() for u in UUID_PATTERN.findall(serialized_text)}
    allowed_uuids = {str(context.subject.execution_id).lower()}
    if found_uuids - allowed_uuids:
        return refs_valid, False, "external_uuid_in_text"
    if any(org.lower() in serialized_text.lower() for org in forbidden_org_ids):
        return refs_valid, False, "forbidden_org_in_text"
    return refs_valid, True, None


def nearest_rank_p95(samples: list[float]) -> float:
    if not samples:
        raise ValueError("samples cannot be empty")
    ordered = sorted(samples)
    rank = math.ceil(0.95 * len(ordered)) - 1
    return ordered[max(0, min(rank, len(ordered) - 1))]


def measure_microbenchmark_non_inference_p95(
    case_path: Path, warmups: int = 5, samples: int = 30
) -> dict:
    """Microbenchmark of SyntheticContextReader + prepare_prompt (not DB/API)."""
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    org_id = UUID(payload["subject"]["organization_id"])
    exec_id = UUID(payload["subject"]["execution_id"])
    actor = ActorContext(
        user_id=ACTOR_USER,
        session_id=uuid5(NAMESPACE, "p95-session"),
        token_id=uuid5(NAMESPACE, "p95-token"),
        permissions={
            "execution.read": frozenset({org_id}),
            "ai.assistance.generate": frozenset({org_id}),
            "ai.assistance.read": frozenset({org_id}),
        },
        correlation_id=uuid5(NAMESPACE, "p95-corr"),
    )
    builder = ExecutionContextBuilder(SyntheticContextReader(payload))

    def _run_once() -> tuple[float, float, float]:
        t0 = time.perf_counter()
        ctx = builder.build(actor, exec_id, generated_at=_ts(6))
        t1 = time.perf_counter()
        prepare_prompt(ctx)
        t2 = time.perf_counter()
        return (t1 - t0) * 1000.0, (t2 - t1) * 1000.0, (t2 - t0) * 1000.0

    for _ in range(warmups):
        _run_once()

    context_samples: list[float] = []
    prompt_samples: list[float] = []
    total_samples: list[float] = []
    for _ in range(samples):
        c_ms, p_ms, tot_ms = _run_once()
        context_samples.append(round(c_ms, 3))
        prompt_samples.append(round(p_ms, 3))
        total_samples.append(round(tot_ms, 3))

    return {
        "scope": "microbenchmark_synthetic_reader_and_prompt_only",
        "covers_db_auth_persistence": False,
        "reference_case": payload["case_id"],
        "warmups": warmups,
        "sample_count": samples,
        "method": "nearest-rank",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "samples_ms": {
            "context_build": context_samples,
            "prompt_prepare": prompt_samples,
            "microbenchmark_total": total_samples,
        },
        "p95_ms": {
            "context_build": nearest_rank_p95(context_samples),
            "prompt_prepare": nearest_rank_p95(prompt_samples),
            "microbenchmark_total": nearest_rank_p95(total_samples),
        },
    }


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def _corpus_snapshot(corpus_dir: Path) -> dict:
    manifest = verify_corpus(corpus_dir)
    manifest_bytes = (corpus_dir / "manifest.json").read_bytes()
    return {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "freeze": freeze_metadata(),
        "case_hashes": {c["case_id"]: c["sha256"] for c in manifest["cases"]},
    }


def run_campaign(
    *,
    mode: str,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
    output_dir: Path = ROOT / ".local-evidence" / "issue-192",
    endpoint: str | None = None,
) -> dict:
    start_snapshot = _corpus_snapshot(corpus_dir)
    manifest_start = verify_corpus(corpus_dir)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{mode}-{stamp}-{uuid4().hex[:8]}"
    run_dir = output_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = run_dir / "raw"

    if mode == "ci-fake":
        inner_provider = ControlledCampaignProvider()
    elif mode == "real":
        env_model = os.getenv("SYNERGIA_AI_ASSISTANCE_MODEL", MODEL).strip()
        env_digest = os.getenv("SYNERGIA_AI_ASSISTANCE_DIGEST", MODEL_DIGEST).strip()
        if env_model != MODEL or env_digest != MODEL_DIGEST:
            raise ValueError(
                "Modelo ou digest de ambiente divergem do freeze homologado"
            )
        resolved_endpoint = endpoint or os.getenv(
            "SYNERGIA_AI_ASSISTANCE_ENDPOINT", "http://127.0.0.1:11434"
        )
        config = AiAssistanceConfig(
            enabled=True,
            generation_enabled=True,
            endpoint=resolved_endpoint,
            model=MODEL,
            digest=MODEL_DIGEST,
        )
        inner_provider = LocalAiModelProvider(config)
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    provider = RecordingProvider(inner_provider, raw_dir)
    generator = AiAssistanceGenerator(provider)
    all_orgs = set(manifest_start["organizations"].values())

    case_reports: list[dict] = []
    origin_counts = {"model": 0, "deterministic": 0}
    state_counts = {
        "ready": 0,
        "insufficient_evidence": 0,
        "unavailable": 0,
        "rejected": 0,
    }
    sufficient_count = 0
    insufficient_count = 0
    insufficient_calls = 0
    unavailable_on_sufficient = 0
    model_ready_on_sufficient = 0
    schema_valid_on_sufficient = 0
    valid_refs_passed = 0
    no_external_passed = 0
    within_time_budget = 0
    within_bytes_budget = 0

    for case in manifest_start["cases"]:
        case_path = corpus_dir / case["file"]
        t_ctx_start = time.perf_counter()
        ctx = build_case_context(case_path)
        context_ms = round((time.perf_counter() - t_ctx_start) * 1000.0, 3)
        context_bytes = len(serialize_snapshot(ctx))

        calls_before = provider.calls
        provider.begin_case(case["case_id"])
        t_gen_start = time.perf_counter()
        result = generator.generate(ctx)
        elapsed_gen_ms = round((time.perf_counter() - t_gen_start) * 1000.0, 3)
        calls_made = provider.calls - calls_before

        if ctx.sufficiency == "insufficient":
            insufficient_count += 1
            insufficient_calls += calls_made
            generation_ms = None
            inference_applicable = False
            total_ms = round(context_ms + elapsed_gen_ms, 3)
        else:
            sufficient_count += 1
            generation_ms = elapsed_gen_ms
            inference_applicable = True
            total_ms = round(context_ms + generation_ms, 3)
            if result.state == "unavailable":
                unavailable_on_sufficient += 1
            if result.state == "ready" and result.origin == "model":
                model_ready_on_sufficient += 1

        origin_counts[result.origin] = origin_counts.get(result.origin, 0) + 1
        state_counts[result.state] = state_counts.get(result.state, 0) + 1

        delivered_bytes = len(
            json.dumps(
                {
                    "summary": result.summary,
                    "findings": result.findings,
                    "human_checks": result.human_checks,
                    "limitations": result.limitations,
                },
                ensure_ascii=False,
            ).encode("utf-8")
        )
        raw_bytes = provider.last_raw_bytes
        transport_error = provider.last_transport_error
        raw_schema_valid: bool | None = None
        raw_schema_error: str | None = None
        if inference_applicable:
            if provider.last_raw is not None and provider.last_schema is not None:
                try:
                    validate_against_request_schema(
                        json.loads(provider.last_raw.decode("utf-8")),
                        provider.last_schema,
                    )
                    raw_schema_valid = True
                    schema_valid_on_sufficient += 1
                except (UnicodeError, ValueError) as exc:
                    raw_schema_valid = False
                    raw_schema_error = str(exc)
            else:
                raw_schema_valid = False
                raw_schema_error = "missing_raw_or_schema"

        forbidden_orgs = all_orgs - {str(ctx.subject.organization_id)}
        refs_valid, no_external, validation_reason = validate_delivered_output(
            result=result,
            context=ctx,
            forbidden_org_ids=forbidden_orgs,
            context_ms=int(context_ms),
        )

        time_ok = total_ms <= 30000.0
        bytes_ok = (
            context_bytes <= 8192
            and delivered_bytes <= 8192
            and (raw_bytes is None or raw_bytes <= 8192)
            and transport_error != "runtime_response_too_large"
        )

        if refs_valid:
            valid_refs_passed += 1
        if no_external:
            no_external_passed += 1
        if time_ok:
            within_time_budget += 1
        if bytes_ok:
            within_bytes_budget += 1

        case_reports.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "organization_key": case["organization_key"],
                "source": case["source"],
                "status": case["status"],
                "sufficiency": ctx.sufficiency,
                "truncated_sections": list(ctx.truncated_sections),
                "inference_applicable": inference_applicable,
                "provider_calls": calls_made,
                "context_ms": context_ms,
                "generation_ms": generation_ms,
                "total_ms": total_ms,
                "context_bytes": context_bytes,
                "raw_response_bytes": raw_bytes,
                "delivered_response_bytes": delivered_bytes,
                "transport_error": transport_error,
                "state": result.state,
                "origin": result.origin,
                "rejection_code": result.rejection_code,
                "refs_valid": refs_valid,
                "no_external_facts": no_external,
                "raw_matches_request_schema": raw_schema_valid,
                "raw_schema_error": raw_schema_error,
                "validation_reason": validation_reason,
            }
        )

    p95 = measure_microbenchmark_non_inference_p95(
        corpus_dir / manifest_start["cases"][0]["file"]
    )
    end_snapshot = _corpus_snapshot(corpus_dir)
    freeze_unchanged = start_snapshot == end_snapshot

    total_cases = len(case_reports)
    gates = {
        "freeze_unchanged": {
            "passed": freeze_unchanged,
            "start_manifest_sha256": start_snapshot["manifest_sha256"],
            "end_manifest_sha256": end_snapshot["manifest_sha256"],
        },
        "valid_references": {
            "passed": valid_refs_passed == total_cases,
            "numerator": valid_refs_passed,
            "denominator": total_cases,
        },
        "no_external_facts": {
            "passed": no_external_passed == total_cases,
            "numerator": no_external_passed,
            "denominator": total_cases,
        },
        "no_unavailable_on_sufficient": {
            "passed": unavailable_on_sufficient == 0,
            "unavailable_count": unavailable_on_sufficient,
            "denominator": sufficient_count,
        },
        "inference_completed": {
            "passed": (
                unavailable_on_sufficient == 0
                and model_ready_on_sufficient == sufficient_count
            ),
            "model_ready": model_ready_on_sufficient,
            "denominator": sufficient_count,
        },
        "raw_matches_request_schema": {
            "passed": schema_valid_on_sufficient == sufficient_count,
            "numerator": schema_valid_on_sufficient,
            "denominator": sufficient_count,
        },
        "insufficient_no_inference": {
            "passed": insufficient_calls == 0,
            "calls": insufficient_calls,
            "denominator": insufficient_count,
        },
        "within_30s_budget": {
            "passed": within_time_budget == total_cases,
            "numerator": within_time_budget,
            "denominator": total_cases,
        },
        "within_8192_bytes": {
            "passed": within_bytes_budget == total_cases,
            "numerator": within_bytes_budget,
            "denominator": total_cases,
        },
        "microbenchmark_p95_under_1000ms": {
            "passed": p95["p95_ms"]["microbenchmark_total"] < 1000.0,
            "value_ms": p95["p95_ms"]["microbenchmark_total"],
            "threshold_ms": 1000.0,
        },
    }
    overall_passed = all(g["passed"] for g in gates.values())

    report = {
        "schema_version": "1.1.0",
        "issue": 192,
        "run_id": run_id,
        "mode": mode,
        "commit": _git_head(),
        "executed_at": datetime.now(UTC).isoformat(),
        "overall_passed": overall_passed,
        "freeze_verified_start": True,
        "freeze_verified_end": freeze_unchanged,
        "counts": {
            "total_cases": total_cases,
            "sufficient_cases": sufficient_count,
            "insufficient_cases": insufficient_count,
            "provider_calls": provider.calls,
            "by_origin": origin_counts,
            "by_state": state_counts,
        },
        "microbenchmark_non_inference_p95": p95,
        "cases": case_reports,
        "gates": gates,
    }

    report_filename = (
        "ci-fake-report.json" if mode == "ci-fake" else "real-qwen-report.json"
    )
    report_path = run_dir / report_filename
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    hashes = {
        p.relative_to(run_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(run_dir.rglob("*"))
        if p.is_file() and p.name != "manifest-hashes.json"
    }
    (run_dir / "manifest-hashes.json").write_text(
        json.dumps(hashes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report["run_dir"] = str(run_dir)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("ci-fake", "real"), default="ci-fake")
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / ".local-evidence" / "issue-192"
    )
    parser.add_argument("--endpoint", default=None)
    args = parser.parse_args()
    report = run_campaign(
        mode=args.mode,
        corpus_dir=args.corpus_dir,
        output_dir=args.output_dir,
        endpoint=args.endpoint,
    )
    print(
        json.dumps(
            {
                "run_id": report["run_id"],
                "run_dir": report["run_dir"],
                "mode": report["mode"],
                "overall_passed": report["overall_passed"],
                "counts": report["counts"],
                "gates": report["gates"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
