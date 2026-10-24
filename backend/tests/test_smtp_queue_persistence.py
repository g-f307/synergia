from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Event
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from test_email_delivery_persistence import _notification, _recipient

from app.email_config import EmailConfig, SMTPConfig
from app.email_contracts import (
    ConfigurationEmailError,
    TemporaryEmailError,
    UncertainEmailError,
)
from app.email_delivery import (
    SMTP_UNCERTAIN,
    EmailDeliveryRepository,
    EmailDeliveryService,
)
from app.email_reconciliation import EmailReconciliationRepository

ROOT = Path(__file__).resolve().parents[2]
SENSITIVE = "SYNTHETIC-SMTP-PRIVATE-RESPONSE-143"
pytestmark = pytest.mark.integration


class FakeSMTPProvider:
    name = "smtp"

    def __init__(self, config, fault=None):
        self.config, self.fault = config, fault
        self.messages = []
        self.accepted = []
        self.before_send = None

    def send(self, message):
        self.config.validate_message(message)
        self.messages.append(message)
        if self.before_send:
            self.before_send(message)
        if self.fault:
            raise self.fault
        self.accepted.append(message.delivery_id)
        return f"smtp-{message.delivery_id}"


class SMTPScene:
    def __init__(self, database):
        self.database = database
        self.repository = EmailDeliveryRepository(database)
        self.reconciler = EmailReconciliationRepository(database)
        self.org = uuid4()
        self.addresses = []
        self.notifications = []
        with psycopg.connect(database) as conn:
            conn.execute(
                "INSERT INTO synergia.iam_organizations "
                "(id, organization_code, display_name) "
                "VALUES (%s, %s, 'Synthetic SMTP')",
                (self.org, f"smtp-{self.org.hex}"),
            )

    def enqueue(self, locale="pt-BR"):
        with psycopg.connect(self.database) as conn:
            user = _recipient(conn, locale=locale)
            notification = _notification(
                conn, user, self.org, uuid4().int % 2_000_000_000
            )
        self.addresses.append(f"email-{user}@example.invalid")
        self.notifications.append(notification)
        return user, notification

    def config(self, **overrides):
        smtp = SMTPConfig(
            host="smtp.example.invalid",
            sender="sender@example.invalid",
            allowed_recipients=frozenset(self.addresses),
            username="synthetic-user",
            password="synthetic-secret",
        )
        return replace(
            EmailConfig(
                enabled=True,
                provider="smtp",
                sender=smtp.sender,
                smtp=smtp,
                consolidation_seconds=0,
                batch_size=5,
            ),
            **overrides,
        )

    def service(self, fault=None, **overrides):
        config = self.config(**overrides)
        provider = FakeSMTPProvider(config.smtp, fault)
        return EmailDeliveryService(config, self.repository, provider), provider

    def delivery(self, notification=None):
        with psycopg.connect(self.database, row_factory=psycopg.rows.dict_row) as conn:
            return conn.execute(
                "SELECT * FROM synergia.email_deliveries WHERE notification_id = %s",
                (notification or self.notifications[0],),
            ).fetchone()

    def attempts(self, identifier):
        with psycopg.connect(self.database) as conn:
            return conn.execute(
                "SELECT attempt_number, outcome, failure_code "
                "FROM synergia.email_delivery_attempts WHERE delivery_id = %s "
                "ORDER BY id",
                (identifier,),
            ).fetchall()

    def uncertain(self, **overrides):
        service, provider = self.service(UncertainEmailError(SENSITIVE), **overrides)
        assert service.run_once()["failed"] == 1
        return self.delivery(), service, provider

    def resolve(self, delivery, **overrides):
        args = {
            "resolution": "accepted",
            "evidence": "smtp_log",
            "request_id": uuid4(),
            "actor_id": uuid4(),
            "workers_stopped": True,
        }
        args.update(overrides)
        return self.reconciler.reconcile(delivery["id"], **args)


