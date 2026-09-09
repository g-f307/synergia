from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

SAFE_PARAMETERS = frozenset({"execution_id", "count", "version"})


class TemporaryEmailError(RuntimeError):
    """A provider failure that may be retried without changing the source event."""


class PermanentEmailError(RuntimeError):
    """A provider rejection that must not be retried."""


@dataclass(frozen=True)
class EmailConfig:
    enabled: bool = False
    provider: str = "disabled"
    sender: str = ""
    capture_path: Path | None = None
    batch_size: int = 50
    max_attempts: int = 3
    retry_seconds: int = 60

    @classmethod
    def from_env(cls) -> EmailConfig:
        enabled = os.getenv("EMAIL_DELIVERY_ENABLED", "false").lower() == "true"
        provider = os.getenv("EMAIL_PROVIDER", "disabled").strip().lower()
        sender = os.getenv("EMAIL_FROM_ADDRESS", "").strip()
        capture = os.getenv("EMAIL_CAPTURE_PATH", "").strip()
        if not enabled:
            return cls()
        if provider != "local_capture":
            raise ValueError("EMAIL_PROVIDER must be local_capture in this release")
        if not sender:
            raise ValueError("EMAIL_FROM_ADDRESS is required when email is enabled")
        if not capture:
            raise ValueError("EMAIL_CAPTURE_PATH is required for local_capture")
        return cls(
            enabled=True,
            provider=provider,
            sender=sender,
            capture_path=Path(capture),
            batch_size=_bounded_env("EMAIL_BATCH_SIZE", 50, 1, 500),
            max_attempts=_bounded_env("EMAIL_MAX_ATTEMPTS", 3, 1, 10),
            retry_seconds=_bounded_env("EMAIL_RETRY_SECONDS", 60, 1, 86_400),
        )


