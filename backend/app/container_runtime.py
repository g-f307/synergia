from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from psycopg.conninfo import make_conninfo

POSTGRES_ENVIRONMENT_VARIABLES = (
    "PGHOST",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
)

DEPLOYMENT_ENVIRONMENTS = frozenset(
    {"development", "test", "homologation", "production"}
)
LOCAL_DEFAULTS = {
    "POSTGRES_PASSWORD": "synergia-local-only",
    "AUTH_JWT_SIGNING_KEY": "synergia-local-signing-key-change-me-119",
    "RATE_LIMIT_KEY_SECRET": "synergia-local-rate-limit-key-change-me",
}
LOCAL_LOGIN_MAX_DAYS = 90


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def _absolute_http_url(name: str, value: str, *, allow_local: bool) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{name} must be an absolute HTTP origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f"{name} must not contain credentials, query or fragment")
    if not allow_local and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(f"{name} must not use a local address outside development")


def _validate_homologation_login(environment: Mapping[str, str]) -> None:
    if not _enabled(environment.get("SYNERGIA_LOCAL_AUTH_ENABLED")):
        return
    raw = environment.get("AUTH_LOCAL_LOGIN_EXPIRES_AT", "").strip()
    try:
        expires_at = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            "AUTH_LOCAL_LOGIN_EXPIRES_AT must be an ISO 8601 date with timezone"
        ) from exc
    if expires_at.tzinfo is None:
        raise ValueError("AUTH_LOCAL_LOGIN_EXPIRES_AT must include a timezone")
    now = datetime.now(UTC)
    if expires_at <= now or expires_at > now + timedelta(days=LOCAL_LOGIN_MAX_DAYS):
        raise ValueError(
            "AUTH_LOCAL_LOGIN_EXPIRES_AT must be in the future and at most 90 days"
        )


def validate_deployment_environment(environment: Mapping[str, str]) -> str:
    """Fail before a container command runs with an unsafe deployment profile."""
    selected = environment.get("SYNERGIA_ENV", "").strip().lower()
    if selected not in DEPLOYMENT_ENVIRONMENTS:
        allowed = ", ".join(sorted(DEPLOYMENT_ENVIRONMENTS))
        raise ValueError(f"SYNERGIA_ENV must be explicit and one of: {allowed}")
    if selected in {"development", "test"}:
        return selected

    for name, local_default in LOCAL_DEFAULTS.items():
        value = environment.get(name, "").strip()
        if not value or value == local_default or value.upper().startswith("CHANGE_ME"):
            raise ValueError(f"{name} must be configured outside development")
    for name in ("AUTH_JWT_SIGNING_KEY", "RATE_LIMIT_KEY_SECRET"):
        if len(environment[name].encode()) < 32:
            raise ValueError(f"{name} must contain at least 32 bytes")

    origins = [
        item.strip()
        for item in environment.get("AUTH_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    ]
    if not origins:
        raise ValueError("AUTH_ALLOWED_ORIGINS must be configured")
    for origin in origins:
        _absolute_http_url("AUTH_ALLOWED_ORIGINS", origin, allow_local=False)
    _absolute_http_url(
        "SYNERGIA_API_ORIGIN",
        environment.get("SYNERGIA_API_ORIGIN", "").strip(),
        allow_local=False,
    )

    if selected == "homologation":
        _validate_homologation_login(environment)
    else:
        if _enabled(environment.get("SYNERGIA_LOCAL_AUTH_ENABLED")):
            raise ValueError("SYNERGIA_LOCAL_AUTH_ENABLED must be false in production")
        if not _enabled(environment.get("AUTH_REFRESH_COOKIE_SECURE")):
            raise ValueError("AUTH_REFRESH_COOKIE_SECURE must be true in production")
        if environment.get("AUTH_IDENTITY_PROVIDER", "").strip() != "corporate":
            raise ValueError("AUTH_IDENTITY_PROVIDER must be corporate in production")
        for name in (
            "AUTH_CORPORATE_ISSUER",
            "AUTH_CORPORATE_DISCOVERY_URL",
            "AUTH_CORPORATE_AUDIENCE",
            "AUTH_CORPORATE_CLIENT_ID",
        ):
            if not environment.get(name, "").strip():
                raise ValueError(f"{name} must be configured in production")
        for name in (
            "AUTH_CORPORATE_CLIENT_SECRET_FILE",
            "AUTH_CORPORATE_MAPPING_FILE",
        ):
            if not Path(environment.get(name, "").strip()).is_absolute():
                raise ValueError(f"{name} must be an absolute mounted path")
        if any(urlparse(origin).scheme != "https" for origin in origins):
            raise ValueError("AUTH_ALLOWED_ORIGINS must use HTTPS in production")
        if urlparse(environment["SYNERGIA_API_ORIGIN"]).scheme != "https":
            raise ValueError("SYNERGIA_API_ORIGIN must use HTTPS in production")

    return selected


def build_database_conninfo(environment: Mapping[str, str]) -> str:
    missing = [
        name
        for name in POSTGRES_ENVIRONMENT_VARIABLES
        if name not in environment
    ]
    if missing:
        raise ValueError(f"missing PostgreSQL settings: {', '.join(missing)}")
    return make_conninfo(
        host=environment["PGHOST"],
        port=environment["PGPORT"],
        dbname=environment["PGDATABASE"],
        user=environment["PGUSER"],
        password=environment["PGPASSWORD"],
    )