@pytest.fixture
def scene(request):
    # One new database per scenario: tests neither drain nor mutate another
    # test's queue, and immutable audit rows need not be deleted.
    name = "synergia_smtp_test_" + uuid4().hex
    with psycopg.connect("", dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    database = psycopg.conninfo.make_conninfo(os.environ["DATABASE_URL"], dbname=name)
    try:
        with psycopg.connect(database) as conn:
            for migration in sorted((ROOT / "database/migrations").glob("*.sql")):
                conn.execute(migration.read_text(), prepare=False)
        value = SMTPScene(database)
        parameters = getattr(getattr(request.node, "callspec", None), "params", {})
        value.enqueue(locale=parameters.get("locale", "pt-BR"))
        yield value
    finally:
        with psycopg.connect("", dbname="postgres", autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (name,),
            )
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.mark.parametrize("locale", ["pt-BR", "en-US"])
def test_versioned_template_and_confirmed_delivery_are_not_resent(scene, locale):
    with psycopg.connect(scene.database) as conn:
        user = conn.execute(
            "SELECT recipient_user_id FROM synergia.notifications WHERE id = %s",
            (scene.notifications[0],),
        ).fetchone()[0]
        _notification(conn, user, scene.org, uuid4().int % 2_000_000_000, count=5)
    service, provider = scene.service()
    assert service.run_once() == {
        "status": "enabled",
        "processed": 1,
        "sent": 1,
        "failed": 0,
    }
    item = provider.messages[0]
    assert item.locale == locale and "5" in item.body
    row = scene.delivery()
    assert row["state"] == "sent" and row["provider"] == "smtp"
    assert row["template_revision_id"] and row["notification_version"] == 2
    assert service.run_once()["processed"] == 0 and len(provider.messages) == 1
    assert scene.attempts(row["id"]) == [(1, "started", None), (1, "sent", None)]


def test_known_nonacceptance_retries_once_with_the_same_delivery_id(scene):
    service, provider = scene.service(TemporaryEmailError(SENSITIVE))
    assert service.run_once()["failed"] == 1
    row = scene.delivery()
    assert row["state"] == "retry" and row["attempt_count"] == 1
    with psycopg.connect(scene.database) as conn:
        conn.execute(
            "UPDATE synergia.email_deliveries SET available_at = now() WHERE id = %s",
            (row["id"],),
        )
    provider.fault = None
    assert service.run_once()["sent"] == 1
    assert {m.delivery_id for m in provider.messages} == {row["id"]}
    assert provider.accepted == [row["id"]]
    assert scene.delivery()["attempt_count"] == 2
    assert [a[1] for a in scene.attempts(row["id"])] == [
        "started",
        "retry",
        "started",
        "sent",
    ]


@pytest.mark.parametrize(
    "error", [UncertainEmailError(SENSITIVE), RuntimeError(SENSITIVE)]
)
def test_unknown_result_is_terminal_even_after_new_notification_version(
    scene, caplog, error
):
    service, provider = scene.service(error)
    with caplog.at_level(logging.WARNING):
        assert service.run_once()["failed"] == 1
    row = scene.delivery()
    assert (row["state"], row["failure_code"], row["attempt_count"]) == (
        "failed",
        SMTP_UNCERTAIN,
        1,
    )
    with psycopg.connect(scene.database) as conn:
        conn.execute(
            "UPDATE synergia.notifications SET version = version + 1 WHERE id = %s",
            (scene.notifications[0],),
        )
    assert service.run_once()["processed"] == 0
    assert len(provider.messages) == 1
    assert SENSITIVE not in caplog.text and scene.addresses[0] not in caplog.text
    assert scene.attempts(row["id"])[-1] == (1, "failed", SMTP_UNCERTAIN)
    with pytest.raises(ValueError, match="cannot be retried"):
        scene.repository.fail(
            row["id"], 1, code=SMTP_UNCERTAIN, retry=True, retry_after=None
        )


def test_configuration_failure_stops_batch_and_preserves_internal_notification(scene):
    scene.enqueue()
    service, provider = scene.service(ConfigurationEmailError(SENSITIVE))
    assert service.run_once()["failed"] == 1 and len(provider.messages) == 1
    row = scene.delivery()
    assert (
        row["failure_code"] == "provider_configuration_invalid"
        and row["state"] == "failed"
    )
    with psycopg.connect(scene.database) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM synergia.notifications WHERE state = 'unread'"
            ).fetchone()[0]
            == 2
        )


