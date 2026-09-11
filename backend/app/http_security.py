from __future__ import annotations

import os
from dataclasses import dataclass

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


@dataclass(frozen=True)
class HttpSecurityConfig:
    environment: str

    @property
    def production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_env(cls) -> HttpSecurityConfig:
        environment = os.getenv("SYNERGIA_ENV", "development").strip().lower()
        if environment not in {"development", "test", "homologation", "production"}:
            raise ValueError("SYNERGIA_ENV possui valor desconhecido")
        return cls(environment=environment)


class HttpSecurityMiddleware:
    """Apply the transport and browser baseline to every HTTP response."""

    def __init__(self, app: ASGIApp, config: HttpSecurityConfig) -> None:
        self.app = app
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        async def send_secure(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = API_CSP
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Permissions-Policy"] = (
                    "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
                )
                headers["Cross-Origin-Resource-Policy"] = "same-site"
                headers["Cache-Control"] = (
                    "no-cache" if path == "/health" else "no-store"
                )
                if self.config.production:
                    headers["Strict-Transport-Security"] = (
                        "max-age=31536000; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_secure)
