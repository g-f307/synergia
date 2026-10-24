"""Offline configuration and SMTP envelope policy, independent of any provider."""

from __future__ import annotations

import ipaddress
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.email_contracts import EmailMessage, PermanentEmailError

_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_ATOM = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_LOCAL = re.compile(rf"{_ATOM}(?:\.{_ATOM})*")


def _utf8_fits(value: str, maximum: int) -> bool:
    if len(value) > maximum:
        return False
    try:
        return len(value.encode("utf-8")) <= maximum
    except UnicodeError:
        return False


def normalize_smtp_mailbox(value: str) -> str:
    """One ASCII dot-atom mailbox, normalized like the identity email registry.

    No display names, address lists, quoted local parts or SMTPUTF8. No provider
    alias expansion: plus tags and dots remain significant for the allowlist.
    """
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid SMTP mailbox")
    normalized = value.strip().lower()
    if (
        not normalized.isascii()
        or len(normalized) > 254
        or normalized.count("@") != 1
        or "*" in normalized
    ):
        raise ValueError("Invalid SMTP mailbox")
    local, domain = normalized.split("@")
    if (
        len(local) > 64
        or not _LOCAL.fullmatch(local)
        or "." not in domain
        or not all(_LABEL.fullmatch(label) for label in domain.split("."))
    ):
        raise ValueError("Invalid SMTP mailbox")
    return normalized


def _bounded_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _smtp_password() -> str:
    password = os.getenv("EMAIL_SMTP_PASSWORD", "")
    filename = os.getenv("EMAIL_SMTP_PASSWORD_FILE", "").strip()
    if password and filename:
        raise ValueError("Configure only one SMTP password source")
    if filename:
        try:
            with Path(filename).open("rb") as stream:
                content = stream.read(4097)
            if len(content) > 4096:
                raise ValueError("SMTP password file is too large")
            password = content.decode("utf-8").removesuffix("\n").removesuffix("\r")
        except (OSError, UnicodeError):
            raise ValueError("SMTP password file is unreadable") from None
    return password


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    sender: str = field(repr=False)
    allowed_recipients: frozenset[str] = field(repr=False)
    port: int = 587
    tls_mode: str = "starttls"
    timeout_seconds: float = 15.0
    auth_mode: str = "password"
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.host, str)
            or not self.host
            or len(self.host) > 253
            or not self.host.isascii()
        ):
            raise ValueError("Invalid EMAIL_SMTP_HOST")
        try:
            ipaddress.ip_address(self.host)
        except ValueError:
            if not all(_LABEL.fullmatch(label) for label in self.host.split(".")):
                raise ValueError("Invalid EMAIL_SMTP_HOST") from None
        if (
            isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 1 <= self.port <= 65535
        ):
            raise ValueError("Invalid EMAIL_SMTP_PORT")
        if self.tls_mode not in {"starttls", "implicit"}:
            raise ValueError("EMAIL_SMTP_TLS_MODE must be starttls or implicit")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int | float)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 30
        ):
            raise ValueError("EMAIL_SMTP_TIMEOUT_SECONDS must be finite in (0, 30]")
        if self.auth_mode not in {"password", "none"}:
            raise ValueError("EMAIL_SMTP_AUTH_MODE must be password or none")
        if self.auth_mode == "password" and (not self.username or not self.password):
            raise ValueError(
                "SMTP password authentication requires username and secret"
            )
        if self.auth_mode == "none" and (self.username or self.password):
            raise ValueError(
                "Unauthenticated SMTP relay must not configure credentials"
            )
        if (
            not isinstance(self.username, str)
            or not isinstance(self.password, str)
            or len(self.username) > 320
            or not _utf8_fits(self.password, 4096)
            or not _utf8_fits(self.username, 1280)
            or any(c in self.username + self.password for c in ("\r", "\n", "\x00"))
        ):
            raise ValueError("Invalid SMTP credentials")
        object.__setattr__(self, "sender", normalize_smtp_mailbox(self.sender))
        if (
            not isinstance(self.allowed_recipients, frozenset | set)
            or not self.allowed_recipients
            or len(self.allowed_recipients) > 500
        ):
            raise ValueError(
                "EMAIL_SMTP_ALLOWED_RECIPIENTS requires 1 to 500 mailboxes"
            )
        object.__setattr__(
            self,
            "allowed_recipients",
            frozenset(
                normalize_smtp_mailbox(value) for value in self.allowed_recipients
            ),
        )

    @classmethod
    def from_env(cls) -> SMTPConfig:
        try:
            timeout = float(os.getenv("EMAIL_SMTP_TIMEOUT_SECONDS", "15"))
        except ValueError:
            raise ValueError("Invalid EMAIL_SMTP_TIMEOUT_SECONDS") from None
        raw_allowed = os.getenv("EMAIL_SMTP_ALLOWED_RECIPIENTS", "")
        allowed = raw_allowed.split(",")
        if not raw_allowed.strip() or any(not part.strip() for part in allowed):
            raise ValueError(
                "EMAIL_SMTP_ALLOWED_RECIPIENTS requires explicit mailboxes"
            )
        return cls(
            host=os.getenv("EMAIL_SMTP_HOST", "").strip(),
            sender=os.getenv("EMAIL_FROM_ADDRESS", ""),
            allowed_recipients=frozenset(allowed),
            port=_bounded_env("EMAIL_SMTP_PORT", 587, 1, 65535),
            tls_mode=os.getenv("EMAIL_SMTP_TLS_MODE", "starttls").strip().lower(),
            timeout_seconds=timeout,
            auth_mode=os.getenv("EMAIL_SMTP_AUTH_MODE", "password").strip().lower(),
            username=os.getenv("EMAIL_SMTP_USERNAME", ""),
            password=_smtp_password(),
        )

    def validate_message(self, message: EmailMessage) -> tuple[str, str]:
        """Reject before connection; use the returned single-address envelope."""
        try:
            sender = normalize_smtp_mailbox(message.sender)
            recipient = normalize_smtp_mailbox(message.recipient)
        except ValueError:
            raise PermanentEmailError("invalid_smtp_envelope") from None
        if sender != self.sender:
            raise PermanentEmailError("smtp_sender_mismatch")
        if recipient not in self.allowed_recipients:
            raise PermanentEmailError("smtp_recipient_not_allowed")
        if (
            not isinstance(message.subject, str)
            or not message.subject.strip()
            or len(message.subject) > 998
            or not _utf8_fits(message.subject, 3992)
            or any(ord(c) < 32 or ord(c) == 127 for c in message.subject)
        ):
            raise PermanentEmailError("invalid_smtp_subject")
        if (
            not isinstance(message.body, str)
            or not message.body.strip()
            or not _utf8_fits(message.body, 262144)
            or any(
                (ord(c) < 32 and c not in "\t\r\n") or ord(c) == 127
                for c in message.body
            )
        ):
            raise PermanentEmailError("invalid_smtp_body")
        return sender, recipient