def test_each_smtp_reservation_is_made_just_before_its_send(scene):
    scene.enqueue()
    scene.enqueue()
    service, provider = scene.service()

    def verify(message):
        with psycopg.connect(scene.database) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM synergia.email_deliveries "
                    "WHERE state = 'processing'"
                ).fetchone()[0]
                == 1
            )
        assert scene.repository.owns_attempt(message.delivery_id, 1, "smtp")

    provider.before_send = verify
    assert service.run_once()["sent"] == 3
    assert len(set(provider.accepted)) == 3


@pytest.mark.parametrize("distinct", [False, True])
def test_two_workers_do_not_send_the_same_delivery(scene, distinct):
    if distinct:
        scene.enqueue()
    entered, release = Event(), Event()
    first, provider_a = scene.service(batch_size=1)
    second, provider_b = scene.service(batch_size=1)

    def hold(message):
        entered.set()
        assert release.wait(10)

    provider_a.before_send = hold
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first.run_once)
        try:
            assert entered.wait(5)
            assert second.run_once()["sent"] == int(distinct)
        finally:
            release.set()
        assert future.result(timeout=10)["sent"] == 1
    assert len(set(provider_a.accepted + provider_b.accepted)) == 1 + int(distinct)


@pytest.mark.parametrize("accepted_before_crash", [False, True])
def test_expired_smtp_attempt_is_not_recovered_by_sending_again(
    scene, accepted_before_crash
):
    original = scene.repository.claim(
        limit=10, provider="smtp", max_attempts=3, consolidation_seconds=0
    )[0]
    service, provider = scene.service()
    if accepted_before_crash:
        from app.email_delivery import EmailMessage

        provider.send(
            EmailMessage(
                original["id"],
                original["recipient"],
                service.config.sender,
                original["subject_template"],
                original["body_template"],
                original["locale"],
                original["correlation_id"],
            )
        )
    with psycopg.connect(scene.database) as conn:
        conn.execute(
            "UPDATE synergia.email_deliveries "
            "SET claimed_at = now() - interval '6 minutes' WHERE id = %s",
            (original["id"],),
        )
    assert service.run_once()["processed"] == 0
    row = scene.delivery()
    assert (row["state"], row["failure_code"], row["attempt_count"]) == (
        "failed",
        SMTP_UNCERTAIN,
        1,
    )
    assert len(provider.messages) == int(accepted_before_crash)
    assert not scene.repository.complete(row["id"], 1, f"smtp-{row['id']}")


def test_local_capture_worker_cannot_consume_an_smtp_lease(scene, tmp_path):
    scene.repository.claim(
        limit=1, provider="smtp", max_attempts=3, consolidation_seconds=0
    )
    with psycopg.connect(scene.database) as conn:
        conn.execute(
            "UPDATE synergia.email_deliveries "
            "SET claimed_at = now() - interval '6 minutes'"
        )
    from app.email_delivery import LocalCaptureEmailProvider

    capture = tmp_path / "capture.jsonl"
    config = EmailConfig(
        enabled=True,
        provider="local_capture",
        sender="sender@example.invalid",
        capture_path=capture,
        consolidation_seconds=0,
    )
    assert (
        EmailDeliveryService(
            config, scene.repository, LocalCaptureEmailProvider(capture)
        ).run_once()["processed"]
        == 0
    )
    assert not capture.exists() and scene.delivery()["state"] == "processing"


