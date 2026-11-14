"""Internal deterministic context builder. No model, prompt or business writes."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import psycopg
from prometheus_client import Counter, Histogram
from pydantic import ValidationError

from app.ai_assistance_context_models import (
    CONTEXT_VERSION,
    SECTIONS,
    ContextClassification,
    ContextCounts,
    ContextDivergence,
    ContextEvidence,
    ContextHistory,
    ContextPending,
    ContextSubject,
    ExecutionAssistanceContext,
)
from app.ai_assistance_context_policy import (
    ISSUE_CODES,
    LIFECYCLES,
    MEDIA_TYPES,
    RULE_IDS,
    normalized_text,
    vocabulary,
)
from app.ai_assistance_context_reader import ContextReader
from app.ai_assistance_contract import serialize_context
from app.ai_assistance_errors import assistance_error
from app.authorization import ActorContext
from app.errors import ApiError
from app.observability.metrics import REGISTRY

CONTEXTS = Counter(
    "synergia_ai_assistance_contexts",
    "Completed internal context builds.",
    ["sufficiency"],
    registry=REGISTRY,
)
CONTEXT_BYTES = Histogram(
    "synergia_ai_assistance_context_bytes",
    "Serialized context size in UTF-8 bytes.",
    buckets=(1024, 2048, 4096, 6144, 8192),
    registry=REGISTRY,
)
TRUNCATIONS = Counter(
    "synergia_ai_assistance_context_truncations",
    "Truncated context collections.",
    ["section"],
    registry=REGISTRY,
)
PREFIXES = dict(zip(SECTIONS, ("DIV", "PEN", "CLA", "EVI", "HIS"), strict=True))


def reference_id(section: str, execution_id: str, native_id: object) -> str:
    value = json.dumps([CONTEXT_VERSION, section, execution_id, str(native_id)])
    return PREFIXES[section] + "-" + hashlib.sha256(value.encode()).hexdigest()[:32]


def canonical_bytes(context: ExecutionAssistanceContext) -> bytes:
    return serialize_context(
        context.model_dump(
            mode="json",
            exclude={"generated_at", "context_sha256"},
        )
    )


def serialize_snapshot(context: ExecutionAssistanceContext) -> bytes:
    if hashlib.sha256(canonical_bytes(context)).hexdigest() != context.context_sha256:
        raise ValueError("context integrity check failed")
    return serialize_context(context.model_dump(mode="json"))


def _project(section: str, execution: str, row: dict):
    ref = reference_id(section, execution, row["id"])
    if section == "divergences":
        return ContextDivergence(
            ref_id=ref,
            severity=row["severity"],
            scope=row["scope"],
            code=vocabulary(row["code"], ISSUE_CODES),
            occurred_at=row["occurred_at"],
        )
    if section == "pending_items":
        return ContextPending(
            ref_id=ref,
            rule_id=vocabulary(row["rule_id"], RULE_IDS),
            status=row["status"],
            priority_score=row["priority_score"],
            created_at=row["created_at"],
        )
    if section == "classifications":
        return ContextClassification(
            ref_id=ref,
            rule_id=vocabulary(row["rule_id"], RULE_IDS),
            state=row["state"],
            data_quality=row["data_quality"],
            priority_score=row["priority_score"],
            classified_at=row["classified_at"],
        )
    if section == "evidences":
        extension = normalized_text(row["extension"], 4)
        extension = extension if extension in MEDIA_TYPES else "bin"
        return ContextEvidence(
            ref_id=ref,
            safe_name=f"evidence-{ref[4:]}.{extension}",
            evidence_type="source_file",
            media_type=MEDIA_TYPES[extension],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            available=row["available"],
        )
    return ContextHistory(
        ref_id=ref,
        from_state=row["from_state"],
        to_state=row["to_state"],
        state_version=row["state_version"],
        occurred_at=row["occurred_at"],
    )


def _sufficiency(items: dict) -> str:
    return (
        "sufficient"
        if (
            items["divergences"]
            or items["pending_items"]
            or items["classifications"]
            or any(item.available for item in items["evidences"])
        )
        else "insufficient"
    )


class ExecutionContextBuilder:
    def __init__(self, reader: ContextReader):
        self.reader = reader

    def build(
        self,
        actor: ActorContext,
        execution_id: UUID,
        *,
        generated_at: datetime | None = None,
    ) -> ExecutionAssistanceContext:
        if not actor.scopes_for("execution.read"):
            raise ApiError(403, "access_denied", "Acao nao autorizada")
        try:
            return self._build(actor, execution_id, generated_at or datetime.now(UTC))
        except ApiError:
            raise
        except psycopg.Error:
            raise ApiError(
                503, "ai_context_unavailable", "Contexto indisponível"
            ) from None
        except (ValidationError, ValueError, TypeError, KeyError):
            raise ApiError(
                422, "ai_context_invalid", "Contexto persistido inválido"
            ) from None

    def _build(self, actor, execution_id, generated_at):
        execution = str(execution_id)
        with self.reader.snapshot() as session:
            row = session.subject(execution, actor.scope_filter("execution.read"))
            if (
                row is None
                or row["organization_id"] is None
                or row["execution_id"] != execution
                or not actor.allows("execution.read", row["organization_id"])
            ):
                raise ApiError(404, "resource_not_found", "Recurso nao encontrado")
            lifecycle = LIFECYCLES.get(row["status"])
            if lifecycle is None:
                raise assistance_error("execution_active")
            # Explicit projection also protects tests/adapters returning extra keys.
            subject_fields = ContextSubject.model_fields
            subject = {key: row[key] for key in subject_fields}
            subject["execution_id"] = UUID(subject["execution_id"])
            for name in ("source", "pipeline_version", "rule_catalog_version"):
                subject[name] = normalized_text(subject[name])
            subject = ContextSubject.model_validate(subject)
            organization = subject.organization_id
            counts = ContextCounts.model_validate(
                session.counts(execution, organization)
            )
            items, truncated = {}, set()
            for section in SECTIONS:
                rows = session.items(section, execution, organization)
                limit = 10 if section == "state_history" else 20
                if len(rows) > limit:
                    truncated.add(section)
                items[section] = [
                    _project(section, execution, item) for item in rows[:limit]
                ]
        # No transaction is held during canonicalization or by future inference.
        while True:
            context = ExecutionAssistanceContext(
                contract_version=CONTEXT_VERSION,
                subject=subject,
                lifecycle=lifecycle,
                counts=counts,
                **items,
                sufficiency=_sufficiency(items),
                truncated_sections=[
                    section for section in SECTIONS if section in truncated
                ],
                generated_at=generated_at,
                context_sha256="0" * 64,
            )
            try:
                serialize_context(context.model_dump(mode="json"))
                break
            except ValueError:
                section = next((s for s in reversed(SECTIONS) if items[s]), None)
                if section is None:
                    raise ValueError("context metadata exceeds fixed budget") from None
                items[section].pop()
                truncated.add(section)
        digest = hashlib.sha256(canonical_bytes(context)).hexdigest()
        context = context.model_copy(update={"context_sha256": digest})
        serialized = serialize_snapshot(context)
        CONTEXTS.labels(context.sufficiency).inc()
        CONTEXT_BYTES.observe(len(serialized))
        for section in context.truncated_sections:
            TRUNCATIONS.labels(section).inc()
        return context
