"""Internal generation boundary. Model text is accepted only from a grounded catalog."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, Field, ValidationError

from app.ai_assistance_context import canonical_bytes, serialize_snapshot
from app.ai_assistance_context_models import ExecutionAssistanceContext
from app.ai_assistance_contract import StrictContract, plain_text
from app.ai_assistance_fallback import (
    HUMAN_CHECK_OPTIONS,
    describe_finding_items,
    deterministic_fallback,
    deterministic_triage_findings,
    required_limitations,
    valid_summaries,
    validate_language,
)
from app.ai_assistance_provider import AiModelProvider, ProviderError
from app.ai_assistance_telemetry import (
    GENERATION_DURATION,
    GENERATIONS,
    RESPONSE_BYTES,
    environment,
    inference,
    log_event,
)
from app.observability.telemetry import safe_log

_ASSETS = Path(__file__).parent / "ai_assistance_assets"
SYSTEM = (_ASSETS / "system.txt").read_text(encoding="utf-8")
TEMPLATE = (_ASSETS / "template.txt").read_text(encoding="utf-8")
SYSTEM_SHA256 = hashlib.sha256(SYSTEM.encode()).hexdigest()
TEMPLATE_SHA256 = hashlib.sha256(TEMPLATE.encode()).hexdigest()


def _log_unexpected_exception(exc: Exception) -> None:
    """Log only a sanitized exception type, without stack or exception content."""
    exception_type = type(exc).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", exception_type):
        exception_type = "Exception"
    safe_log(
        logging.ERROR,
        "ai.assistance.unexpected_error",
        exception_type=exception_type,
        error_code="internal_error",
    )


SafeText = Annotated[
    str, Field(min_length=1, max_length=600), AfterValidator(validate_language)
]


class Finding(StrictContract):
    title: Annotated[SafeText, Field(max_length=120)]
    explanation: SafeText
    evidence_refs: list[str] = Field(min_length=1, max_length=3)


class ModelOutput(StrictContract):
    summary: SafeText
    findings: list[Finding] = Field(max_length=5)
    human_checks: list[SafeText] = Field(max_length=3)
    limitations: list[SafeText] = Field(max_length=5)


SCHEMA = ModelOutput.model_json_schema()
SCHEMA["$id"] = "urn:synergia:ai-assistance:model-output:1.0.0"
if json.loads((_ASSETS / "output.schema.json").read_text(encoding="utf-8")) != SCHEMA:
    raise RuntimeError("assistance model output schema differs from versioned asset")
SCHEMA_SHA256 = hashlib.sha256(
    json.dumps(
        SCHEMA, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
).hexdigest()


@dataclass(frozen=True)
class GenerationResult:
    state: str
    origin: str
    summary: str
    findings: list[dict]
    human_checks: list[str]
    limitations: list[str]
    rejection_code: str | None
    context_sha256: str
    prompt_sha256: str
    response_sha256: str | None
    schema_sha256: str
    base_schema_sha256: str
    model: str
    digest: str
    elapsed_ms: int


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _decode(raw: bytes, context: ExecutionAssistanceContext) -> ModelOutput:
    if len(raw) > 8192:
        raise ProviderError("response_too_large")
    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, RecursionError):
        raise ProviderError("invalid_json") from None
    try:
        output = ModelOutput.model_validate(data)
    except (ValidationError, ValueError, TypeError):
        raise ProviderError("invalid_schema") from None

    # Controlled declarative grammar makes grounding decidable. A lexical filter
    # alone cannot establish whether an arbitrary natural-language claim is true.
    if output.summary not in valid_summaries(context):
        raise ProviderError("ungrounded_summary")
    refs = context.evidence_refs()
    used_refs = set()
    for finding in output.findings:
        selected = finding.evidence_refs
        if (
            len(set(selected)) != len(selected)
            or not set(selected) <= refs
            or used_refs.intersection(selected)
        ):
            raise ProviderError("invalid_reference")
        used_refs.update(selected)
        valid_titles, valid_explanations = describe_finding_items(context, selected)
        if (
            finding.title not in valid_titles
            or finding.explanation not in valid_explanations
        ):
            raise ProviderError("ungrounded_finding")
    if any(
        check not in HUMAN_CHECK_OPTIONS for check in output.human_checks
    ) or len(set(output.human_checks)) != len(output.human_checks):
        raise ProviderError("ungrounded_checks")
    required = set(required_limitations(context))
    if not required <= set(output.limitations):
        raise ProviderError("missing_limitations")
    if (
        len(set(output.limitations)) != len(output.limitations)
        or not set(output.limitations) <= required
    ):
        raise ProviderError("ungrounded_limitations")
    return output


def _compact_prompt_data(
    context: ExecutionAssistanceContext, triage_preview: list[dict]
) -> bytes:
    """Project prioritized items into the model prompt while keeping full counts."""
    keep_refs = {ref for item in triage_preview for ref in item["evidence_refs"]}
    payload = json.loads(canonical_bytes(context))
    for section in (
        "divergences",
        "pending_items",
        "classifications",
        "evidences",
        "state_history",
    ):
        items = payload.get(section, [])
        if not items:
            continue
        selected = [item for item in items if item.get("ref_id") in keep_refs]
        if not selected:
            selected = items[:1]
        if section == "evidences" and any(not item.get("available") for item in items):
            if not any(not item.get("available") for item in selected):
                unavailable = next(
                    item for item in items if not item.get("available")
                )
                selected.append(unavailable)
        payload[section] = selected
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def prepare_prompt(context: ExecutionAssistanceContext) -> tuple[str, dict, str, str]:
    # Verify the complete snapshot, but omit its volatile assembly timestamp
    # from model input so equivalent contexts have the same idempotency key.
    serialize_snapshot(context)
    canonical_bytes(context)
    request_schema = copy.deepcopy(SCHEMA)
    request_schema["properties"]["summary"]["enum"] = list(valid_summaries(context))
    request_schema["properties"]["human_checks"]["items"]["enum"] = list(
        HUMAN_CHECK_OPTIONS
    )
    all_refs = sorted(context.evidence_refs())
    triage_preview: list[dict] = (
        deterministic_triage_findings(context) if all_refs else []
    )
    if triage_preview:
        request_schema["$defs"]["Finding"] = {
            "title": "Finding",
            "anyOf": [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"const": item["title"]},
                        "explanation": {"const": item["explanation"]},
                        "evidence_refs": {"const": item["evidence_refs"]},
                    },
                    "required": ["title", "explanation", "evidence_refs"],
                }
                for item in triage_preview
            ],
        }
    else:
        request_schema["properties"]["findings"]["maxItems"] = 0
    limitations = required_limitations(context)
    limits_schema = request_schema["properties"]["limitations"]
    limits_schema["items"]["enum"] = limitations
    limits_schema["minItems"] = len(limitations)
    limits_schema["maxItems"] = len(limitations)
    limits_schema["uniqueItems"] = True
    schema_sha256 = hashlib.sha256(
        json.dumps(
            request_schema,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    prompt_hint = {
        "summary": request_schema["properties"]["summary"]["enum"],
        "human_checks": request_schema["properties"]["human_checks"]["items"]["enum"],
        "limitations": limitations,
        "findings_max": len(triage_preview),
    }
    compact_prompt_schema = json.dumps(
        prompt_hint, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    prompt_data = _compact_prompt_data(context, triage_preview)
    prompt = TEMPLATE.format(
        schema=compact_prompt_schema,
        data=prompt_data.decode(),
    )
    prompt_hash = hashlib.sha256(
        (SYSTEM + "\n" + prompt + "\n" + schema_sha256).encode()
    ).hexdigest()
    return prompt, request_schema, prompt_hash, schema_sha256


class AiAssistanceGenerator:
    def __init__(self, provider: AiModelProvider):
        self.provider = provider

    def generate(self, context: ExecutionAssistanceContext) -> GenerationResult:
        start = time.monotonic()
        prompt, request_schema, prompt_hash, schema_sha256 = prepare_prompt(context)
        response_hash = None
        state, origin, rejection = "ready", "model", None
        findings, checks = [], []
        summary, limitations = deterministic_fallback(context)
        if context.sufficiency == "insufficient":
            state, origin = "insufficient_evidence", "deterministic"
        else:
            try:
                with inference():
                    raw = self.provider.generate(SYSTEM, prompt, request_schema)
                if not isinstance(raw, bytes):
                    raise ProviderError("runtime_invalid_response")
                RESPONSE_BYTES.labels(environment()).observe(len(raw))
                response_hash = hashlib.sha256(raw).hexdigest()
                output = _decode(raw, context)
                summary, findings = (
                    output.summary,
                    [item.model_dump() for item in output.findings],
                )
                checks, limitations = output.human_checks, output.limitations
            except ProviderError as exc:
                known = {
                    "runtime_busy",
                    "runtime_timeout",
                    "runtime_unavailable",
                    "runtime_pin_mismatch",
                    "runtime_redirect",
                    "runtime_response_too_large",
                    "runtime_invalid_response",
                    "response_too_large",
                    "invalid_json",
                    "invalid_schema",
                    "invalid_reference",
                    "ungrounded_summary",
                    "ungrounded_finding",
                    "ungrounded_checks",
                    "ungrounded_limitations",
                    "missing_limitations",
                }
                rejection = exc.code if exc.code in known else "runtime_unavailable"
                state = (
                    "unavailable" if rejection.startswith("runtime_") else "rejected"
                )
                origin = "deterministic"
            except Exception as exc:
                _log_unexpected_exception(exc)
                state, origin, rejection = (
                    "unavailable",
                    "deterministic",
                    "runtime_unavailable",
                )
        elapsed = max(0, int((time.monotonic() - start) * 1000))
        outcome = {
            "ready": "generated",
            "insufficient_evidence": "insufficient",
            "rejected": "rejected",
        }.get(state, "timeout" if rejection == "runtime_timeout" else "unavailable")
        GENERATIONS.labels(environment(), origin, outcome, rejection or "none").inc()
        GENERATION_DURATION.labels(environment()).observe(elapsed / 1000)
        log_event(
            "ai.assistance.generator.finished",
            result=outcome,
            state=state,
            origin=origin,
            code=rejection or "none",
            duration=elapsed / 1000,
        )
        return GenerationResult(
            state,
            origin,
            plain_text(summary),
            findings,
            checks,
            limitations,
            rejection,
            context.context_sha256,
            prompt_hash,
            response_hash,
            schema_sha256,
            SCHEMA_SHA256,
            self.provider.model,
            self.provider.digest,
            elapsed,
        )