@pytest.mark.parametrize("committed", [False, True])
def test_database_failure_after_acceptance_never_schedules_a_resend(
    scene, monkeypatch, committed
):
    original = scene.repository.complete

    def lost_confirmation(*args):
        if committed:
            original(*args)
        raise RuntimeError(SENSITIVE)

    monkeypatch.setattr(scene.repository, "complete", lost_confirmation)
    service, provider = scene.service()
    assert service.run_once()["failed"] == 1
    row = scene.delivery()
    assert row["state"] == ("sent" if committed else "failed")
    assert service.run_once()["processed"] == 0
    assert provider.accepted == [row["id"]]


def test_reconciliation_records_acceptance_without_rewriting_attempt_history(scene):
    row, service, provider = scene.uncertain()
    before = scene.attempts(row["id"])
    assert scene.reconciler.inspect(row["id"])["state"] == "failed"
    request, actor = uuid4(), uuid4()
    result = scene.resolve(
        row, evidence="recipient_confirmation", request_id=request, actor_id=actor
    )
    replay = scene.resolve(
        row, evidence="recipient_confirmation", request_id=request, actor_id=actor
    )
    assert result["resulting_state"] == "sent" and not result["idempotent_replay"]
    assert replay["idempotent_replay"] and replay["audit_id"] == result["audit_id"]
    assert scene.attempts(row["id"]) == before
    assert service.run_once()["processed"] == 0 and len(provider.messages) == 1
    with (
        psycopg.connect(scene.database) as conn,
        pytest.raises(psycopg.errors.CheckViolation),
    ):
        conn.execute(
            "UPDATE synergia.email_delivery_reconciliations "
            "SET resolution = 'not_accepted'"
        )


@pytest.mark.parametrize("max_attempts,expected", [(3, "retry"), (1, "failed")])
def test_positive_nonacceptance_evidence_respects_remaining_attempt_budget(
    scene, max_attempts, expected
):
    row, service, provider = scene.uncertain(max_attempts=max_attempts)
    result = scene.resolve(
        row, resolution="not_accepted", evidence="smtp_log", max_attempts=max_attempts
    )
    assert result["resulting_state"] == expected
    assert scene.delivery()["attempt_count"] == 1
    provider.fault = None
    assert service.run_once()["sent"] == int(expected == "retry")
    assert scene.delivery()["attempt_count"] == (2 if expected == "retry" else 1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"workers_stopped": False},
        {"resolution": "not_accepted", "evidence": "recipient_confirmation"},
    ],
)
def test_reconciliation_refuses_unsafe_preconditions(scene, overrides):
    row, _, _ = scene.uncertain()
    with pytest.raises(ValueError):
        scene.resolve(row, **overrides)
    assert scene.delivery()["state"] == "failed"


def test_two_reconciliation_requests_with_same_key_have_one_audit_record(scene):
    row, _, _ = scene.uncertain()
    request, actor = uuid4(), uuid4()
    barrier = Barrier(2)

    def resolve():
        barrier.wait(timeout=5)
        return scene.resolve(row, request_id=request, actor_id=actor)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(resolve) for _ in range(2)]
        results = [f.result(timeout=10) for f in futures]
    assert len({r["audit_id"] for r in results}) == 1
    assert {r["idempotent_replay"] for r in results} == {False, True}


