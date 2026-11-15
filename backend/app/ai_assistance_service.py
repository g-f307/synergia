"""Application coordination for tenant-scoped assistance results."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from app.ai_assistance_contract import AiAssistanceResponse
from app.ai_assistance_generator import prepare_prompt
from app.ai_assistance_repository import AssistanceKey, AssistancePersistenceError
from app.authorization import ActorContext
from app.errors import ApiError


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
        raise ApiError(404, "ai_assistance_not_found", "Assistência não encontrada")
    return replace(actor, permissions={**actor.permissions, "execution.read": scopes})


class AiAssistanceService:
    def __init__(self, contexts, generator, repository):
        self.contexts = contexts
        self.generator = generator
        self.repository = repository

    def _context(self, actor: ActorContext, execution_id: UUID, action: str):
        restricted = _scoped_actor(actor, f"ai.assistance.{action}")
        try:
            return self.contexts.build(restricted, execution_id)
        except ApiError as exc:
            if exc.status_code == 404:
                raise ApiError(
                    404, "ai_assistance_not_found", "Assistência não encontrada"
                ) from None
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
        context = self._context(actor, execution_id, "generate")
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
            try:
                assistance_id = self.repository.reserve(
                    key, actor.user_id, actor.correlation_id
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
            generated = self.generator.generate(context)
            if generated.state == "unavailable":
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
                                "context_ms": 0,
                                "generation_ms": generated.elapsed_ms,
                                "total_ms": generated.elapsed_ms,
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
                elapsed_ms=generated.elapsed_ms,
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
