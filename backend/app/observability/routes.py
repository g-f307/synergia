from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.errors import ApiError, ErrorResponse
from app.observability.config import ObservabilityConfig
from app.observability.health import complete_health, critical_health
from app.observability.metrics import record_dependency, render_metrics

router = APIRouter(tags=["system"])
metrics_bearer = HTTPBearer(auto_error=False, scheme_name="ObservabilityScrapeToken")


class ComponentHealthResponse(BaseModel):
    component: Literal["configuration", "postgresql", "storage", "email_worker"]
    status: Literal["healthy", "degraded", "unavailable", "disabled"]
    critical: bool
    duration_ms: float
    reason: Literal[
        "invalid_configuration",
        "not_configured",
        "probe_failed",
        "schema_unavailable",
        "state_unavailable",
        "queue_stalled",
    ] | None = None


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    service: str = "synergia-api"
    checked_at: datetime
    components: list[ComponentHealthResponse]


class LivenessResponse(BaseModel):
    status: Literal["alive"] = "alive"
    service: str = "synergia-api"
    checked_at: datetime


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    service: str = "synergia-api"
    checked_at: datetime
    components: list[ComponentHealthResponse]


def _now() -> datetime:
    return datetime.now(UTC)


def _configuration_failure() -> ComponentHealthResponse:
    record_dependency("configuration", "unavailable")
    return ComponentHealthResponse(
        component="configuration",
        status="unavailable",
        critical=True,
        duration_ms=0,
        reason="invalid_configuration",
    )


@router.get("/health/live", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    return LivenessResponse(checked_at=_now())


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={
        503: {"model": ReadinessResponse, "description": "Instância não pronta"}
    },
)
def readiness() -> Response:
    try:
        config = ObservabilityConfig.from_env()
    except ValueError:
        response = ReadinessResponse(
            status="not_ready",
            checked_at=_now(),
            components=[_configuration_failure()],
        )
        return Response(
            content=response.model_dump_json(),
            status_code=503,
            media_type="application/json",
        )
    checks = critical_health(config)
    ready = all(item.status == "healthy" for item in checks)
    response = ReadinessResponse(
        status="ready" if ready else "not_ready",
        checked_at=_now(),
        components=[
            ComponentHealthResponse.model_validate(item.public()) for item in checks
        ],
    )
    return Response(
        content=response.model_dump_json(),
        status_code=200 if ready else 503,
        media_type="application/json",
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Serviço indisponível"}},
)
def health() -> Response:
    try:
        config = ObservabilityConfig.from_env()
    except ValueError:
        response = HealthResponse(
            status="unhealthy",
            checked_at=_now(),
            components=[_configuration_failure()],
        )
        return Response(
            content=response.model_dump_json(),
            status_code=503,
            media_type="application/json",
        )
    checks = complete_health(config)
    if any(item.critical and item.status != "healthy" for item in checks):
        status = "unhealthy"
        status_code = 503
    elif any(item.status == "degraded" for item in checks):
        status = "degraded"
        status_code = 200
    else:
        status = "healthy"
        status_code = 200
    response = HealthResponse(
        status=status,
        checked_at=_now(),
        components=[
            ComponentHealthResponse.model_validate(item.public()) for item in checks
        ],
    )
    return Response(
        content=response.model_dump_json(),
        status_code=status_code,
        media_type="application/json",
    )


def require_metrics_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(metrics_bearer)
    ],
) -> ObservabilityConfig:
    try:
        config = ObservabilityConfig.from_env()
        config.validate_scrape_token()
    except ValueError as exc:
        raise ApiError(
            503, "observability_configuration_invalid", "Telemetria indisponivel"
        ) from exc
    supplied = credentials.credentials if credentials else ""
    if not hmac.compare_digest(supplied.encode(), config.scrape_token.encode()):
        raise ApiError(
            401,
            "invalid_observability_token",
            "Credencial tecnica invalida",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return config


@router.get(
    "/metrics",
    response_class=Response,
    responses={
        401: {"model": ErrorResponse, "description": "Credencial técnica inválida"},
        503: {"model": ErrorResponse, "description": "Telemetria não configurada"},
    },
)
def metrics(
    config: Annotated[ObservabilityConfig, Depends(require_metrics_token)],
) -> Response:
    complete_health(config)
    return Response(content=render_metrics(), media_type="text/plain; version=0.0.4")
