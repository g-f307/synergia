"""Authenticated, informative runtime probe, separate from API readiness."""

from __future__ import annotations

import os
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from app.ai_assistance_config import AiAssistanceConfig
from app.ai_assistance_contract import StrictContract
from app.ai_assistance_provider import LocalAiModelProvider, ProviderError
from app.errors import ErrorResponse
from app.observability.config import ObservabilityConfig
from app.observability.routes import require_metrics_token

router = APIRouter(tags=["system"])


class AiAssistanceHealth(StrictContract):
    status: Literal["disabled", "suspended", "healthy", "busy", "unavailable"]
    generation_enabled: bool
    duration_ms: int
    code: Literal[
        "disabled",
        "generation_disabled",
        "ok",
        "runtime_busy",
        "runtime_timeout",
        "runtime_unavailable",
        "runtime_pin_mismatch",
        "runtime_redirect",
        "runtime_response_too_large",
        "invalid_configuration",
    ]


def probe_assistance() -> AiAssistanceHealth:
    started = time.monotonic()
    enabled = False
    try:
        config = AiAssistanceConfig.from_environment(os.environ)
        enabled = config.enabled and config.generation_enabled
        if not config.enabled:
            status, code = "disabled", "disabled"
        elif not config.generation_enabled:
            status, code = "suspended", "generation_disabled"
        else:
            provider = LocalAiModelProvider(
                config,
                allowed_service=os.getenv("SYNERGIA_AI_ASSISTANCE_ALLOWED_SERVICE", ""),
            )
            provider.probe()
            status, code = "healthy", "ok"
    except ProviderError as exc:
        status = "busy" if exc.code == "runtime_busy" else "unavailable"
        code = (
            exc.code
            if exc.code
            in {
                "runtime_busy",
                "runtime_timeout",
                "runtime_unavailable",
                "runtime_pin_mismatch",
                "runtime_redirect",
                "runtime_response_too_large",
            }
            else "runtime_unavailable"
        )
    except ValueError:
        status, code = "unavailable", "invalid_configuration"
    except Exception:
        status, code = "unavailable", "runtime_unavailable"
    return AiAssistanceHealth(
        status=status,
        generation_enabled=enabled,
        duration_ms=max(0, int((time.monotonic() - started) * 1000)),
        code=code,
    )


@router.get(
    "/operations/ai-assistance/health",
    response_model=AiAssistanceHealth,
    responses={
        401: {"model": ErrorResponse, "description": "Credencial técnica inválida"},
        503: {"model": ErrorResponse, "description": "Observabilidade não configurada"},
    },
)
def assistance_health(
    _access: Annotated[ObservabilityConfig, Depends(require_metrics_token)],
) -> AiAssistanceHealth:
    # HTTP 200 means the informative check ran, not that inference is available.
    return probe_assistance()
