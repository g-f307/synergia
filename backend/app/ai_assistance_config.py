"""Validated, opt-in operational assistance settings. No runtime connection."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

PREFIX = "SYNERGIA_AI_ASSISTANCE_"


@dataclass(frozen=True)
class AiAssistanceConfig:
    enabled: bool = False
    endpoint: str = ""
    model: str = ""
    digest: str = ""
    timeout_seconds: int = 30
    context_max_bytes: int = 8192
    response_max_bytes: int = 8192
    max_concurrency: int = 1
    retention_days: int = 30
    follow_redirects: bool = False

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> AiAssistanceConfig:
        def value(key: str, default: str = "") -> str:
            raw = environment.get(PREFIX + key, default).strip()
            if re.search(r"change.?me|placeholder|<|>", raw, re.I):
                raise ValueError(f"{PREFIX}{key}: placeholder is forbidden")
            return raw

        flag = value("ENABLED", "false")
        if flag not in {"true", "false"}:
            raise ValueError(f"{PREFIX}ENABLED must be true or false")
        for key, fixed in (
            ("TIMEOUT_SECONDS", "30"),
            ("CONTEXT_MAX_BYTES", "8192"),
            ("RESPONSE_MAX_BYTES", "8192"),
            ("MAX_CONCURRENCY", "1"),
            ("FOLLOW_REDIRECTS", "false"),
        ):
            if value(key, fixed) != fixed:
                raise ValueError(f"{PREFIX}{key} must be {fixed}")
        retention = value("RETENTION_DAYS", "30")
        if not retention.isascii() or not retention.isdecimal():
            raise ValueError(f"{PREFIX}RETENTION_DAYS must be an integer")
        if not 1 <= int(retention) <= 365:
            raise ValueError(f"{PREFIX}RETENTION_DAYS must be between 1 and 365")
        endpoint, model, digest = value("ENDPOINT"), value("MODEL"), value("DIGEST")
        allowed_service = value("ALLOWED_SERVICE")
        if allowed_service and not re.fullmatch(
            r"[a-z][a-z0-9-]{0,62}", allowed_service
        ):
            raise ValueError(f"{PREFIX}ALLOWED_SERVICE must be a single service name")
        if endpoint:
            parsed = urlsplit(endpoint)
            try:
                valid_port = parsed.port is None or 1 <= parsed.port <= 65535
                local = ipaddress.ip_address(parsed.hostname or "").is_loopback
            except ValueError:
                local = parsed.hostname == "localhost"
                try:
                    valid_port = parsed.port is None or 1 <= parsed.port <= 65535
                except ValueError:
                    valid_port = False
            if (
                parsed.scheme != "http"
                or not parsed.hostname
                or not valid_port
                or not (
                    local or (allowed_service and parsed.hostname == allowed_service)
                )
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or "?" in endpoint
                or "#" in endpoint
                or any(char.isspace() for char in endpoint)
                or "\\" in endpoint
            ):
                raise ValueError(
                    f"{PREFIX}ENDPOINT must be an allowed local HTTP origin"
                )
        if model and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}", model):
            raise ValueError(f"{PREFIX}MODEL must be a fixed model identifier")
        if digest and not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise ValueError(f"{PREFIX}DIGEST must be a sha256 digest")
        if flag == "true" and not all((endpoint, model, digest)):
            raise ValueError(
                f"{PREFIX}ENDPOINT, MODEL and DIGEST are required when enabled"
            )
        if bool(model) != bool(digest):
            raise ValueError(f"{PREFIX}MODEL and DIGEST must be configured together")
        return cls(
            enabled=flag == "true",
            endpoint=endpoint,
            model=model,
            digest=digest,
            retention_days=int(retention),
        )