def test_inspection_and_reconciliation_cli_expose_only_technical_metadata(scene):
    row, _, _ = scene.uncertain()
    env = os.environ.copy()
    env["DATABASE_URL"] = scene.database
    script = ROOT / "scripts/reconcile_smtp_delivery.py"
    process = subprocess.run(
        [sys.executable, str(script), str(row["id"])],
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert process.returncode == 0
    assert json.loads(process.stdout)["state"] == "failed"
    assert scene.delivery()["state"] == "failed"
    for forbidden in (
        *scene.addresses,
        SENSITIVE,
        "synthetic-secret",
        "body",
        "subject",
    ):
        assert forbidden not in process.stdout + process.stderr


def test_rollback_refuses_to_remove_smtp_delivery_history(scene):
    scene.uncertain()
    rollback = (
        ROOT / "database/rollbacks/0033_allow_smtp_email_delivery.down.sql"
    ).read_text()
    with (
        psycopg.connect(scene.database) as conn,
        pytest.raises(psycopg.errors.RaiseException),
    ):
        conn.execute(rollback, prepare=False)
    assert scene.delivery()["provider"] == "smtp"


def test_lost_lease_prevents_smtp_call(scene, monkeypatch):
    monkeypatch.setattr(scene.repository, "owns_attempt", lambda *args: False)
    service, provider = scene.service()
    assert service.run_once()["failed"] == 1
    assert not provider.messages
    assert scene.delivery()["failure_code"] == SMTP_UNCERTAIN


def test_full_database_outage_after_acceptance_leaves_attempt_for_quarantine(
    scene, monkeypatch
):
    def unavailable(*args, **kwargs):
        raise RuntimeError(SENSITIVE)

    service, provider = scene.service()
    with monkeypatch.context() as patch:
        patch.setattr(scene.repository, "complete", unavailable)
        patch.setattr(scene.repository, "fail", unavailable)
        with pytest.raises(RuntimeError, match="^email_state_unavailable$"):
            service.run_once()
    row = scene.delivery()
    assert row["state"] == "processing" and len(provider.accepted) == 1
    with psycopg.connect(scene.database) as conn:
        conn.execute(
            "UPDATE synergia.email_deliveries "
            "SET claimed_at = now() - interval '6 minutes'"
        )
    assert service.run_once()["processed"] == 0
    assert scene.delivery()["failure_code"] == SMTP_UNCERTAIN
    assert len(provider.accepted) == 1


def test_smtp_worker_does_not_retag_pending_capture_delivery(scene):
    assert (
        scene.repository.claim(
            limit=1,
            provider="local_capture",
            max_attempts=3,
            consolidation_seconds=3600,
        )
        == []
    )
    service, provider = scene.service()
    assert service.run_once()["processed"] == 0
    assert scene.delivery()["provider"] == "local_capture"
    assert not provider.messages


def test_reconciliation_key_cannot_be_reused_for_another_resolution(scene):
    row, _, _ = scene.uncertain()
    request = uuid4()
    scene.resolve(row, request_id=request)
    with pytest.raises(ValueError, match="reconciliation_request_conflict"):
        scene.resolve(row, request_id=request, resolution="not_accepted")
    assert scene.delivery()["state"] == "sent"


@pytest.mark.parametrize("expired", [False, True])
def test_stopped_worker_reservation_requires_expiration_before_reconciliation(
    scene, expired
):
    scene.repository.claim(
        limit=1, provider="smtp", max_attempts=3, consolidation_seconds=0
    )
    row = scene.delivery()
    if not expired:
        with pytest.raises(ValueError, match="not_awaiting_smtp_reconciliation"):
            scene.resolve(row)
        assert scene.delivery()["state"] == "processing"
        return
    with psycopg.connect(scene.database) as conn:
        conn.execute(
            "UPDATE synergia.email_deliveries "
            "SET claimed_at = now() - interval '6 minutes'"
        )
    assert scene.resolve(row)["resulting_state"] == "sent"
    assert scene.attempts(row["id"]) == [
        (1, "started", None),
        (1, "failed", SMTP_UNCERTAIN),
    ]


def test_rollback_before_first_smtp_delivery_preserves_internal_notifications(scene):
    rollback = (
        ROOT / "database/rollbacks/0033_allow_smtp_email_delivery.down.sql"
    ).read_text()
    with psycopg.connect(scene.database) as conn:
        conn.execute(rollback, prepare=False)
        assert conn.execute(
            "SELECT count(*) FROM synergia.notifications"
        ).fetchone() == (1,)
        assert conn.execute(
            "SELECT to_regclass('synergia.email_delivery_reconciliations')"
        ).fetchone() == (None,)
