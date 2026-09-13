from __future__ import annotations

from time import perf_counter
from uuid import UUID, uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.telemetry import (
    bind_correlation_id,
    bind_execution_id,
    observe_http_request,
    reset_correlation_id,
    reset_execution_id,
)

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = MutableHeaders(scope=scope)
        supplied = headers.get(CORRELATION_HEADER)
        try:
            correlation_id = UUID(supplied) if supplied else uuid4()
        except ValueError:
            correlation_id = uuid4()
        scope.setdefault("state", {})["correlation_id"] = correlation_id
        correlation_token = bind_correlation_id(correlation_id)
        execution_token = bind_execution_id(None)
        started_at = perf_counter()
        status_code = 500

        async def send_with_correlation(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append(
                    CORRELATION_HEADER, str(correlation_id)
                )
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation)
        finally:
            route = scope.get("route")
            route_template = getattr(route, "path", "unmatched")
            observe_http_request(
                method=scope.get("method", "OTHER"),
                route=route_template,
                status_code=status_code,
                duration_seconds=perf_counter() - started_at,
            )
            reset_execution_id(execution_token)
            reset_correlation_id(correlation_token)
