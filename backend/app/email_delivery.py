from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

# Re-export the existing public imports for workers, tests and integrations.
from app.email_config import EmailConfig as EmailConfig
from app.email_contracts import ConfigurationEmailError, UncertainEmailError
from app.email_contracts import EmailMessage as EmailMessage
from app.email_contracts import EmailProvider as EmailProvider
from app.email_contracts import PermanentEmailError as PermanentEmailError
from app.email_contracts import TemporaryEmailError as TemporaryEmailError
from app.observability.telemetry import safe_log
from app.smtp_email_provider import SAFE_SMTP_FAILURE_CODES, SMTPEmailProvider

SAFE_PARAMETERS = frozenset({"execution_id", "count", "version"})
SMTP_UNCERTAIN = "smtp_confirmation_unknown"


class LocalCaptureEmailProvider:
    """Development/CI provider: captures messages locally and never uses a network."""

    name = "local_capture"

    def __init__(self, path: Path) -> None:
        self.path = path

    def send(self, message: EmailMessage) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        provider_reference = f"local-{message.delivery_id}"
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                captured = json.loads(line)
                if captured.get("delivery_id") == str(message.delivery_id):
                    return str(captured["provider_reference"])
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
    if not config.enabled:
        raise ValueError("email delivery is disabled")
    if config.provider == "smtp":
        if config.smtp is None:
            raise ValueError("SMTP transport configuration is required")
        return SMTPEmailProvider(config.smtp)
    if config.provider != "local_capture":
        raise ValueError("unsupported email provider")
    assert config.capture_path is not None
    return LocalCaptureEmailProvider(config.capture_path)


class EmailDeliveryRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def claim(
        self,
        *,
        limit: int,
        provider: str,
        max_attempts: int,
        consolidation_seconds: int,
        notification_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        if provider not in {"local_capture", "smtp"}:
            raise ValueError("unsupported email provider")
        limit = 1 if provider == "smtp" else limit
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO synergia.email_deliveries (
                    notification_id, notification_version, recipient_user_id,
                    locale, template_version, template_revision_id, state,
                    provider, correlation_id, failure_code, available_at
                )
                SELECT n.id, n.version, n.recipient_user_id,
                       COALESCE(n.email_template_locale, 'pt-BR'),
                       COALESCE(template.version_label, 'unavailable'),
                       n.email_template_revision_id,
                       CASE
                         WHEN n.email_template_revision_id IS NULL THEN 'skipped'
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
                         WHEN n.email_template_revision_id IS NULL
                           THEN 'template_unavailable'
                         WHEN u.status <> 'active' THEN 'recipient_inactive'
                         WHEN NOT COALESCE(
                           (u.notification_preferences->>'email')::boolean, true
                         ) THEN 'preference_disabled'
                         WHEN address.normalized_email IS NULL THEN 'unverified_address'
                         ELSE NULL
                       END,
                       n.last_occurred_at + make_interval(secs => %s)
                FROM synergia.notifications n
                JOIN synergia.identity_users u ON u.id = n.recipient_user_id
                LEFT JOIN synergia.notification_template_revisions template
                  ON template.id = n.email_template_revision_id
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
                  AND (%s::uuid IS NULL OR n.id = %s)
                  AND (
                    NOT EXISTS (
                      SELECT 1 FROM synergia.email_deliveries existing
                      WHERE existing.notification_id = n.id
                    )
                    OR EXISTS (
                      SELECT 1 FROM synergia.email_deliveries existing
                      WHERE existing.notification_id = n.id
                        AND existing.state IN ('queued', 'retry', 'skipped')
                        AND existing.notification_version < n.version
                    )
                  )
                ORDER BY n.last_occurred_at, n.id
                LIMIT %s
                ON CONFLICT (notification_id) DO UPDATE SET
                    notification_version = EXCLUDED.notification_version,
                    locale = EXCLUDED.locale,
                    template_version = EXCLUDED.template_version,
                    template_revision_id = EXCLUDED.template_revision_id,
                    state = EXCLUDED.state,
                    failure_code = EXCLUDED.failure_code,
                    available_at = EXCLUDED.available_at,
                    updated_at = now()
                WHERE synergia.email_deliveries.state IN (
                    'queued', 'retry', 'skipped'
                )
                  AND synergia.email_deliveries.notification_version
                      < EXCLUDED.notification_version
                """,
                (
                    provider,
                    consolidation_seconds,
                    notification_id,
                    notification_id,
                    limit,
                ),
            )
            cursor.execute(
                """
                SELECT id, attempt_count, correlation_id, provider
                FROM synergia.email_deliveries
                WHERE state = 'processing'
                  AND claimed_at < now() - interval '5 minutes'
                  AND provider = %s
                  AND (%s::uuid IS NULL OR notification_id = %s)
                  AND (provider = 'smtp' OR attempt_count >= %s)
                FOR UPDATE SKIP LOCKED
                """,
                (provider, notification_id, notification_id, max_attempts),
            )
            exhausted = cursor.fetchall()
            for delivery in exhausted:
                code = (
                    SMTP_UNCERTAIN
                    if delivery["provider"] == "smtp"
                    else "max_attempts_exceeded"
                )
                cursor.execute(
                    """UPDATE synergia.email_deliveries
                       SET state = 'failed', failure_code = %s,
                           claimed_at = NULL, updated_at = now()
                       WHERE id = %s""",
                    (code, delivery["id"]),
                )
                cursor.execute(
                    """INSERT INTO synergia.email_delivery_attempts (
                         delivery_id, attempt_number, outcome, failure_code,
                         correlation_id
                       ) VALUES (%s, %s, 'failed', %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (
                        delivery["id"],
                        delivery["attempt_count"],
                        code,
                        delivery["correlation_id"],
                    ),
                )
            cursor.execute(
                """
                WITH selected AS (
                    SELECT id FROM synergia.email_deliveries
                    WHERE provider = %s
                      AND (%s::uuid IS NULL OR notification_id = %s) AND (
                           (state = 'queued' AND available_at <= now()) OR (
                             state = 'retry' AND available_at <= now()
                           ) OR (
                             state = 'processing'
                             AND provider = 'local_capture'
                             AND claimed_at < now() - interval '5 minutes'
                           )) AND attempt_count < %s
                    ORDER BY available_at, created_at, id
                    LIMIT %s FOR UPDATE SKIP LOCKED
                )
                UPDATE synergia.email_deliveries d
                   SET state = 'processing', claimed_at = now(),
                       attempt_count = attempt_count + 1, updated_at = now()
                FROM selected WHERE d.id = selected.id
                RETURNING d.*
                """,
                (provider, notification_id, notification_id, max_attempts, limit),
            )
            deliveries = cursor.fetchall()
            for delivery in deliveries:
                cursor.execute(
                    """INSERT INTO synergia.email_delivery_attempts (
                         delivery_id, attempt_number, outcome, correlation_id
                       ) VALUES (%s, %s, 'started', %s)""",
                    (
                        delivery["id"],
                        delivery["attempt_count"],
                        delivery["correlation_id"],
                    ),
                )
                cursor.execute(
                    """
                    SELECT n.notification_type, n.parameters,
                           e.title_template AS subject_template, e.body_template,
                           address.normalized_email AS recipient
                    FROM synergia.notifications n
                    JOIN synergia.notification_template_revisions e
                      ON e.id = %s
                     AND e.channel = 'email'
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
                        delivery["template_revision_id"],
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

    def owns_attempt(
        self, delivery_id: UUID, attempt_number: int, provider: str
    ) -> bool:
        with self._connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM synergia.email_deliveries WHERE id = %s "
                    "AND state = 'processing' AND attempt_count = %s AND provider = %s "
                    "AND claimed_at >= now() - interval '5 minutes'",
                    (delivery_id, attempt_number, provider),
                ).fetchone()
                is not None
            )

    def complete(
        self, delivery_id: UUID, attempt_number: int, provider_reference: str
    ) -> bool:
        return self._finish(
            delivery_id,
            attempt_number,
            "sent",
            None,
            provider_reference,
            None,
        )

    def fail(
        self,
        delivery_id: UUID,
        attempt_number: int,
        *,
        code: str,
        retry: bool,
        retry_after: datetime | None,
    ) -> bool:
        if code == SMTP_UNCERTAIN and retry:
            raise ValueError("Uncertain SMTP results cannot be retried automatically")
        return self._finish(
            delivery_id,
            attempt_number,
            "retry" if retry else "failed",
            code,
            None,
            retry_after,
        )

    def _finish(
        self,
        delivery_id: UUID,
        attempt_number: int,
        state: str,
        failure_code: str | None,
        provider_reference: str | None,
        available_at: datetime | None,
    ) -> bool:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE synergia.email_deliveries
                   SET state = %s, failure_code = %s, provider_reference = %s,
                       available_at = COALESCE(%s, available_at),
                       sent_at = CASE WHEN %s = 'sent' THEN now() ELSE sent_at END,
                       claimed_at = NULL, updated_at = now()
                 WHERE id = %s AND state = 'processing'
                   AND attempt_count = %s
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
                    attempt_number,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                return False
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
            return True


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

    def _code(self, error: Exception, fallback: str) -> str:
        # Only adapter-owned constants may enter audit/logs, never exception text.
        if self.provider is not None and self.provider.name == "smtp":
            code = str(error)
            if code in SAFE_SMTP_FAILURE_CODES:
                return code
        return fallback

    def _failure(self, delivery: dict, code: str, retry: bool) -> bool:
        attempt = delivery["attempt_count"]
        try:
            finalized = self.repository.fail(
                delivery["id"],
                attempt,
                code=code,
                retry=retry,
                retry_after=(
                    datetime.now(UTC)
                    + timedelta(
                        seconds=self.config.retry_seconds * (2 ** (attempt - 1))
                    )
                )
                if retry
                else None,
            )
        except Exception:
            # A database outage must not create a new transport attempt. SMTP
            # processing left behind will be quarantined on lease expiration.
            raise RuntimeError("email_state_unavailable") from None
        safe_log(
            logging.WARNING,
            "email_delivery.failed",
            correlation_id=delivery["correlation_id"],
            attempt=attempt,
            outcome=("retry" if retry else "failed") if finalized else "ignored",
            error_code=code,
        )
        return finalized

    def _process(self, delivery: dict) -> tuple[int, int, bool]:
        assert self.provider is not None
        smtp = self.provider.name == "smtp"
        if smtp:
            try:
                owned = self.repository.owns_attempt(
                    delivery["id"], delivery["attempt_count"], "smtp"
                )
            except Exception:
                raise RuntimeError("email_state_unavailable") from None
            if not owned:
                self._failure(delivery, SMTP_UNCERTAIN, False)
                return 0, 1, True
        message = EmailMessage(
            delivery_id=delivery["id"],
            recipient=delivery["recipient"],
            sender=self.config.sender,
            subject=self._render(delivery["subject_template"], delivery["parameters"]),
            body=self._render(delivery["body_template"], delivery["parameters"]),
            locale=delivery["locale"],
            correlation_id=delivery["correlation_id"],
        )
        try:
            reference = self.provider.send(message)
        except UncertainEmailError:
            code = SMTP_UNCERTAIN if smtp else "provider_confirmation_unknown"
            finalized = self._failure(delivery, code, False)
            return 0, int(finalized) if not smtp else 1, True
        except ConfigurationEmailError as error:
            finalized = self._failure(
                delivery, self._code(error, "provider_configuration_invalid"), False
            )
            return 0, int(finalized), True
        except TemporaryEmailError as error:
            retry = delivery["attempt_count"] < self.config.max_attempts
            finalized = self._failure(
                delivery, self._code(error, "provider_temporarily_unavailable"), retry
            )
            return 0, int(finalized), smtp
        except PermanentEmailError as error:
            finalized = self._failure(
                delivery, self._code(error, "provider_rejected"), False
            )
            return 0, int(finalized), False
        except Exception:
            retry = not smtp and delivery["attempt_count"] < self.config.max_attempts
            finalized = self._failure(
                delivery, SMTP_UNCERTAIN if smtp else "provider_unavailable", retry
            )
            return 0, int(finalized) if not smtp else 1, smtp

        # Finalization is separate from transport. Never schedule a resend just
        # because a server-confirmed message could not be recorded as sent.
        if smtp and reference != f"smtp-{delivery['id']}":
            self._failure(delivery, SMTP_UNCERTAIN, False)
            return 0, 1, True
        try:
            completed = self.repository.complete(
                delivery["id"], delivery["attempt_count"], reference
            )
        except Exception:
            retry = not smtp and delivery["attempt_count"] < self.config.max_attempts
            finalized = self._failure(
                delivery, SMTP_UNCERTAIN if smtp else "provider_unavailable", retry
            )
            return 0, int(finalized) if not smtp else 1, smtp
        if completed:
            return 1, 0, False
        safe_log(
            logging.WARNING if smtp else logging.INFO,
            "email_delivery.stale_completion",
            attempt=delivery["attempt_count"],
            correlation_id=delivery["correlation_id"],
            outcome="ignored",
        )
        return 0, int(smtp), smtp

    def run_once(self, *, notification_id: UUID | None = None) -> dict[str, int | str]:
        if not self.config.enabled:
            return {"status": "disabled", "processed": 0, "sent": 0, "failed": 0}
        if self.provider is None:
            raise RuntimeError("enabled email delivery requires a provider")
        if self.provider.name != self.config.provider:
            raise ConfigurationEmailError("email_provider_mismatch")
        if notification_id is not None and not isinstance(notification_id, UUID):
            raise ValueError("invalid_email_notification_id")
        smtp = self.provider.name == "smtp"
        processed = sent = failed = 0
        # Reserve SMTP just before sending, rather than leasing a whole batch
        # whose later messages could expire before their network call starts.
        for _ in range(self.config.batch_size if smtp else 1):
            deliveries = self.repository.claim(
                limit=1 if smtp else self.config.batch_size,
                provider=self.provider.name,
                max_attempts=self.config.max_attempts,
                consolidation_seconds=self.config.consolidation_seconds,
                **({"notification_id": notification_id} if notification_id else {}),
            )
            if not deliveries:
                break
            for delivery in deliveries:
                processed += 1
                delivered, rejected, stop = self._process(delivery)
                sent += delivered
                failed += rejected
                if stop:
                    return {
                        "status": "enabled",
                        "processed": processed,
                        "sent": sent,
                        "failed": failed,
                    }
        return {
            "status": "enabled",
            "processed": processed,
            "sent": sent,
            "failed": failed,
        }
