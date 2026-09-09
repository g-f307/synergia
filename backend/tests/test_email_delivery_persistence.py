from __future__ import annotations

import json
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.email_delivery import (
    EmailConfig,
    EmailDeliveryRepository,
    EmailDeliveryService,
    LocalCaptureEmailProvider,
    TemporaryEmailError,
)

pytestmark = pytest.mark.integration


class TemporarilyUnavailableProvider:
    name = "local_capture"

    def send(self, _message):
        raise TemporaryEmailError("sensitive provider response")


def _recipient(connection, *, verified=True, email_enabled=True, locale="pt-BR"):
    user_id = uuid4()
    connection.execute(
        """INSERT INTO synergia.identity_users (
             id, status, display_name, locale, notification_preferences
           ) VALUES (%s, 'active', 'Email Delivery Test', %s, %s)""",
        (user_id, locale, Jsonb({"email": email_enabled, "in_app": True})),
    )
    connection.execute(
        """INSERT INTO synergia.user_emails (
             user_id, email, is_primary, is_verified, verified_at
           ) VALUES (%s, %s, true, %s,
             CASE WHEN %s THEN now() ELSE NULL END)""",
        (user_id, f"email-{user_id}@example.invalid", verified, verified),
    )
    return user_id


def _notification(connection, user_id, org_id, source_id, *, count=2):
    return connection.execute(
        """SELECT synergia.enqueue_internal_notification(
             %s, %s, 'pending.summary', %s, %s, %s,
             'audit_event', %s, now(), %s)""",
        (
            user_id,
            org_id,
            f"email-execution-{source_id}",
            Jsonb({"execution_id": f"email-execution-{source_id}", "count": count}),
            f"email.pending:{user_id}",
            source_id,
            uuid4(),
        ),
    ).fetchone()[0]


def test_local_capture_respects_recipient_eligibility_and_audits(tmp_path) -> None:
    database_url = os.environ["DATABASE_URL"]
    org_id = uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO synergia.iam_organizations (
                 id, organization_code, display_name
               ) VALUES (%s, %s, 'Email Delivery Org')""",
            (org_id, f"email-{org_id.hex[:10]}"),
        )
        verified = _recipient(connection, locale="en-US")
        unverified = _recipient(connection, verified=False)
        disabled = _recipient(connection, email_enabled=False)
        source_ids = [uuid4().int % 2_000_000_000 for _ in range(5)]
        notification_id = _notification(
            connection, verified, org_id, source_ids[0]
        )
        assert (
            _notification(connection, verified, org_id, source_ids[1], count=5)
            == notification_id
        )
        _notification(connection, unverified, org_id, source_ids[1])
        _notification(connection, disabled, org_id, source_ids[3])

    capture = tmp_path / "email-capture.jsonl"
    config = EmailConfig(
        enabled=True,
        provider="local_capture",
        sender="no-reply@example.invalid",
        capture_path=capture,
    )
    result = EmailDeliveryService(
        config,
        EmailDeliveryRepository(database_url),
        LocalCaptureEmailProvider(capture),
    ).run_once()
    assert result == {"status": "enabled", "processed": 1, "sent": 1, "failed": 0}
    records = [
        json.loads(line)
        for line in capture.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["locale"] == "en-US"
    assert records[0]["recipient"] == f"email-{verified}@example.invalid"
    assert "5 open pending item" in records[0]["body"]

    with psycopg.connect(database_url) as connection:
        states = connection.execute(
            """SELECT recipient_user_id, state, attempt_count, failure_code
               FROM synergia.email_deliveries
               WHERE recipient_user_id = ANY(%s)
               ORDER BY recipient_user_id""",
            ([verified, unverified, disabled],),
        ).fetchall()
        by_user = {row[0]: row[1:] for row in states}
        assert by_user[verified] == ("sent", 1, None)
        assert by_user[unverified] == (
            "skipped",
            0,
            "unverified_address",
        )
        assert by_user[disabled] == ("skipped", 0, "preference_disabled")
        attempt = connection.execute(
            """SELECT a.outcome, a.failure_code, a.correlation_id
               FROM synergia.email_delivery_attempts a
               JOIN synergia.email_deliveries d ON d.id = a.delivery_id
               WHERE d.notification_id = %s""",
            (notification_id,),
        ).fetchone()
        assert attempt[0:2] == ("sent", None)
        assert attempt[2] is not None
        persisted = str(states).lower()
        assert "@example.invalid" not in persisted
        assert "token" not in persisted and "password" not in persisted

    with psycopg.connect(database_url) as connection:
        failing_user = _recipient(connection)
        failing_notification = _notification(
            connection, failing_user, org_id, source_ids[4]
        )
    failed = EmailDeliveryService(
        config,
        EmailDeliveryRepository(database_url),
        TemporarilyUnavailableProvider(),
    ).run_once()
    assert failed["failed"] == 1
    with psycopg.connect(database_url) as connection:
        failure = connection.execute(
            """SELECT d.state, d.attempt_count, d.failure_code,
                      a.outcome, a.failure_code
               FROM synergia.email_deliveries d
               JOIN synergia.email_delivery_attempts a ON a.delivery_id = d.id
               WHERE d.notification_id = %s""",
            (failing_notification,),
        ).fetchone()
        assert failure == (
            "retry",
            1,
            "provider_temporarily_unavailable",
            "retry",
            "provider_temporarily_unavailable",
        )
