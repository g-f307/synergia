"""Real PostgreSQL, committed intent, restart, late commits and safe reconciliation."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.graylog import DeliveryResult, GraylogConfig, GraylogError, stable_id
from app.graylog_delivery import GraylogRepository, run_batch
from app.graylog_metrics import GraylogCollector
from app.model_audit import ModelAuditRepository

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def database():
    # A new database owned by this fixture; no truncation of shared audit tables.
    source = os.environ["DATABASE_URL"]
    name = "synergia_graylog_" + uuid4().hex
    with psycopg.connect(source, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    target = make_conninfo(**(conninfo_to_dict(source) | {"dbname": name}))
    try:
        env = dict(os.environ, DATABASE_URL=target)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/apply_migrations.py")],
            env=env,
            check=True,
            capture_output=True,
        )
        yield target
    finally:
        with psycopg.connect(source, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


@pytest.fixture
def config():
    return GraylogConfig(
        endpoint="https://graylog.example.invalid/gelf",
        environment="test",
        application_version="synthetic-v1",
        enabled=True,
        authorization_confirmed=True,
        include_global_events=True,
        headers={"Authorization": "synthetic-input-secret"},
        retry_seconds=1,
        max_attempts=2,
    )


@pytest.fixture
def repository(database):
    # Each case leaves immutable evidence. Defer previous pending fixtures only.
    with psycopg.connect(database) as connection:
        connection.execute(
            """UPDATE synergia.graylog_deliveries
            SET next_attempt_at = clock_timestamp() + interval '100 years'
            WHERE state = 'pending'"""
        )
    return GraylogRepository(database)


def insert_event(connection, *, when=None, payload=None):
    return "identity:" + str(
        connection.execute(
            """INSERT INTO synergia.identity_access_events
        (event_key, entity_type, entity_id, correlation_id, payload, occurred_at)
        VALUES ('auth.login_failed', 'security_control', 'synthetic', %s, %s, %s)
        RETURNING id""",
            (uuid4(), Jsonb(payload or {}), when or datetime.now(UTC)),
        ).fetchone()["id"]
    )


def row(database, key):
    with psycopg.connect(database, row_factory=dict_row) as connection:
        return connection.execute(
            "SELECT * FROM synergia.graylog_deliveries WHERE event_key = %s",
            (key,),
        ).fetchone()


def event(database, **kwargs):
    with psycopg.connect(database, row_factory=dict_row) as connection:
        return insert_event(connection, **kwargs)


class Transport:
    def __init__(self, state="accepted", code="http_202", callback=None):
        self.calls = []
        self.state, self.code, self.callback = state, code, callback

    def send(self, payload):
        self.calls.append(payload)
        if self.callback:
            self.callback(payload)
        return DeliveryResult(self.state, self.code)


def test_accepted_is_not_resent_and_intent_is_committed_before_network(
    database, repository, config
):
    key = event(database, payload={"prompt": "private-cell", "token": "private-token"})

    def assert_intent(_):
        assert row(database, key)["state"] == "inflight"
        assert row(database, key)["attempts"] == 1

    transport = Transport(callback=assert_intent)
    run_batch(repository, config, transport)
    run_batch(repository, config, transport)
    assert len(transport.calls) == 1
    assert row(database, key)["state"] == "accepted"
    assert "private" not in str(row(database, key)["source_snapshot"])
    with psycopg.connect(database) as connection:
        assert connection.execute(
            "SELECT action FROM synergia.graylog_delivery_history "
            "WHERE event_key = %s ORDER BY id",
            (key,),
        ).fetchall() == [("intent",), ("accepted",)]


def test_late_commit_and_equal_timestamp_are_not_skipped(database, repository, config):
    when = datetime(2026, 8, 1, tzinfo=UTC)
    with psycopg.connect(database, row_factory=dict_row) as late:
        first = insert_event(late, when=when)
        second = event(database, when=when)
        transport = Transport()
        run_batch(repository, config, transport)
        assert [p["_event_id"] for p in transport.calls] == [
            stable_id("identity_access_events", second, when)
        ]
        late.commit()
    run_batch(repository, config, transport)
    assert len(transport.calls) == 2
    assert row(database, first)["state"] == "accepted"


def test_interrupted_send_is_held_until_receipt_is_confirmed(
    database, repository, config
):
    key = event(database)

    def crash(_):
        raise RuntimeError("simulated process interruption")

    with pytest.raises(RuntimeError):
        run_batch(repository, config, Transport(callback=crash))
    assert row(database, key)["state"] == "inflight"
    recovered = Transport()
    run_batch(repository, config, recovered)
    assert recovered.calls == []
    assert row(database, key)["state"] == "uncertain"
    with repository.locked() as connection:
        repository.reconcile(
            connection,
            row(database, key)["event_id"],
            "confirm_received",
            uuid4(),
            uuid4(),
        )
    run_batch(repository, config, recovered)
    assert recovered.calls == []
    assert row(database, key)["state"] == "accepted"


def test_unknown_result_requires_absence_evidence_before_requeue(
    database, repository, config
):
    key = event(database)
    run_batch(repository, config, Transport("uncertain", "network_result_unknown"))
    held = row(database, key)
    with repository.locked() as connection:
        with pytest.raises(GraylogError, match="reconciliation_state_invalid"):
            repository.reconcile(
                connection, held["event_id"], "requeue", uuid4(), uuid4()
            )
        repository.reconcile(
            connection, held["event_id"], "confirm_absent", uuid4(), uuid4()
        )
    transport = Transport()
    run_batch(repository, config, transport)
    assert len(transport.calls) == 1
    with repository.locked() as connection:
        with pytest.raises(GraylogError):
            repository.reconcile(
                connection, held["event_id"], "confirm_absent", uuid4(), uuid4()
            )


def test_bounded_backoff_and_exhausted_event_are_preserved(
    database, repository, config
):
    key = event(database)
    transport = Transport("pending", "http_503")
    run_batch(repository, config, transport, jitter=lambda _a, _b: 0)
    assert row(database, key)["state"] == "pending"
    run_batch(repository, config, transport)
    assert len(transport.calls) == 1
    with psycopg.connect(database) as connection:
        connection.execute(
            "UPDATE synergia.graylog_deliveries SET next_attempt_at = now() "
            "WHERE event_key = %s",
            (key,),
        )
    run_batch(repository, config, transport)
    assert row(database, key)["state"] == "exhausted"
    run_batch(repository, config, transport)
    assert len(transport.calls) == 2


def test_two_collectors_cannot_send_the_same_batch(repository):
    with repository.locked():
        with pytest.raises(GraylogError, match="collector_busy"):
            with repository.locked():
                pytest.fail("second collector acquired lock")


def test_source_projection_survives_security_transient_retention(
    database, repository, config
):
    with psycopg.connect(database, row_factory=dict_row) as connection:
        value = connection.execute(
            """INSERT INTO synergia.rate_limit_events
            (operation, dimension, key_hash, retry_after_seconds, method, route_group)
            VALUES ('login', 'origin', %s, 1, 'POST', '/auth/login') RETURNING id""",
            ("f" * 64,),
        ).fetchone()["id"]
        connection.execute(
            "DELETE FROM synergia.rate_limit_events WHERE id = %s", (value,)
        )
    transport = Transport()
    run_batch(repository, config, transport)
    assert len(transport.calls) == 1
    assert transport.calls[0]["short_message"] == "security.rate_limit_denied"
    assert "f" * 64 not in str(transport.calls)
    assert row(database, "security_rate:" + str(value))["state"] == "accepted"


def test_historical_windows_resume_and_do_not_duplicate(database, repository):
    start = datetime(2025, 1, 1, tzinfo=UTC)
    keys = [event(database, when=start) for _ in range(3)]
    with repository.locked() as connection:
        for expected, complete in [(2, False), (1, True), (0, True)]:
            assert repository.backfill(
                connection,
                "identity_access_events",
                start,
                start + timedelta(days=1),
                2,
                uuid4(),
                uuid4(),
            ) == (expected, complete)
        actual = connection.execute(
            "SELECT count(*) AS count FROM synergia.graylog_deliveries "
            "WHERE event_key = ANY(%s)",
            (keys,),
        ).fetchone()["count"]
        assert actual == 3


def test_historical_template_backfill_and_future_capture_match_catalog(
    database, repository
):
    from app.audit import sanitize_event

    with repository.locked() as connection:
        historical = connection.execute(
            """SELECT * FROM synergia.audit_event_catalog
            WHERE origin = 'notification_template_events'
            ORDER BY occurred_at LIMIT 1"""
        ).fetchone()
        assert historical is not None
        assert (
            connection.execute(
                "SELECT 1 FROM synergia.graylog_deliveries WHERE event_key = %s",
                (historical["id"],),
            ).fetchone()
            is None
        )
        repository.backfill(
            connection,
            "notification_template_events",
            historical["occurred_at"],
            historical["occurred_at"] + timedelta(seconds=1),
            100,
            uuid4(),
            uuid4(),
        )
        snapshot = connection.execute(
            "SELECT source_snapshot FROM synergia.graylog_deliveries "
            "WHERE event_key = %s",
            (historical["id"],),
        ).fetchone()["source_snapshot"]
        assert sanitize_event(snapshot) == sanitize_event(historical)
        created = connection.execute(
            """INSERT INTO synergia.notification_template_events
            (revision_id, event_type, reason, payload)
            SELECT id, 'template.published', 'synthetic test', %s
            FROM synergia.notification_template_revisions LIMIT 1 RETURNING id""",
            (Jsonb({"prompt": "private-text"}),),
        ).fetchone()["id"]
        captured = connection.execute(
            """SELECT q.source_snapshot, c.* FROM synergia.graylog_deliveries q
            JOIN synergia.audit_event_catalog c ON c.id = q.event_key
            WHERE c.id = %s""",
            ("template:" + str(created),),
        ).fetchone()
        snapshot = captured.pop("source_snapshot")
        assert sanitize_event(snapshot) == sanitize_event(captured)
        assert "private-text" not in str(snapshot)


def test_unapproved_scope_is_blocked_and_metrics_need_no_graylog_secret(
    database, repository, config, monkeypatch
):
    from dataclasses import replace

    # This config was bound by previous cases: changing privacy/scope is refused.
    with repository.locked() as connection:
        with pytest.raises(GraylogError, match="destination_or_scope_changed"):
            repository.bind(connection, replace(config, include_actor_id=True))
    monkeypatch.setenv("DATABASE_URL", database)
    metrics = list(GraylogCollector().collect())
    assert any(m.name == "synergia_graylog_queue" for m in metrics)
    assert "synthetic-input-secret" not in str(metrics)


def test_llm_metadata_is_durable_sanitized_and_history_is_immutable(
    database, repository
):
    from types import SimpleNamespace

    from app.audit import sanitize_event

    actor = uuid4()
    with psycopg.connect(database) as connection:
        connection.execute(
            "INSERT INTO synergia.identity_users (id, status, display_name) "
            "VALUES (%s, 'active', 'Synthetic')",
            (actor,),
        )
    ModelAuditRepository(database).record(
        SimpleNamespace(user_id=actor, correlation_id=uuid4()),
        uuid4(),
        "llm.completed",
        duration_ms=100,
        fallback=True,
    )
    with psycopg.connect(database, row_factory=dict_row) as connection:
        source = connection.execute(
            "SELECT * FROM synergia.audit_event_catalog "
            "WHERE origin = 'observability_events'"
        ).fetchone()
        clean = sanitize_event(source)
        assert clean.metadata["fallback"] is True
        assert clean.metadata["model"] == "qwen3:4b-instruct"
        assert "prompt" not in clean.metadata and "tokens" not in clean.metadata
        with pytest.raises(psycopg.Error):
            connection.execute("DELETE FROM synergia.observability_events")


def test_execution_capture_uses_text_id_and_matches_canonical_projection(
    database, repository
):
    from app.audit import sanitize_event

    identifier = "synthetic-graylog-" + uuid4().hex
    with psycopg.connect(database, row_factory=dict_row) as connection:
        connection.execute(
            "INSERT INTO synergia.executions (id) VALUES (%s)",
            (identifier,),
        )
        captured = connection.execute(
            """SELECT q.source_snapshot, c.* FROM synergia.graylog_deliveries q
            JOIN synergia.audit_event_catalog c ON c.id = q.event_key
            WHERE c.resource_id = %s AND c.origin = 'audit_events'""",
            (identifier,),
        ).fetchall()
        assert captured
        for item in captured:
            snapshot = item.pop("source_snapshot")
            assert sanitize_event(snapshot) == sanitize_event(item)
        connection.execute(
            """INSERT INTO synergia.audit_events
            (execution_id, entity_type, entity_id, event_type, payload)
            VALUES (%s, 'execution', %s, 'execution_started', %s)""",
            (
                identifier,
                identifier,
                Jsonb(
                    {
                        "version": {"nested": ["private-prompt"]},
                        "from_state": "private-response",
                        "state_version": 2,
                    }
                ),
            ),
        )
        snapshots = connection.execute(
            "SELECT source_snapshot FROM synergia.graylog_deliveries "
            "WHERE origin = 'audit_events'"
        ).fetchall()
        assert "private-prompt" not in str(snapshots)
        assert "private-response" not in str(snapshots)


def test_manual_rollback_preserves_receipts_and_canonical_audit(
    database, repository, config
):
    key = event(database)
    run_batch(repository, config, Transport())
    with psycopg.connect(database, row_factory=dict_row) as connection:
        try:
            connection.execute(
                (
                    ROOT / "database/rollbacks/0036_create_graylog_delivery.down.sql"
                ).read_text(),
                prepare=False,
            )
            assert (
                connection.execute(
                    "SELECT state FROM synergia.graylog_deliveries "
                    "WHERE event_key = %s",
                    (key,),
                ).fetchone()["state"]
                == "accepted"
            )
            assert (
                connection.execute(
                    "SELECT id FROM synergia.audit_event_catalog WHERE id = %s",
                    (key,),
                ).fetchone()["id"]
                == key
            )
            assert (
                connection.execute(
                    "SELECT count(*) AS total FROM pg_trigger "
                    "WHERE tgname = 'graylog_source_insert'"
                ).fetchone()["total"]
                == 0
            )
        finally:
            connection.rollback()
