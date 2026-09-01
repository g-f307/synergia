from __future__ import annotations

import os
from dataclasses import dataclass

from app.errors import ApiError

NON_PRODUCTION_ENVIRONMENTS = frozenset({"development", "test", "homologation"})
DEFAULT_ALLOWED_ORIGINS = "http://localhost:4200"


def _boolean(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes"}


def _integer(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ApiError(
            503, "auth_configuration_invalid", "Autenticacao indisponivel"
        ) from exc
    if value < minimum:
        raise ApiError(503, "auth_configuration_invalid", "Autenticacao indisponivel")
    return value


def configured_allowed_origins() -> tuple[str, ...]:
    origins = tuple(
        item.strip()
        for item in os.getenv(
            "AUTH_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS
        ).split(",")
        if item.strip()
    )
    if not origins:
        raise ValueError("AUTH_ALLOWED_ORIGINS deve possuir ao menos uma origem")
    return origins


@dataclass(frozen=True)
class AuthConfig:
    environment: str
    local_auth_enabled: bool
    signing_key: str
    issuer: str
    audience: str
    algorithm: str = "HS256"
    access_minutes: int = 15
    refresh_idle_hours: int = 8
    refresh_absolute_hours: int = 24
    clock_skew_seconds: int = 30
    cookie_name: str = "synergia_refresh"
    cookie_secure: bool = True
    allowed_origins: tuple[str, ...] = ("http://localhost:4200",)
    login_max_attempts: int = 5
    login_window_seconds: int = 900
    login_block_seconds: int = 900

    @classmethod
    def from_env(cls) -> AuthConfig:
        environment = os.getenv("SYNERGIA_ENV", "").strip().lower()
        local_enabled = _boolean("SYNERGIA_LOCAL_AUTH_ENABLED")
        if local_enabled and environment not in NON_PRODUCTION_ENVIRONMENTS:
            local_enabled = False

        algorithm = os.getenv("AUTH_JWT_ALGORITHM", "HS256").strip()
        signing_key = os.getenv("AUTH_JWT_SIGNING_KEY", "")
        issuer = os.getenv("AUTH_JWT_ISSUER", "").strip()
        audience = os.getenv("AUTH_JWT_AUDIENCE", "").strip()
        invalid_crypto = (
            algorithm != "HS256"
            or len(signing_key.encode()) < 32
            or not issuer
            or not audience
        )
        if invalid_crypto:
            raise ApiError(
                503, "auth_configuration_invalid", "Autenticacao indisponivel"
            )

        try:
            origins = configured_allowed_origins()
        except ValueError as exc:
            raise ApiError(
                503, "auth_configuration_invalid", "Autenticacao indisponivel"
            ) from exc

        cookie_secure = _boolean("AUTH_REFRESH_COOKIE_SECURE", True)
        if environment == "production" and not cookie_secure:
            raise ApiError(
                503, "auth_configuration_invalid", "Autenticacao indisponivel"
            )

        access_minutes = _integer("AUTH_ACCESS_TOKEN_MINUTES", 15, 1)
        idle_hours = _integer("AUTH_REFRESH_IDLE_HOURS", 8, 1)
        absolute_hours = _integer("AUTH_REFRESH_ABSOLUTE_HOURS", 24, 1)
        if absolute_hours < idle_hours:
            raise ApiError(
                503, "auth_configuration_invalid", "Autenticacao indisponivel"
            )
        if environment == "production" and (
            access_minutes != 15 or idle_hours != 8 or absolute_hours != 24
        ):
            raise ApiError(
                503, "auth_configuration_invalid", "Autenticacao indisponivel"
            )

        return cls(
            environment=environment,
            local_auth_enabled=local_enabled,
            signing_key=signing_key,
            issuer=issuer,
            audience=audience,
            algorithm=algorithm,
            access_minutes=access_minutes,
            refresh_idle_hours=idle_hours,
            refresh_absolute_hours=absolute_hours,
            clock_skew_seconds=_integer("AUTH_CLOCK_SKEW_SECONDS", 30, 0),
            cookie_secure=cookie_secure,
            allowed_origins=origins,
            login_max_attempts=_integer("AUTH_LOGIN_MAX_ATTEMPTS", 5, 1),
            login_window_seconds=_integer("AUTH_LOGIN_WINDOW_SECONDS", 900, 1),
            login_block_seconds=_integer("AUTH_LOGIN_BLOCK_SECONDS", 900, 1),
        )
