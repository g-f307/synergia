"""Application coordination for tenant-scoped assistance results."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from app.ai_assistance_contract import AiAssistanceResponse
from app.ai_assistance_generator import prepare_prompt
from app.ai_assistance_repository import AssistanceKey, AssistancePersistenceError
from app.authorization import ActorContext
from app.errors import ApiError


def _not_found_for_scope():
    error = ApiError(404, "ai_assistance_not_found", "Assistência não encontrada")
    error.audit_denial = True
    return error


def _scoped_actor(actor: ActorContext, permission: str) -> ActorContext:
    """Restrict the context reader to the intersection of both permissions."""
    execution = actor.scopes_for("execution.read")
    assistance = actor.scopes_for(permission)
    if not execution or not assistance:
        raise ApiError(403, "access_denied", "Acao nao autorizada")
    if None in execution:
        scopes = assistance
    elif None in assistance:
        scopes = execution
    else:
        scopes = execution & assistance
    if not scopes:
        raise _not_found_for_scope()
    return replace(actor, permissions={**actor.permissions, "execution.read": scopes})


class AiAssistanceService:
    def __init__(self, contexts, generator, repository, limits=None):
        self.contexts = contexts
        self.generator = generator
        self.repository = repository
        self.limits = limits

    def _context(self, actor: ActorContext, execution_id: UUID, action: str):
        restricted = _scoped_actor(actor, f"ai.assistance.{action}")
        try:
            return self.contexts.build(restricted, execution_id)
        except ApiError as exc:
            if exc.status_code == 404:
                raise _not_found_for_scope() from None
            if exc.code == "ai_assistance_execution_active":
                raise ApiError(
                    409,
                    "ai_assistance_execution_not_terminal",
                    "A execução ainda está em andamento",
                ) from None
            raise

    def latest(self, actor: ActorContext, execution_id: UUID):
        context = self._context(actor, execution_id, "read")
        try:
            result = self.repository.latest(
                context.subject.organization_id,
                execution_id,
                context.context_sha256,
                actor.user_id,
                actor.correlation_id,
                evidence_refs=context.evidence_refs(),
            )
        except AssistancePersistenceError as exc:
            self._persistence_error(exc)
        if result is None:
            raise ApiError(404, "ai_assistance_not_found", "Assistência não encontrada")
        return result

    def generate(self, actor: ActorContext, execution_id: UUID):
        if self.generator is None:
            raise ApiError(
                503,
                "ai_assistance_generation_disabled",
                "Geração temporariamente suspensa",
            )
        started = time.monotonic()
        context = self._context(actor, execution_id, "generate")
        context_ms = int((time.monotonic() - started) * 1000)
        return self._generate(actor, execution_id, context, started, context_ms)

    def _generate(self, actor, execution_id, context, started, context_ms):
        _, _, prompt_hash, _ = prepare_prompt(context)
        key = AssistanceKey(
            context.subject.organization_id,
            execution_id,
            context.context_sha256,
            prompt_hash,
            self.generator.provider.model,
            self.generator.provider.digest,
        )
        refs = context.evidence_refs()
        try:
            existing = self.repository.find(
                key, actor.user_id, actor.correlation_id, evidence_refs=refs
            )
            if existing is not None:
                return existing
            if self.limits is not None:
                self.limits.consume(actor, key.organization_id)
            try:
                assistance_id = self.repository.reserve(
                    key, actor.user_id, actor.correlation_id, enforce_inflight=True
                )
            except AssistancePersistenceError as exc:
                if str(exc) != "conflict_or_not_found":
                    raise
                # The other request may have completed since the lookup.
                existing = self.repository.find(
                    key, actor.user_id, actor.correlation_id, evidence_refs=refs
                )
                if existing is not None:
                    return existing
                raise ApiError(
                    409, "ai_assistance_in_progress", "Geração em andamento"
                ) from None
            remaining = 30 - (time.monotonic() - started)
            if remaining <= 1:
                self.repository.abandon(
                    key,
                    assistance_id,
                    actor.user_id,
                    actor.correlation_id,
                    "runtime_timeout",
                )
                raise ApiError(504, "ai_assistance_timeout", "Tempo limite excedido")
            if hasattr(self.generator.provider, "timeout_seconds"):
                self.generator.provider.timeout_seconds = remaining
            generated = self.generator.generate(context)
            if generated.state == "unavailable":
                self.repository.abandon(
                    key,
                    assistance_id,
                    actor.user_id,
                    actor.correlation_id,
                    generated.rejection_code,
                )
                if generated.rejection_code == "runtime_timeout":
                    raise ApiError(
                        504, "ai_assistance_timeout", "Tempo limite excedido"
                    )
                if generated.rejection_code == "runtime_busy":
                    raise ApiError(
                        409, "ai_assistance_in_progress", "Geração em andamento"
                    )
                raise ApiError(
                    503, "ai_assistance_runtime_unavailable", "Assistência indisponível"
                )
            if generated.prompt_sha256 != key.prompt_sha256:
                raise AssistancePersistenceError("integrity_error")
            total_ms = int((time.monotonic() - started) * 1000)
            if total_ms > 30000:
                self.repository.abandon(
                    key,
                    assistance_id,
                    actor.user_id,
                    actor.correlation_id,
                    "runtime_timeout",
                )
                raise ApiError(504, "ai_assistance_timeout", "Tempo limite excedido")
            response = AiAssistanceResponse.model_validate_json(
                json.dumps(
                    {
                        "assistance_id": str(assistance_id),
                        "execution_id": str(execution_id),
                        "state": generated.state,
                        "summary": generated.summary,
                        "findings": generated.findings,
                        "human_checks": generated.human_checks,
                        "limitations": generated.limitations,
                        "provenance": {
                            "contract_version": key.contract_version,
                            "model": key.model_name,
                            "digest": key.model_digest,
                            "context_hash": key.context_sha256,
                            "prompt_hash": key.prompt_sha256,
                            "origin": generated.origin,
                            "timings": {
                                "context_ms": context_ms,
                                "generation_ms": generated.elapsed_ms,
                                "total_ms": total_ms,
                            },
                        },
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                ),
                context={"evidence_refs": refs},
            )
            return self.repository.finish(
                key,
                assistance_id,
                actor.user_id,
                actor.correlation_id,
                response,
                evidence_refs=refs,
                response_sha256=generated.response_sha256,
                rejection_code=generated.rejection_code,
                elapsed_ms=total_ms,
            )
        except AssistancePersistenceError as exc:
            self._persistence_error(exc)

    @staticmethod
    def _persistence_error(exc: AssistancePersistenceError):
        if str(exc) == "integrity_error":
            raise ApiError(
                500, "ai_assistance_integrity_error", "Assistência inválida"
            ) from None
        raise ApiError(
            503, "ai_assistance_runtime_unavailable", "Assistência indisponível"
        ) from None