@dataclass(frozen=True)
class EmailConfig:
    enabled: bool = False
    provider: str = "disabled"
    sender: str = field(default="", repr=False)
    capture_path: Path | None = field(default=None, repr=False)
    batch_size: int = 50
    max_attempts: int = 3
    retry_seconds: int = 60
    consolidation_seconds: int = 60
    smtp: SMTPConfig | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.enabled and self.provider == "smtp":
            if (
                self.smtp is None
                or normalize_smtp_mailbox(self.sender) != self.smtp.sender
            ):
                raise ValueError(
                    "SMTP delivery requires matching transport configuration"
                )

    @classmethod
    def from_env(cls) -> EmailConfig:
        enabled = os.getenv("EMAIL_DELIVERY_ENABLED", "false").lower() == "true"
        provider = os.getenv("EMAIL_PROVIDER", "disabled").strip().lower()
        sender = os.getenv("EMAIL_FROM_ADDRESS", "").strip()
        capture = os.getenv("EMAIL_CAPTURE_PATH", "").strip()
        if not enabled:
            return cls()
        if provider not in {"local_capture", "smtp"}:
            raise ValueError("EMAIL_PROVIDER must be local_capture or smtp")
        if not sender:
            raise ValueError("EMAIL_FROM_ADDRESS is required when email is enabled")
        if provider == "local_capture" and not capture:
            raise ValueError("EMAIL_CAPTURE_PATH is required for local_capture")
        return cls(
            enabled=True,
            provider=provider,
            sender=sender,
            capture_path=Path(capture) if provider == "local_capture" else None,
            smtp=SMTPConfig.from_env() if provider == "smtp" else None,
            batch_size=_bounded_env("EMAIL_BATCH_SIZE", 50, 1, 500),
            max_attempts=_bounded_env("EMAIL_MAX_ATTEMPTS", 3, 1, 10),
            retry_seconds=_bounded_env("EMAIL_RETRY_SECONDS", 60, 1, 86400),
            consolidation_seconds=_bounded_env(
                "EMAIL_CONSOLIDATION_SECONDS", 60, 0, 86400
            ),
        )
