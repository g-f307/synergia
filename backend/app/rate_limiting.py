from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from typing import Final
from urllib.parse import parse_qs
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth.config import AuthConfig
from app.auth.security import TokenCodec

logger = logging.getLogger("synergia.rate_limit")


@dataclass(frozen=True)
class RatePolicy:
    operation: str
    limit: int
    window_seconds: int
    fail_closed: bool


DEFAULTS: Final[dict[str, tuple[int, int, bool]]] = {
    "login": (10, 60, True),
    "refresh": (30, 60, True),
    "upload": (20, 60, True),
    "search": (120, 60, True),
    "reprocess": (10, 300, True),
    "report_generate": (20, 300, True),
    "report_export": (60, 60, True),
    "decision": (30, 60, True),
}


def _positive_integer(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} deve ser um inteiro") from exc
    if value < 1:
        raise ValueError(f"{name} deve ser positivo")
    return value


def policies_from_env() -> dict[str, RatePolicy]:
    result = {}
    for operation, (limit, window, fail_closed) in DEFAULTS.items():
        prefix = f"RATE_LIMIT_{operation.upper()}"
        result[operation] = RatePolicy(
            operation,
            _positive_integer(f"{prefix}_LIMIT", limit),
            _positive_integer(f"{prefix}_WINDOW_SECONDS", window),
            fail_closed,
        )
    return result


def classify_operation(method: str, path: str) -> str | None:
    if method == "POST" and path == "/auth/login":
        return "login"
    if method == "POST" and path == "/auth/refresh":
        return "refresh"
    if method == "POST" and path == "/imports":
        return "upload"
    if method == "GET" and path == "/search":
        return "search"
    if method == "POST" and path.endswith("/reprocess"):
        return "reprocess"
    if method == "POST" and (path == "/reports" or path.endswith("/versions")):
        return "report_generate"
    if method == "GET" and path.startswith("/reports/") and path.endswith("/export"):
        return "report_export"
    if method == "POST" and (
        path.startswith("/approvals/")
        or (path.startswith("/pending-items/") and path.endswith("/approval"))
    ):
        return "decision"
    return None


class PostgresRateLimiter:
    def __init__(self, database_url: str, secret: str) -> None:
        self.database_url = database_url
        self.secret = secret.encode()

    def digest(self, value: str) -> str:
        return hmac.new(self.secret, value.encode(), hashlib.sha256).hexdigest()

    def refresh_subjects(self, token: str) -> list[tuple[str, str]]:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """
                SELECT s.user_id, rt.session_id
                FROM synergia.session_refresh_tokens rt
                JOIN synergia.identity_sessions s ON s.id = rt.session_id
                WHERE rt.token_hash = %s
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            return []
        return [("user", str(row[0])), ("session", str(row[1]))]

    def consume(
        self,
        policy: RatePolicy,
        dimension: str,
        value: str,
        correlation_id: UUID | None,
        method: str,
    ) -> int | None:
        key_hash = self.digest(value)
        now = datetime.now(UTC)
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            connection.execute(
                """
                DELETE FROM synergia.rate_limit_buckets
                WHERE updated_at < %s - interval '24 hours'
                """,
                (now,),
            )
            connection.execute(
                """
                DELETE FROM synergia.rate_limit_events
                WHERE occurred_at < %s - interval '30 days'
                """,
                (now,),
            )
            row = connection.execute(
                """
                INSERT INTO synergia.rate_limit_buckets (
                    operation, dimension, key_hash, window_started_at,
                    window_expires_at, request_count
                ) VALUES (%s, %s, %s, %s, %s + make_interval(secs => %s), 1)
                ON CONFLICT (operation, dimension, key_hash) DO UPDATE SET
                    window_started_at = CASE
                        WHEN synergia.rate_limit_buckets.window_expires_at <= %s
                        THEN %s ELSE synergia.rate_limit_buckets.window_started_at END,
                    window_expires_at = CASE
                        WHEN synergia.rate_limit_buckets.window_expires_at <= %s
                        THEN %s + make_interval(secs => %s)
                        ELSE synergia.rate_limit_buckets.window_expires_at END,
                    request_count = CASE
                        WHEN synergia.rate_limit_buckets.window_expires_at <= %s
                        THEN 1 ELSE synergia.rate_limit_buckets.request_count + 1 END,
                    updated_at = %s
                RETURNING request_count, window_expires_at
                """,
                (
                    policy.operation,
                    dimension,
                    key_hash,
                    now,
                    now,
                    policy.window_seconds,
                    now,
                    now,
                    now,
                    now,
                    policy.window_seconds,
                    now,
                    now,
                ),
            ).fetchone()
            assert row is not None
            if row["request_count"] <= policy.limit:
                return None
            retry_after = max(
                1, ceil((row["window_expires_at"] - now).total_seconds())
            )
            connection.execute(
                """
                UPDATE synergia.rate_limit_buckets
                SET denied_count = denied_count + 1, updated_at = %s
                WHERE operation = %s AND dimension = %s AND key_hash = %s
                """,
                (now, policy.operation, dimension, key_hash),
            )
            connection.execute(
                """
                INSERT INTO synergia.rate_limit_events (
                    operation, dimension, key_hash, retry_after_seconds,
                    correlation_id, method, route_group
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    policy.operation,
                    dimension,
                    key_hash,
                    retry_after,
                    correlation_id,
                    method,
                    policy.operation,
                ),
            )
            return retry_after


