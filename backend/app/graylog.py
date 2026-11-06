"""GELF projection: closed field contract and a single, verified HTTPS destination."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import ssl
import stat
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from app.audit import FORMAT_VERSION, sanitize_event


class GraylogError(ValueError):
    """Only stable codes may leave the private worker process."""


def stable_id(origin: str, event_key: str, occurred_at: datetime | str) -> str:
    when = (
        datetime.fromisoformat(occurred_at)
        if isinstance(occurred_at, str)
        else occurred_at
    )
    if when.utcoffset() is None:
        raise GraylogError("event_timezone_required")
    # Restoring a database can reuse numeric sequences. A different occurrence
    # must not be collapsed into an older event with the same table-local ID.
    stamp = when.astimezone(UTC).isoformat(timespec="microseconds")
    return hashlib.sha256(f"{origin}:{event_key}:{stamp}".encode()).hexdigest()


def private_json(path: Path) -> dict:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
        raise GraylogError("configuration_invalid")
    if os.name != "nt" and info.st_mode & 0o077:
        raise GraylogError("configuration_not_private")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise GraylogError("configuration_invalid")
    return value


@dataclass(frozen=True)
class GraylogConfig:
    endpoint: str = field(repr=False)
    environment: str
    application_version: str
    host: str = "synergia"
    enabled: bool = False
    authorization_confirmed: bool = False
    include_global_events: bool = False
    organization_ids: tuple[UUID, ...] = ()
    include_actor_id: bool = False
    include_resource_id: bool = False
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    ca_file: str | None = field(default=None, repr=False)
    client_cert_file: str | None = field(default=None, repr=False)
    client_key_file: str | None = field(default=None, repr=False)
    timeout_seconds: int = 10
    batch_size: int = 50
    max_attempts: int = 5
    retry_seconds: int = 30
    retryable_statuses: tuple[int, ...] = ()

    def __post_init__(self):
        if not isinstance(self.endpoint, str):
            raise GraylogError("endpoint_invalid")
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path != "/gelf"
            or any(ord(c) <= 32 for c in self.endpoint)
        ):
            raise GraylogError("endpoint_invalid")
        try:
            parsed.port
        except ValueError as exc:
            raise GraylogError("endpoint_invalid") from exc
        if self.environment not in {
            "development",
            "test",
            "homologation",
            "production",
        }:
            raise GraylogError("environment_invalid")
        for value in (self.host, self.application_version):
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}", value):
                raise GraylogError("technical_identity_invalid")
        for name in (
            "enabled",
            "authorization_confirmed",
            "include_global_events",
            "include_actor_id",
            "include_resource_id",
        ):
            if type(getattr(self, name)) is not bool:
                raise GraylogError("boolean_invalid")
        for name, maximum in (
            ("timeout_seconds", 30),
            ("batch_size", 100),
            ("max_attempts", 20),
            ("retry_seconds", 3600),
        ):
            if (
                type(getattr(self, name)) is not int
                or not 1 <= getattr(self, name) <= maximum
            ):
                raise GraylogError("budget_invalid")
        if not all(isinstance(item, UUID) for item in self.organization_ids):
            raise GraylogError("scope_invalid")
        if any(
            type(code) is not int or code not in {429, 503}
            for code in self.retryable_statuses
        ):
            raise GraylogError("retry_contract_invalid")
        if not isinstance(self.headers, dict) or len(self.headers) > 1:
            raise GraylogError("authentication_invalid")
        for key, value in self.headers.items():
            if (
                not re.fullmatch(r"Authorization|X-[A-Za-z0-9-]{1,60}", key)
                or not isinstance(value, str)
                or not 1 <= len(value) <= 4096
                or not all(32 <= ord(c) < 127 for c in value)
            ):
                raise GraylogError("authentication_invalid")
        if bool(self.client_key_file) != bool(self.client_cert_file):
            raise GraylogError("client_certificate_invalid")
        if self.enabled and (
            not self.authorization_confirmed
            or not (self.organization_ids or self.include_global_events)
            or not (self.headers or self.client_cert_file)
        ):
            raise GraylogError("approval_or_authentication_missing")

    @classmethod
    def load(cls, path: Path) -> GraylogConfig:
        raw = private_json(path)
        if "organization_ids" in raw:
            if not isinstance(raw["organization_ids"], list):
                raise GraylogError("scope_invalid")
            raw["organization_ids"] = tuple(
                UUID(value) for value in raw["organization_ids"]
            )
        if "retryable_statuses" in raw:
            if not isinstance(raw["retryable_statuses"], list):
                raise GraylogError("retry_contract_invalid")
            raw["retryable_statuses"] = tuple(raw["retryable_statuses"])
        try:
            return cls(**raw)
        except TypeError as exc:
            raise GraylogError("configuration_invalid") from exc

    def destination_hash(self) -> str:
        # Credentials/certificates can rotate without changing the destination.
        policy = [
            self.endpoint,
            self.environment,
            self.host,
            sorted(str(value) for value in self.organization_ids),
            self.include_global_events,
            self.include_actor_id,
            self.include_resource_id,
        ]
        return hashlib.sha256(json.dumps(policy).encode()).hexdigest()


def to_gelf(row: dict, config: GraylogConfig) -> dict:
    event = sanitize_event(row)
    if event.organization_id is None:
        allowed = config.include_global_events
    else:
        allowed = event.organization_id in config.organization_ids
    if not allowed:
        raise GraylogError("scope_not_approved")
    result = {
        "version": "1.1",
        "host": config.host,
        "short_message": event.action,
        "timestamp": event.occurred_at.timestamp(),
        "level": 4 if event.outcome == "failure" else 6,
        "_event_id": stable_id(row["origin"], row["id"], event.occurred_at),
        "_format_version": FORMAT_VERSION,
        "_environment": config.environment,
        "_service": "synergia-audit-projector",
        "_application_version": config.application_version,
        "_version_context": "collector_release",
        "_emitter_version": "unknown",
        "_origin": event.origin,
        "_outcome": event.outcome,
        "_actor_type": event.actor_type,
        "_resource_type": event.resource_type,
    }
    if event.correlation_id:
        result["_correlation_id"] = str(event.correlation_id)
    if event.organization_id:
        result["_organization_id"] = str(event.organization_id)
    if config.include_actor_id and event.actor_id:
        result["_actor_id"] = str(event.actor_id)
    if config.include_resource_id:
        result["_resource_id"] = event.resource_id
    for key, value in event.metadata.items():
        # GELF 1.1 additional fields are strings/numbers, not JSON booleans.
        result[f"_meta_{key}"] = int(value) if type(value) is bool else value
    # No arbitrary metadata names, full_message, stream/index routing or raw text.
    if len(json.dumps(result).encode()) > 16384:
        raise GraylogError("message_too_large")
    return result


@dataclass(frozen=True)
class DeliveryResult:
    state: str
    code: str


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GelfTransport:
    def __init__(self, config: GraylogConfig):
        self.config = config
        context = ssl.create_default_context(cafile=config.ca_file)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        if config.client_cert_file:
            context.load_cert_chain(config.client_cert_file, config.client_key_file)
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            NoRedirect(),
            urllib.request.HTTPSHandler(context=context),
        )

    def send(self, payload: dict) -> DeliveryResult:
        request = urllib.request.Request(
            self.config.endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json", **self.config.headers},
            method="POST",
        )
        try:
            with self.opener.open(
                request, timeout=self.config.timeout_seconds
            ) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
        except (
            urllib.error.URLError,
            OSError,
            TimeoutError,
            http.client.HTTPException,
        ):
            # A network failure can happen after acceptance. Never retry blindly.
            return DeliveryResult("uncertain", "network_result_unknown")
        if type(status) is not int or not 100 <= status <= 599:
            return DeliveryResult("uncertain", "invalid_http_status")
        if status == 202:
            return DeliveryResult("accepted", "http_202")
        if status in self.config.retryable_statuses:
            return DeliveryResult("pending", f"http_{status}")
        if status >= 500 or 200 <= status < 300:
            return DeliveryResult("uncertain", f"http_{status}_uncertain")
        return DeliveryResult("blocked", f"http_{status}")