def _bounded_env(name: str, default: int, minimum: int, maximum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class EmailMessage:
    delivery_id: UUID
    recipient: str
    sender: str
    subject: str
    body: str
    locale: str
    correlation_id: UUID | None


class EmailProvider(Protocol):
    name: str

    def send(self, message: EmailMessage) -> str: ...


class LocalCaptureEmailProvider:
    """Development/CI provider: captures messages locally and never uses a network."""

    name = "local_capture"

    def __init__(self, path: Path) -> None:
        self.path = path

    def send(self, message: EmailMessage) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        provider_reference = f"local-{message.delivery_id}"
        record = {
            "delivery_id": str(message.delivery_id),
            "provider_reference": provider_reference,
            "recipient": message.recipient,
            "sender": message.sender,
            "subject": message.subject,
            "body": message.body,
            "locale": message.locale,
            "correlation_id": (
                str(message.correlation_id) if message.correlation_id else None
            ),
        }
        with self.path.open("a", encoding="utf-8") as capture:
            capture.write(json.dumps(record, ensure_ascii=False) + "\n")
        return provider_reference


def build_provider(config: EmailConfig) -> EmailProvider:
    if not config.enabled or config.provider != "local_capture":
        raise ValueError("email delivery is disabled")
    assert config.capture_path is not None
    return LocalCaptureEmailProvider(config.capture_path)


class EmailDeliveryRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def claim(self, *, limit: int, provider: str) -> list[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO synergia.email_deliveries (
                    notification_id, notification_version, recipient_user_id,
                    locale, template_version, state, provider, correlation_id,
                    failure_code
                )
                SELECT n.id, n.version, n.recipient_user_id,
                       CASE WHEN u.locale = 'en-US' THEN 'en-US' ELSE 'pt-BR' END,
                       n.template_version,
                       CASE
                         WHEN u.status <> 'active' THEN 'skipped'
                         WHEN NOT COALESCE(
                           (u.notification_preferences->>'email')::boolean, true
                         ) THEN 'skipped'
                         WHEN address.normalized_email IS NULL THEN 'skipped'
                         ELSE 'queued'
                       END,
                       %s,
                       event.correlation_id,
                       CASE
                         WHEN u.status <> 'active' THEN 'recipient_inactive'
                         WHEN NOT COALESCE(
                           (u.notification_preferences->>'email')::boolean, true
                         ) THEN 'preference_disabled'
                         WHEN address.normalized_email IS NULL THEN 'unverified_address'
                         ELSE NULL
                       END
                FROM synergia.notifications n
                JOIN synergia.identity_users u ON u.id = n.recipient_user_id
                LEFT JOIN LATERAL (
                    SELECT normalized_email
                    FROM synergia.user_emails
                    WHERE user_id = u.id AND disabled_at IS NULL
                      AND is_verified AND verified_at IS NOT NULL
                    ORDER BY is_primary DESC, id
                    LIMIT 1
                ) address ON true
                LEFT JOIN LATERAL (
                    SELECT correlation_id
                    FROM synergia.notification_events
                    WHERE notification_id = n.id AND correlation_id IS NOT NULL
                    ORDER BY id DESC LIMIT 1
                ) event ON true
                WHERE n.state IN ('unread', 'read')
                  AND NOT EXISTS (
                    SELECT 1 FROM synergia.email_deliveries d
                    WHERE d.notification_id = n.id
                      AND d.notification_version = n.version
                  )
                ORDER BY n.last_occurred_at, n.id
                LIMIT %s
                ON CONFLICT (notification_id, notification_version) DO NOTHING
                """,
                (provider, limit),
            )
            cursor.execute(
                """
                WITH selected AS (
                    SELECT id FROM synergia.email_deliveries
                    WHERE (state = 'queued' OR (
                             state = 'retry' AND available_at <= now()
                           ) OR (
                             state = 'processing'
                             AND claimed_at < now() - interval '5 minutes'
                           ))
                    ORDER BY available_at, created_at, id
                    LIMIT %s FOR UPDATE SKIP LOCKED
                )
                UPDATE synergia.email_deliveries d
                   SET state = 'processing', claimed_at = now(), updated_at = now()
                FROM selected WHERE d.id = selected.id
                RETURNING d.*
                """,
                (limit,),
            )
            deliveries = cursor.fetchall()
            for delivery in deliveries:
                cursor.execute(
                    """
                    SELECT n.notification_type, n.parameters,
                           e.subject_template, e.body_template,
                           address.normalized_email AS recipient
                    FROM synergia.notifications n
                    JOIN synergia.email_notification_templates e
                      ON e.notification_type = n.notification_type
                     AND e.template_version = n.template_version
                     AND e.locale = %s
                    JOIN LATERAL (
                        SELECT normalized_email
                        FROM synergia.user_emails
                        WHERE user_id = n.recipient_user_id
                          AND disabled_at IS NULL AND is_verified
                          AND verified_at IS NOT NULL
                        ORDER BY is_primary DESC, id LIMIT 1
                    ) address ON true
                    JOIN synergia.identity_users u ON u.id = n.recipient_user_id
                    WHERE n.id = %s AND n.version = %s
                      AND n.state IN ('unread', 'read') AND u.status = 'active'
                      AND COALESCE(
                        (u.notification_preferences->>'email')::boolean, true
                      )
                    """,
                    (
                        delivery["locale"],
                        delivery["notification_id"],
                        delivery["notification_version"],
                    ),
                )
                content = cursor.fetchone()
                if content is None:
                    cursor.execute(
                        """UPDATE synergia.email_deliveries
                           SET state = 'skipped', failure_code = 'recipient_ineligible',
                               claimed_at = NULL, updated_at = now()
                           WHERE id = %s""",
                        (delivery["id"],),
                    )
                    continue
                delivery.update(content)
            return [item for item in deliveries if "recipient" in item]

    def complete(self, delivery_id: UUID, provider_reference: str) -> None:
        self._finish(delivery_id, "sent", None, provider_reference, None)

    def fail(
        self,
        delivery_id: UUID,
        *,
        code: str,
        retry: bool,
        retry_after: datetime | None,
    ) -> None:
        self._finish(
            delivery_id,
            "retry" if retry else "failed",
            code,
            None,
            retry_after,
        )

    def _finish(
        self,
        delivery_id: UUID,
        state: str,
        failure_code: str | None,
        provider_reference: str | None,
        available_at: datetime | None,
    ) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE synergia.email_deliveries
                   SET state = %s, attempt_count = attempt_count + 1,
                       failure_code = %s, provider_reference = %s,
                       available_at = COALESCE(%s, available_at),
                       sent_at = CASE WHEN %s = 'sent' THEN now() ELSE sent_at END,
                       claimed_at = NULL, updated_at = now()
                 WHERE id = %s
                 RETURNING attempt_count, recipient_user_id, notification_id,
                           correlation_id
                """,
                (
                    state,
                    failure_code,
                    provider_reference,
                    available_at,
                    state,
                    delivery_id,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("email delivery does not exist")
            cursor.execute(
                """
                INSERT INTO synergia.email_delivery_attempts (
                    delivery_id, attempt_number, outcome, failure_code,
                    correlation_id
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    delivery_id,
                    row["attempt_count"],
                    state,
                    failure_code,
                    row["correlation_id"],
                ),
            )


class EmailDeliveryService:
    def __init__(
        self,
        config: EmailConfig,
        repository: EmailDeliveryRepository,
        provider: EmailProvider | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.provider = provider

    @staticmethod
    def _render(template: str, parameters: dict[str, Any]) -> str:
        safe = {
            key: str(value)
            for key, value in parameters.items()
            if key in SAFE_PARAMETERS and isinstance(value, str | int)
        }
        try:
            return template.format_map(safe)
        except (KeyError, ValueError):
            return template

    def run_once(self) -> dict[str, int | str]:
        if not self.config.enabled:
            return {"status": "disabled", "processed": 0, "sent": 0, "failed": 0}
        if self.provider is None:
            raise RuntimeError("enabled email delivery requires a provider")
        deliveries = self.repository.claim(
            limit=self.config.batch_size, provider=self.provider.name
        )
        sent = failed = 0
        for delivery in deliveries:
            message = EmailMessage(
                delivery_id=delivery["id"],
                recipient=delivery["recipient"],
                sender=self.config.sender,
                subject=self._render(
                    delivery["subject_template"], delivery["parameters"]
                ),
                body=self._render(delivery["body_template"], delivery["parameters"]),
                locale=delivery["locale"],
                correlation_id=delivery["correlation_id"],
            )
            try:
                reference = self.provider.send(message)
                self.repository.complete(delivery["id"], reference)
                sent += 1
            except TemporaryEmailError:
                attempt = delivery["attempt_count"] + 1
                can_retry = attempt < self.config.max_attempts
                delay = self.config.retry_seconds * (2 ** (attempt - 1))
                self.repository.fail(
                    delivery["id"],
                    code="provider_temporarily_unavailable",
                    retry=can_retry,
                    retry_after=datetime.now(UTC) + timedelta(seconds=delay),
                )
                failed += 1
                logger.warning(
                    "email delivery temporarily failed",
                    extra={"delivery_id": str(delivery["id"]), "attempt": attempt},
                )
            except PermanentEmailError:
                self.repository.fail(
                    delivery["id"],
                    code="provider_rejected",
                    retry=False,
                    retry_after=None,
                )
                failed += 1
                logger.warning(
                    "email delivery rejected",
                    extra={"delivery_id": str(delivery["id"])},
                )
            except Exception:
                attempt = delivery["attempt_count"] + 1
                can_retry = attempt < self.config.max_attempts
                delay = self.config.retry_seconds * (2 ** (attempt - 1))
                self.repository.fail(
                    delivery["id"],
                    code="provider_unavailable",
                    retry=can_retry,
                    retry_after=datetime.now(UTC) + timedelta(seconds=delay),
                )
                failed += 1
                logger.warning(
                    "email provider unavailable",
                    extra={"delivery_id": str(delivery["id"]), "attempt": attempt},
                )
        return {
            "status": "enabled",
            "processed": len(deliveries),
            "sent": sent,
            "failed": failed,
        }
