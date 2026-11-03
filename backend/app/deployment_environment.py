from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

DEPLOYMENT_ENVIRONMENTS = frozenset(
    {"development", "test", "homologation", "production"}
)
LOCAL_DEFAULTS = {
    "PGPASSWORD": "synergia-local-only",
    "AUTH_JWT_SIGNING_KEY": "synergia-local-signing-key-change-me-119",
    "RATE_LIMIT_KEY_SECRET": "synergia-local-rate-limit-key-change-me",
}
LOCAL_LOGIN_MAX_DAYS = 90
HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def _valid_hostname(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if len(hostname) > 253:
            return False
        return all(HOST_LABEL.fullmatch(label) for label in hostname.split("."))
    return True


def _absolute_http_url(name: str, value: str, *, allow_local: bool) -> None:
    if "CHANGE_ME" in value.upper():
        raise ValueError(f"{name} must not contain an unedited placeholder")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{name} must be an absolute HTTP origin")
    if not _valid_hostname(parsed.hostname):
        raise ValueError(f"{name} must contain a valid hostname without wildcards")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{name} must contain a valid numeric port") from exc
    if port == 0:
        raise ValueError(f"{name} must contain a port between 1 and 65535")
    if (
        parsed.username
        or parsed.password
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            f"{name} must not contain credentials, path, query or fragment"
        )
    if not allow_local and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(f"{name} must not use a local address outside development")


def _corporate_https_endpoint(name: str, value: str) -> str:
    if "CHANGE_ME" in value.upper():
        raise ValueError(f"{name} must not contain an unedited placeholder")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"{name} must be an absolute HTTPS URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{name} must contain a valid numeric port") from exc
    if port == 0 or not _valid_hostname(parsed.hostname):
        raise ValueError(f"{name} must contain a valid hostname and port")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(f"{name} must not contain credentials, query or fragment")
    return parsed.hostname


def _validate_authentication_contract(
    environment: Mapping[str, str], selected: str
) -> None:
    if environment.get("AUTH_JWT_ALGORITHM", "HS256").strip() != "HS256":
        raise ValueError("AUTH_JWT_ALGORITHM must be HS256")

    provider = environment.get("AUTH_IDENTITY_PROVIDER", "local").strip().lower()
    if provider not in {"local", "corporate"}:
        raise ValueError(
            "AUTH_IDENTITY_PROVIDER must be local or corporate outside offline tests"
        )
    if selected == "production" and provider != "corporate":
        raise ValueError("AUTH_IDENTITY_PROVIDER must be corporate in production")
    if provider != "corporate":
        return

    issuer_host = _corporate_https_endpoint(
        "AUTH_CORPORATE_ISSUER",
        environment.get("AUTH_CORPORATE_ISSUER", "").strip(),
    )
    discovery_host = _corporate_https_endpoint(
        "AUTH_CORPORATE_DISCOVERY_URL",
        environment.get("AUTH_CORPORATE_DISCOVERY_URL", "").strip(),
    )
    if discovery_host != issuer_host:
        raise ValueError(
            "AUTH_CORPORATE_DISCOVERY_URL must use the AUTH_CORPORATE_ISSUER host"
        )
    for name in ("AUTH_CORPORATE_AUDIENCE", "AUTH_CORPORATE_CLIENT_ID"):
        if not environment.get(name, "").strip():
            raise ValueError(f"{name} must be configured for corporate identity")
    if not Path(
        environment.get("AUTH_CORPORATE_CLIENT_SECRET_FILE", "").strip()
    ).is_absolute():
        raise ValueError(
            "AUTH_CORPORATE_CLIENT_SECRET_FILE must be an absolute mounted path"
        )
    mapping_file = environment.get("AUTH_CORPORATE_MAPPING_FILE", "").strip()
    if mapping_file and not Path(mapping_file).is_absolute():
        raise ValueError("AUTH_CORPORATE_MAPPING_FILE must be an absolute mounted path")
    if selected == "production" and not _enabled(
        environment.get("AUTH_CORPORATE_REQUIRE_MFA", "true")
    ):
        raise ValueError("AUTH_CORPORATE_REQUIRE_MFA must be true in production")


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
        _validate_authentication_contract(environment, selected)
        _validate_homologation_login(environment)
    else:
        if _enabled(environment.get("SYNERGIA_LOCAL_AUTH_ENABLED")):
            raise ValueError("SYNERGIA_LOCAL_AUTH_ENABLED must be false in production")
        if not _enabled(environment.get("AUTH_REFRESH_COOKIE_SECURE")):
            raise ValueError("AUTH_REFRESH_COOKIE_SECURE must be true in production")
        _validate_authentication_contract(environment, selected)
        if not Path(
            environment.get("AUTH_CORPORATE_MAPPING_FILE", "").strip()
        ).is_absolute():
            raise ValueError(
                "AUTH_CORPORATE_MAPPING_FILE must be an absolute mounted path"
            )
        if any(urlparse(origin).scheme != "https" for origin in origins):
            raise ValueError("AUTH_ALLOWED_ORIGINS must use HTTPS in production")
        if urlparse(environment["SYNERGIA_API_ORIGIN"]).scheme != "https":
            raise ValueError("SYNERGIA_API_ORIGIN must use HTTPS in production")

    return selected
