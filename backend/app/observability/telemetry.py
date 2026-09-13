from __future__ import annotations

import json
import logging
import os
import re
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

SERVICE_NAME = "synergia-api"
EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{1,95}$")
_correlation_id: ContextVar[str | None] = ContextVar(
    "synergia_correlation_id", default=None
)
_execution_id: ContextVar[str | None] = ContextVar(
    "synergia_execution_id", default=None
)

SAFE_FIELDS = frozenset(
    {
        "attempt",
        "component",
        "confirmed_count",
        "correlation_id",
        "decision",
        "delivery_count",
        "dimension",
        "duration_ms",
        "error_code",
        "exception_type",
        "execution_id",
        "failed_count",
        "file_count",
        "level",
        "method",
        "operation",
        "outcome",
        "processed_count",
        "reason_code",
        "rejected_count",
        "route",
        "service",
        "source",
        "status_code",
        "timestamp",
    }
)


def _scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, UUID):
        return str(value)
    return type(value).__name__


class SafeJsonFormatter(logging.Formatter):
    """Render allowlisted operational fields without exception text or locals."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": SERVICE_NAME,
            "event": (
                record.getMessage()
                if EVENT_PATTERN.fullmatch(record.getMessage())
                else "telemetry.invalid_event"
            ),
        }
        event_data = getattr(record, "synergia_fields", {})
        if isinstance(event_data, dict):
            for key, value in event_data.items():
                if key in SAFE_FIELDS and key not in {"level", "service", "timestamp"}:
                    payload[key] = _scalar(value)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    """Install one JSON handler and replace Uvicorn's raw URL access log."""
    logger = logging.getLogger("synergia")
    if not any(
        getattr(handler, "synergia_handler", False) for handler in logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.setFormatter(SafeJsonFormatter())
        handler.synergia_handler = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    level = os.getenv("OBSERVABILITY_LOG_LEVEL", "INFO").strip().upper()
    logger.setLevel(level if level in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO")
    logger.propagate = False
    logging.getLogger("uvicorn.access").disabled = True


def bind_correlation_id(value: UUID | str) -> Token:
    return _correlation_id.set(str(value))


def reset_correlation_id(token: Token) -> None:
    _correlation_id.reset(token)


def bind_execution_id(value: str | None) -> Token:
    if value is None:
        return _execution_id.set(None)
    try:
        normalized = str(UUID(value))
    except ValueError:
        normalized = None
    return _execution_id.set(normalized)


def reset_execution_id(token: Token) -> None:
    _execution_id.reset(token)


def current_correlation_id() -> UUID | None:
    value = _correlation_id.get()
    return UUID(value) if value else None


def safe_log(level: int, event: str, **fields: Any) -> None:
    data = {key: value for key, value in fields.items() if key in SAFE_FIELDS}
    correlation_id = _correlation_id.get()
    execution_id = _execution_id.get()
    if correlation_id and "correlation_id" not in data:
        data["correlation_id"] = correlation_id
    if execution_id and "execution_id" not in data:
        data["execution_id"] = execution_id
    logging.getLogger("synergia.telemetry").log(
        level,
        event,
        extra={"synergia_fields": data},
    )


def observe_http_request(
    *, method: str, route: str, status_code: int, duration_seconds: float
) -> None:
    from app.observability.metrics import observe_http_request as observe_metric

    observe_metric(method, route, status_code, duration_seconds)
    level = (
        logging.ERROR
        if status_code >= 500
        else logging.WARNING
        if status_code >= 400
        else logging.INFO
    )
    safe_log(
        level,
        "http.request.completed",
        method=method,
        route=route,
        status_code=status_code,
        duration_ms=round(duration_seconds * 1000, 3),
        outcome="success" if status_code < 400 else "failure",
    )
