from __future__ import annotations

from uuid import UUID, uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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

        async def send_with_correlation(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append(
                    CORRELATION_HEADER, str(correlation_id)
                )
            await send(message)

        await self.app(scope, receive, send_with_correlation)
