"""Stable assistance failure taxonomy for the orchestration delivered in #189."""

from typing import Literal

from app.errors import ApiError

AssistanceFailure = Literal[
    "execution_active",
    "generation_in_progress",
    "invalid_contract",
    "disabled",
    "runtime_unavailable",
    "timeout",
]

FAILURES: dict[str, tuple[int, str]] = {
    "execution_active": (409, "A execução ainda está em andamento"),
    "generation_in_progress": (409, "Uma geração de assistência está em andamento"),
    "invalid_contract": (422, "Contrato de assistência inválido"),
    "disabled": (503, "A assistência está desabilitada"),
    "runtime_unavailable": (503, "A assistência está indisponível"),
    "timeout": (504, "O tempo limite da assistência foi excedido"),
}


def assistance_error(reason: AssistanceFailure) -> ApiError:
    status, message = FAILURES[reason]
    return ApiError(status, f"ai_assistance_{reason}", message)
