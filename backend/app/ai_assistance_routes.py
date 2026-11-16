"""HTTP adaptation for execution assistance."""

import asyncio
import json
import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.ai_assistance_config import AiAssistanceConfig
from app.ai_assistance_context import ExecutionContextBuilder
from app.ai_assistance_context_reader import PostgresContextReader
from app.ai_assistance_contract import AiAssistanceResponse
from app.ai_assistance_generator import AiAssistanceGenerator
from app.ai_assistance_limits import AssistanceLimits
from app.ai_assistance_provider import LocalAiModelProvider
from app.ai_assistance_repository import PostgresAiAssistanceRepository
from app.ai_assistance_service import AiAssistanceService
from app.authorization import AuthorizationRepo, CurrentActor
from app.errors import ApiError, ErrorResponse

router = APIRouter(tags=["ai-assistance"])
ASSISTANCE_TIMEOUT_SECONDS = 30


def enabled_config():
    try:
        config = AiAssistanceConfig.from_environment(os.environ)
    except ValueError:
        raise ApiError(
            503, "ai_assistance_disabled", "Assistência indisponível"
        ) from None
    if not config.enabled:
        raise ApiError(503, "ai_assistance_disabled", "Assistência indisponível")
    return config


def generation_config(
    config: Annotated[AiAssistanceConfig, Depends(enabled_config)],
):
    if not config.generation_enabled:
        raise ApiError(
            503, "ai_assistance_generation_disabled", "Geração temporariamente suspensa"
        )
    return config


def get_read_service(
    config: Annotated[AiAssistanceConfig, Depends(enabled_config)],
):
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise ApiError(
            503, "ai_assistance_runtime_unavailable", "Assistência indisponível"
        )
    return AiAssistanceService(
        ExecutionContextBuilder(PostgresContextReader(database_url)),
        None,
        PostgresAiAssistanceRepository(database_url, config.retention_days),
    )


def get_assistance_service(
    config: Annotated[AiAssistanceConfig, Depends(generation_config)],
):
    database_url = os.getenv("DATABASE_URL", "")
    secret = os.getenv("RATE_LIMIT_KEY_SECRET") or os.getenv("AUTH_JWT_SIGNING_KEY", "")
    try:
        if not database_url:
            raise ValueError("missing database")
        provider = LocalAiModelProvider(
            config,
            allowed_service=os.getenv("SYNERGIA_AI_ASSISTANCE_ALLOWED_SERVICE", ""),
        )
        return AiAssistanceService(
            ExecutionContextBuilder(PostgresContextReader(database_url)),
            AiAssistanceGenerator(provider),
            PostgresAiAssistanceRepository(database_url, config.retention_days),
            AssistanceLimits(database_url, secret),
        )
    except ValueError:
        raise ApiError(
            503, "ai_assistance_runtime_unavailable", "Assistência indisponível"
        ) from None


async def empty_body(request: Request):
    raw = await request.body()
    if not raw:
        return
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        value = None
    if type(value) is not dict or value:
        raise ApiError(422, "ai_assistance_invalid_contract", "Contrato inválido")


RESPONSES = {
    status: {"model": ErrorResponse, "description": description}
    for status, description in {
        401: "Sessão inválida",
        403: "Sem permissão",
        404: "Não encontrado",
        409: "Execução ativa ou geração em andamento",
        422: "Corpo inválido",
        429: "Limite de solicitações",
        500: "Resultado persistido inválido",
        503: "Assistência indisponível",
        504: "Tempo limite",
    }.items()
}


def _call(operation, actor, execution_id, audit, request, permission):
    try:
        return operation(actor, execution_id)
    except ApiError as exc:
        if exc.status_code == 403 or getattr(exc, "audit_denial", False):
            try:
                audit.audit_denial(actor, permission, request)
            except Exception:
                raise ApiError(
                    503, "ai_assistance_runtime_unavailable", "Assistência indisponível"
                ) from None
        raise
    except Exception:
        # Never expose provider, database, or serializer details at this boundary.
        raise ApiError(
            503, "ai_assistance_runtime_unavailable", "Assistência indisponível"
        ) from None


@router.post(
    "/executions/{execution_id}/ai-assistance",
    response_model=AiAssistanceResponse,
    responses=RESPONSES,
    openapi_extra={
        "requestBody": {
            "required": False,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/AiAssistanceRequest"}
                }
            },
        }
    },
)
async def generate_assistance(
    execution_id: UUID,
    request: Request,
    config: Annotated[AiAssistanceConfig, Depends(generation_config)],
    actor: CurrentActor,
    audit: AuthorizationRepo,
    service: Annotated[AiAssistanceService, Depends(get_assistance_service)],
    body: Annotated[None, Depends(empty_body)],
):
    try:
        return await asyncio.wait_for(
            run_in_threadpool(
                _call,
                service.generate,
                actor,
                execution_id,
                audit,
                request,
                "ai.assistance.generate",
            ),
            timeout=ASSISTANCE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise ApiError(504, "ai_assistance_timeout", "Tempo limite excedido") from None


@router.get(
    "/executions/{execution_id}/ai-assistance/latest",
    response_model=AiAssistanceResponse,
    responses=RESPONSES,
)
def latest_assistance(
    execution_id: UUID,
    request: Request,
    config: Annotated[AiAssistanceConfig, Depends(enabled_config)],
    actor: CurrentActor,
    audit: AuthorizationRepo,
    service: Annotated[AiAssistanceService, Depends(get_read_service)],
):
    return _call(
        service.latest, actor, execution_id, audit, request, "ai.assistance.read"
    )
