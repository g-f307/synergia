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
    EmailMessage,
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
        consolidation_seconds=0,
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
               WHERE d.notification_id = %s AND a.outcome = 'sent'""",
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
               WHERE d.notification_id = %s AND a.outcome = 'retry'""",
            (failing_notification,),
        ).fetchone()
        assert failure == (
            "retry",
            1,
            "provider_temporarily_unavailable",
            "retry",
            "provider_temporarily_unavailable",
        )


def test_worker_waits_for_consolidation_and_sends_latest_version(tmp_path) -> None:
    database_url = os.environ["DATABASE_URL"]
    org_id, source_id = uuid4(), uuid4().int % 2_000_000_000
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO synergia.iam_organizations (
                 id, organization_code, display_name
               ) VALUES (%s, %s, 'Email Consolidation Org')""",
            (org_id, f"email-window-{org_id.hex[:8]}"),
        )
        user_id = _recipient(connection)
        notification_id = _notification(connection, user_id, org_id, source_id)

    capture = tmp_path / "consolidated.jsonl"
    delayed = EmailConfig(
        enabled=True,
        provider="local_capture",
        sender="no-reply@example.invalid",
        capture_path=capture,
        consolidation_seconds=3600,
    )
    service = EmailDeliveryService(
        delayed,
        EmailDeliveryRepository(database_url),
        LocalCaptureEmailProvider(capture),
    )
    assert service.run_once()["processed"] == 0
    assert not capture.exists()

    with psycopg.connect(database_url) as connection:
        assert (
            _notification(
                connection,
                user_id,
                org_id,
                uuid4().int % 2_000_000_000,
                count=7,
            )
            == notification_id
        )
    assert service.run_once()["processed"] == 0
    with psycopg.connect(database_url) as connection:
        delivery = connection.execute(
            """SELECT id, notification_version, attempt_count
               FROM synergia.email_deliveries
               WHERE notification_id = %s""",
            (notification_id,),
        ).fetchone()
        assert delivery[1:] == (2, 0)
        connection.execute(
            "UPDATE synergia.email_deliveries SET available_at = now() WHERE id = %s",
            (delivery[0],),
        )

    result = service.run_once()
    assert result["sent"] == 1
    records = capture.read_text(encoding="utf-8").splitlines()
    assert len(records) == 1
    assert "7 pendência" in json.loads(records[0])["body"]


def test_recovery_is_idempotent_and_stops_at_attempt_limit(tmp_path) -> None:
    database_url = os.environ["DATABASE_URL"]
    org_id = uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO synergia.iam_organizations (
                 id, organization_code, display_name
               ) VALUES (%s, %s, 'Email Recovery Org')""",
            (org_id, f"email-recovery-{org_id.hex[:8]}"),
        )
        accepted_user = _recipient(connection)
        exhausted_user = _recipient(connection)
        accepted_notification = _notification(
            connection,
            accepted_user,
            org_id,
            uuid4().int % 2_000_000_000,
        )
        exhausted_notification = _notification(
            connection,
            exhausted_user,
            org_id,
            uuid4().int % 2_000_000_000,
        )

    repository = EmailDeliveryRepository(database_url)
    claimed = repository.claim(
        limit=2,
        provider="local_capture",
        max_attempts=3,
        consolidation_seconds=0,
    )
    by_notification = {item["notification_id"]: item for item in claimed}
    accepted = by_notification[accepted_notification]
    exhausted = by_notification[exhausted_notification]
    capture = tmp_path / "recovery.jsonl"
    provider = LocalCaptureEmailProvider(capture)
    provider.send(
        EmailMessage(
            delivery_id=accepted["id"],
            recipient=accepted["recipient"],
            sender="no-reply@example.invalid",
            subject=accepted["subject_template"],
            body=accepted["body_template"],
            locale=accepted["locale"],
            correlation_id=accepted["correlation_id"],
        )
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """UPDATE synergia.email_deliveries
               SET claimed_at = now() - interval '6 minutes'
               WHERE id = ANY(%s)""",
            ([accepted["id"], exhausted["id"]],),
        )
        connection.execute(
            """UPDATE synergia.email_deliveries SET attempt_count = 3
               WHERE id = %s""",
            (exhausted["id"],),
        )

    config = EmailConfig(
        enabled=True,
        provider="local_capture",
        sender="no-reply@example.invalid",
        capture_path=capture,
        max_attempts=3,
        consolidation_seconds=0,
    )
    result = EmailDeliveryService(config, repository, provider).run_once()
    assert result["sent"] == 1
    assert len(capture.read_text(encoding="utf-8").splitlines()) == 1
    with psycopg.connect(database_url) as connection:
        recovered = connection.execute(
            """SELECT state, attempt_count FROM synergia.email_deliveries
               WHERE id = %s""",
            (accepted["id"],),
        ).fetchone()
        exhausted_state = connection.execute(
            """SELECT state, attempt_count, failure_code
               FROM synergia.email_deliveries WHERE id = %s""",
            (exhausted["id"],),
        ).fetchone()
        outcomes = connection.execute(
            """SELECT attempt_number, outcome
               FROM synergia.email_delivery_attempts
               WHERE delivery_id = %s ORDER BY id""",
            (accepted["id"],),
        ).fetchall()
    assert recovered == ("sent", 2)
    assert exhausted_state == ("failed", 3, "max_attempts_exceeded")
    assert outcomes == [(1, "started"), (2, "started"), (2, "sent")]
