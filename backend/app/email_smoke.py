"""Targeted SMTP smoke using the normal queue, read-only unless explicitly sent."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.email_config import EmailConfig
from app.email_delivery import (
    EmailDeliveryRepository,
    EmailDeliveryService,
    build_provider,
)


class SMTPEmailSmoke:
    def __init__(self, config: EmailConfig, database_url: str, *, provider=None):
        if not config.enabled or config.provider != "smtp" or config.smtp is None:
            raise ValueError("smtp_smoke_requires_enabled_smtp")
        self.config = replace(config, batch_size=1)
        self.database_url = database_url
        self.provider = provider

    def inspect(self, notification_id: UUID) -> dict:
        if not isinstance(notification_id, UUID):
            raise ValueError("invalid_email_notification_id")
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            connection.read_only = True
            row = connection.execute(
                """
                SELECT n.id, n.state AS notification_state,
                       n.email_template_revision_id, u.status AS user_status,
                       COALESCE((u.notification_preferences->>'email')::boolean,
                                true) AS email_enabled,
                       address.normalized_email, d.state AS delivery_state,
                       d.provider, COALESCE(d.attempt_count, 0) AS attempt_count,
                       CASE WHEN d.id IS NULL THEN
                         n.last_occurred_at + make_interval(secs => %s) <= now()
                       ELSE d.available_at <= now() END AS due
                FROM synergia.notifications n
                JOIN synergia.identity_users u ON u.id = n.recipient_user_id
                LEFT JOIN synergia.email_deliveries d ON d.notification_id = n.id
                LEFT JOIN LATERAL (
                    SELECT normalized_email FROM synergia.user_emails
                    WHERE user_id = u.id AND disabled_at IS NULL AND is_verified
                      AND verified_at IS NOT NULL
                    ORDER BY is_primary DESC, id LIMIT 1
                ) address ON true
                WHERE n.id = %s
                """,
                (self.config.consolidation_seconds, notification_id),
            ).fetchone()
        if row is None:
            raise ValueError("smtp_smoke_notification_not_found")
        allowed = row["normalized_email"] in self.config.smtp.allowed_recipients
        eligible = (
            row["notification_state"] in {"unread", "read"}
            and row["user_status"] == "active"
            and row["email_enabled"]
            and row["email_template_revision_id"] is not None
            and allowed
        )
        return {
            "notification_id": str(notification_id),
            "provider": "smtp",
            "delivery_state": row["delivery_state"] or "not_projected",
            "provider_matches": row["provider"] in {None, "smtp"},
            "recipient_allowed": allowed,
            "eligible": bool(eligible),
            "ready": bool(
                eligible
                and row["provider"] in {None, "smtp"}
                and row["delivery_state"] in {None, "queued", "retry"}
                and row["attempt_count"] < self.config.max_attempts
                and row["due"]
            ),
        }

    def run(self, notification_id: UUID, *, send: bool = False) -> dict:
        result = self.inspect(notification_id)
        result["mode"] = "send" if send else "dry_run"
        if not send:
            return result
        if result["delivery_state"] == "sent" and result["provider_matches"]:
            return {**result, "outcome": "already_accepted", "sent": 0}
        if not result["ready"]:
            return {**result, "outcome": "blocked", "sent": 0}
        service = EmailDeliveryService(
            self.config,
            EmailDeliveryRepository(self.database_url),
            self.provider if self.provider is not None else build_provider(self.config),
        )
        counts = service.run_once(notification_id=notification_id)
        return {
            **result,
            "outcome": "accepted" if counts["sent"] == 1 else "not_confirmed",
            "processed": counts["processed"],
            "sent": counts["sent"],
            "failed": counts["failed"],
        }
