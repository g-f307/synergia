"""Internal generation boundary. Model text is accepted only from a grounded catalog."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from prometheus_client import Counter, Histogram
from pydantic import AfterValidator, Field, ValidationError

from app.ai_assistance_context import serialize_snapshot
from app.ai_assistance_context_models import ExecutionAssistanceContext
from app.ai_assistance_contract import StrictContract, plain_text
from app.ai_assistance_fallback import deterministic_fallback, required_limitations
from app.ai_assistance_provider import AiModelProvider, ProviderError
from app.observability.metrics import REGISTRY

_ASSETS = Path(__file__).parent / "ai_assistance_assets"
SYSTEM = (_ASSETS / "system.txt").read_text(encoding="utf-8")
TEMPLATE = (_ASSETS / "template.txt").read_text(encoding="utf-8")
SYSTEM_SHA256 = hashlib.sha256(SYSTEM.encode()).hexdigest()
TEMPLATE_SHA256 = hashlib.sha256(TEMPLATE.encode()).hexdigest()
OUTCOMES = Counter(
    "synergia_ai_assistance_generations",
    "Assistance generation outcomes.",
    ["origin", "state", "rejection"],
    registry=REGISTRY,
)
DURATION = Histogram(
    "synergia_ai_assistance_generation_seconds",
    "Assistance generation duration.",
    registry=REGISTRY,
)


def _log_unexpected_exception(exc: Exception) -> None:
    """Log frame locations and type, never exception text, source lines or locals."""
    frames = []
    traceback = exc.__traceback__
    while traceback is not None and len(frames) < 32:
        code = traceback.tb_frame.f_code
        filename = Path(code.co_filename).name
        function = code.co_name
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", filename):
            filename = "unknown"
        if not re.fullmatch(r"[A-Za-z0-9_.<>-]{1,128}", function):
            function = "unknown"
        frames.append(f"{filename}:{traceback.tb_lineno}:{function}")
        traceback = traceback.tb_next
    exception_type = type(exc).__name__
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", exception_type):
        exception_type = "Exception"
    logging.getLogger("synergia.telemetry").error(
        "ai.assistance.unexpected_error",
        extra={
            "synergia_fields": {
                "exception_type": exception_type,
                "stack_trace": " | ".join(frames),
                "error_code": "internal_error",
            }
        },
    )


def validate_language(value: str) -> str:
    """Lexical policy check; grounding is enforced separately below."""
    plain_text(value)
    normalized = "".join(
        c
        for c in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(c)
    )
    if re.search(
        r"\b(select|from|where|join|drop|truncate|create|alter|grant|revoke|"
        r"union|having|values|sql|causa|causou|causada|causado|"
        r"devido a|em decorrencia|decidiu|determinou|decisao automatica|"
        r"sistema decidiu|system decided|caused by|root cause)\b",
        normalized,
    ) or re.search(r"[;]|--|/\*|\*/|\$\(|\|\|", value):
        raise ValueError("prohibited language")
    return value


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
    counts = context.counts
    errors = "erro" if counts.errors == 1 else "erros"
    warnings = "aviso" if counts.warnings == 1 else "avisos"
    pending = "pendência" if counts.pending_items == 1 else "pendências"
    summaries = (
        f"A execução registra {counts.errors} erros, {counts.warnings} avisos e "
        f"{counts.pending_items} pendências.",
        f"A execução registra {counts.errors} {errors}, {counts.warnings} {warnings} e "
        f"{counts.pending_items} {pending}.",
        f"Foram registrados {counts.errors} {errors}, {counts.warnings} {warnings} e "
        f"{counts.pending_items} {pending}.",
        f"Foram registrados {counts.errors} erros, {counts.warnings} avisos e "
        f"{counts.pending_items} pendências.",
    )
    if output.summary not in summaries:
        raise ProviderError("ungrounded_summary")
    refs = context.evidence_refs()
    prefixes = {
        "DIV": "Divergência registrada",
        "PEN": "Pendência registrada",
        "CLA": "Classificação registrada",
        "EVI": "Evidência registrada",
        "HIS": "Transição registrada",
    }
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
        valid_titles = {"Registros disponíveis", "Registros para conferência"}
        if len(selected) == 1:
            valid_titles.add(prefixes[selected[0][:3]])
        elif len({ref[:3] for ref in selected}) == 1:
            valid_titles.add(prefixes[selected[0][:3]])
        if (
            finding.title not in valid_titles
            or finding.explanation
            not in {
                "Há um registro disponível para conferência.",
                "Há registros disponíveis para conferência.",
                "Os registros estão disponíveis para conferência.",
            }
            or (
                len(selected) > 1
                and finding.explanation == "Há um registro disponível para conferência."
            )
        ):
            raise ProviderError("ungrounded_finding")
    if any(
        check
        not in {
            "Conferência humana das referências disponíveis.",
            "Conferência humana das evidências disponíveis.",
        }
        for check in output.human_checks
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


class AiAssistanceGenerator:
    def __init__(self, provider: AiModelProvider):
        self.provider = provider

    def generate(self, context: ExecutionAssistanceContext) -> GenerationResult:
        start = time.monotonic()
        # This also verifies the canonical context hash and size before any model call.
        snapshot = serialize_snapshot(context)
        request_schema = copy.deepcopy(SCHEMA)
        limitations = required_limitations(context)
        limits_schema = request_schema["properties"]["limitations"]
        limits_schema["items"]["enum"] = limitations
        limits_schema["minItems"] = len(limitations)
        limits_schema["maxItems"] = len(limitations)
        limits_schema["uniqueItems"] = True
        prompt = TEMPLATE.format(
            schema=json.dumps(request_schema, ensure_ascii=False, sort_keys=True),
            data=snapshot.decode(),
        )
        prompt_hash = hashlib.sha256((SYSTEM + "\n" + prompt).encode()).hexdigest()
        response_hash = None
        state, origin, rejection = "ready", "model", None
        findings, checks = [], []
        summary, limitations = deterministic_fallback(context)
        if context.sufficiency == "insufficient":
            state, origin = "insufficient_evidence", "deterministic"
        else:
            try:
                raw = self.provider.generate(SYSTEM, prompt, request_schema)
                if not isinstance(raw, bytes):
                    raise ProviderError("runtime_invalid_response")
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
        OUTCOMES.labels(origin, state, rejection or "none").inc()
        DURATION.observe(elapsed / 1000)
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
            SCHEMA_SHA256,
            self.provider.model,
            self.provider.digest,
            elapsed,
        )