def _trusted_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    raw = os.getenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "")
    return tuple(
        ipaddress.ip_network(item.strip(), strict=False)
        for item in raw.split(",")
        if item.strip()
    )


def client_origin(scope: Scope, headers: Headers) -> str:
    peer = scope.get("client")
    peer_value = str(peer[0]) if peer else "unknown"
    try:
        peer_ip = ipaddress.ip_address(peer_value)
    except ValueError:
        return peer_value
    if not any(peer_ip in network for network in _trusted_networks()):
        return peer_value
    chain = headers.get("x-forwarded-for", "").split(",")
    parsed = []
    for item in chain:
        try:
            parsed.append(ipaddress.ip_address(item.strip()))
        except ValueError:
            return peer_value
    networks = _trusted_networks()
    for candidate in reversed(parsed):
        if not any(candidate in network for network in networks):
            return str(candidate)
    return peer_value


def _identity_dimensions(headers: Headers, operation: str) -> list[tuple[str, str]]:
    if operation == "refresh":
        cookie = headers.get("cookie", "")
        values = [
            part.split("=", 1)[1]
            for part in cookie.split(";")
            if part.strip().startswith("synergia_refresh=")
        ]
        return [("credential", values[0])] if values else []
    authorization = headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return []
    token = authorization.split(" ", 1)[1]
    try:
        claims = TokenCodec(AuthConfig.from_env()).decode_access(token)
    except Exception:
        return [("credential", token)]
    return [("user", str(claims.user_id)), ("session", str(claims.session_id))]


async def _login_body(
    receive: Receive,
) -> tuple[str | None, Receive] | tuple[None, None]:
    messages: list[Message] = []
    body = bytearray()
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] == "http.disconnect":
            return None, None
        body.extend(message.get("body", b""))
        if len(body) > 4096:
            return None, None
        if not message.get("more_body", False):
            break
    try:
        payload = json.loads(body)
        identifier = str(payload.get("email", "")).strip().casefold()
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        identifier = ""
    pending = iter(messages)

    async def replay() -> Message:
        try:
            return next(pending)
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    return identifier or None, replay


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        operation = classify_operation(scope["method"], scope["path"])
        disabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "false"
        if operation is None or disabled:
            await self.app(scope, receive, send)
            return
        database_url = os.getenv("DATABASE_URL")
        secret = os.getenv("RATE_LIMIT_KEY_SECRET") or os.getenv("AUTH_JWT_SIGNING_KEY")
        try:
            policy = policies_from_env()[operation]
        except ValueError:
            logger.error("rate_limit_configuration_invalid operation=%s", operation)
            await self._error(send, 503, "rate_limit_unavailable", 1)
            return
        if not database_url or not secret or len(secret.encode()) < 32:
            if policy.fail_closed and os.getenv("SYNERGIA_ENV") != "test":
                await self._error(send, 503, "rate_limit_unavailable", 1)
                return
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        dimensions = [("origin", client_origin(scope, headers))]
        dimensions.extend(_identity_dimensions(headers, operation))
        if operation == "login":
            identifier, replay = await _login_body(receive)
            if replay is None:
                await self._error(send, 413, "request_too_large", 1)
                return
            receive = replay
            if identifier:
                dimensions.append(("identifier", identifier))
        query = parse_qs(scope.get("query_string", b"").decode(errors="ignore"))
        organization = query.get("organization_id", [None])[0]
        if organization:
            dimensions.append(("organization", organization))
        limiter = PostgresRateLimiter(database_url, secret)
        try:
            if operation == "refresh":
                credential = next(
                    (value for key, value in dimensions if key == "credential"),
                    None,
                )
                if credential:
                    dimensions.extend(
                        await run_in_threadpool(limiter.refresh_subjects, credential)
                    )
            retries = []
            for dimension, value in dimensions:
                retries.append(
                    await run_in_threadpool(
                        limiter.consume,
                        policy,
                        dimension,
                        value,
                        scope.get("state", {}).get("correlation_id"),
                        scope["method"],
                    )
                )
        except (psycopg.Error, OSError) as exc:
            logger.error(
                "rate_limit_store_error operation=%s type=%s",
                operation,
                type(exc).__name__,
            )
            if policy.fail_closed:
                await self._error(send, 503, "rate_limit_unavailable", 1)
                return
            await self.app(scope, receive, send)
            return
        retry_after = max((item for item in retries if item is not None), default=None)
        if retry_after is not None:
            await self._error(send, 429, "rate_limit_exceeded", retry_after)
            return
        await self.app(scope, receive, send)

    @staticmethod
    async def _error(send: Send, status: int, code: str, retry_after: int) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": code,
                    "message": "Limite temporario de requisicoes atingido",
                    "details": {"retry_after_seconds": retry_after},
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"retry-after", str(retry_after).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
