"""Reusable organization-bound access guards; no assistance data queries."""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Request

from app.ai_assistance_config import AiAssistanceConfig
from app.ai_assistance_contract import StrictContract
from app.authorization import ActorContext, AuthorizationRepo, CurrentActor
from app.errors import ApiError, ErrorResponse

router = APIRouter(tags=["ai-assistance"])


def shared_scope(actor: ActorContext, permission: str) -> bool:
    execution = actor.scopes_for("execution.read")
    assistance = actor.scopes_for(permission)
    return bool(execution and assistance) and (
        None in execution or None in assistance or bool(execution & assistance)
    )


def require_assistance_permission(action: Literal["read", "generate"]):
    if action not in {"read", "generate"}:
        raise ValueError("unsupported assistance action")
    permission = f"ai.assistance.{action}"

    def dependency(
        execution_id: str,
        request: Request,
        actor: CurrentActor,
        repository: AuthorizationRepo,
    ) -> ActorContext:
        for required in ("execution.read", permission):
            if not actor.scopes_for(required):
                repository.audit_denial(actor, required, request)
                raise ApiError(403, "access_denied", "Acao nao autorizada")
        organization = repository.execution_organization(execution_id)
        if organization is None or not all(
            actor.allows(required, organization)
            for required in ("execution.read", permission)
        ):
            # Same response for invisible and absent resources; no foreign scope
            # or execution metadata is exposed to the caller.
            repository.audit_denial(actor, permission, request)
            raise ApiError(404, "resource_not_found", "Recurso nao encontrado")
        return actor

    return dependency


class AiAssistanceCapability(StrictContract):
    enabled: bool
    read: bool
    generate: bool


@router.get(
    "/me/ai-assistance-capability",
    response_model=AiAssistanceCapability,
    responses={
        403: {"model": ErrorResponse, "description": "Sem permissão de assistência"}
    },
)
def assistance_capability(actor: CurrentActor) -> AiAssistanceCapability:
    read = shared_scope(actor, "ai.assistance.read")
    generate = shared_scope(actor, "ai.assistance.generate")
    if not read and not generate:
        raise ApiError(403, "access_denied", "Acao nao autorizada")
    enabled = AiAssistanceConfig.from_environment(os.environ).enabled
    return AiAssistanceCapability(
        enabled=enabled,
        read=enabled and read,
        generate=enabled and generate,
    )
