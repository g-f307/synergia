"""Provider-independent message and delivery outcomes; no transport or storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


class TemporaryEmailError(RuntimeError):
    """Known non-acceptance that may be retried within the attempt budget."""


class PermanentEmailError(RuntimeError):
    """Known rejection that must not be retried automatically."""


class ConfigurationEmailError(PermanentEmailError):
    """Operator action is required before another delivery can be attempted."""


class UncertainEmailError(RuntimeError):
    """Acceptance is unknown: reconcile explicitly, never retry automatically."""


@dataclass(frozen=True)
class EmailMessage:
    delivery_id: UUID
    recipient: str = field(repr=False)
    sender: str = field(repr=False)
    subject: str = field(repr=False)
    body: str = field(repr=False)
    locale: str
    correlation_id: UUID | None


class EmailProvider(Protocol):
    """Stable delivery ID for correlation, not a promise of remote deduplication.

    Return an opaque reference after confirmed acceptance. Report known failures
    with Temporary/Permanent/ConfigurationEmailError, and unknown acceptance
    with UncertainEmailError. Transport responses must not enter logs or audit.
    """

    name: str

    def send(self, message: EmailMessage) -> str: ...
