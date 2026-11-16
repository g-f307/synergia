import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from prometheus_client import CollectorRegistry, generate_latest

from app.ai_assistance_maintenance import record_event, run_maintenance
from app.ai_assistance_metrics import AiAssistanceCollector
from app.observability.telemetry import SafeJsonFormatter

pytest_plugins = ("test_ai_assistance_repository_persistence",)
pytestmark = [pytest.mark.integration, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("SYNERGIA_ENV", "test")


def collect(database, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database)
    registry = CollectorRegistry()
    registry.register(AiAssistanceCollector())
    return registry, generate_latest(registry).decode()


def rows(database, correlation):
    with psycopg.connect(database) as connection:
        return connection.execute(
            "SELECT outcome,record_count,reason_code "
            "FROM synergia.data_operation_events WHERE correlation_id=%s ORDER BY id",
            (correlation,),
        ).fetchall()


def test_preview_and_empty_effective_batch(setup, database, monkeypatch):
    repo, _, _, actor, _ = setup
    preview, effective = uuid4(), uuid4()
    result = run_maintenance(repo, "retention", actor, preview, dry_run=True)
    assert result["count"] == 0 and rows(database, preview) == []
    result = run_maintenance(repo, "retention", actor, effective, dry_run=False)
    assert result["count"] == 0
    assert rows(database, effective) == [
        ("started", None, None),
        ("succeeded", 0, None),
    ]
    registry, text = collect(database, monkeypatch)
    assert (
        registry.get_sample_value(
            "synergia_ai_assistance_retention_last_success_timestamp_seconds",
            {"environment": "test"},
        )
        > 0
    )
    assert "synergia_ai_assistance_retention_runs_total" in text


def test_recovery_summary_and_outbox_are_atomic(setup, database, monkeypatch):
    repo, key, _, actor, _ = setup
    aid = repo.reserve(key, actor, uuid4())
    with psycopg.connect(database) as connection:
        connection.execute(
            "UPDATE synergia.ai_assistances "
            "SET reservation_until=clock_timestamp()-interval '1 second' WHERE id=%s",
            (aid,),
        )
    correlation = uuid4()
    result = run_maintenance(repo, "recovery", actor, correlation, dry_run=False)
    assert result["count"] == 1
    assert rows(database, correlation) == [
        ("started", None, None),
        ("succeeded", 1, None),
    ]
    with psycopg.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM synergia.graylog_deliveries "
                "WHERE source_snapshot->>'correlation_id'=%s",
                (str(correlation),),
            ).fetchone()[0]
            == 3
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM synergia.audit_event_catalog "
                "WHERE correlation_id=%s",
                (correlation,),
            ).fetchone()[0]
            == 3
        )
    registry, text = collect(database, monkeypatch)
    assert (
        registry.get_sample_value(
            "synergia_ai_assistance_reservations_recovered_total",
            {"environment": "test"},
        )
        >= 1
    )
    assert (
        str(actor) not in text
        and str(aid) not in text
        and str(key.organization_id) not in text
    )


@pytest.mark.parametrize("failure", ["internal", "terminal_conflict"])
def test_failure_rolls_back_deletion_and_is_durably_visible(
    setup, database, monkeypatch, caplog, failure
):
    import app.ai_assistance_maintenance as maintenance

    repo, key, _, actor, _ = setup
    aid = repo.reserve(key, actor, uuid4())
    with psycopg.connect(database) as connection:
        connection.execute(
            "UPDATE synergia.ai_assistances "
            "SET reservation_until=clock_timestamp()-interval '1 second' WHERE id=%s",
            (aid,),
        )
    marker = "PRIVATE_MAINTENANCE_191"

    def fail(*args, **kwargs):
        raise RuntimeError(marker)

    if failure == "internal":
        monkeypatch.setattr(maintenance, "terminal_event", fail)
    else:
        original = maintenance.record_event

        def conflict(connection, operation, actor, correlation, outcome, **kwargs):
            if outcome == "succeeded":
                return False
            return original(
                connection, operation, actor, correlation, outcome, **kwargs
            )

        monkeypatch.setattr(maintenance, "record_event", conflict)
    correlation = uuid4()
    logger = logging.getLogger("synergia.telemetry")
    logger.addHandler(caplog.handler)
    try:
        with pytest.raises(RuntimeError):
            run_maintenance(repo, "recovery", actor, correlation, dry_run=False)
    finally:
        logger.removeHandler(caplog.handler)
    assert rows(database, correlation) == [
        ("started", None, None),
        ("failed", None, "maintenance_failed"),
    ]
    with psycopg.connect(database) as connection:
        assert connection.execute(
            "SELECT id FROM synergia.ai_assistances WHERE id=%s", (aid,)
        ).fetchone()
        assert (
            connection.execute(
                "SELECT count(*) FROM synergia.ai_assistance_events "
                "WHERE assistance_id=%s AND action='expired'",
                (aid,),
            ).fetchone()[0]
            == 0
        )
    registry, _ = collect(database, monkeypatch)
    assert (
        registry.get_sample_value(
            "synergia_ai_assistance_recovery_runs_total",
            {"environment": "test", "result": "failed"},
        )
        >= 1
    )
    from app.observability.metrics import PostgresOperationalCollector

    legacy = CollectorRegistry()
    legacy.register(PostgresOperationalCollector())
    assert (
        legacy.get_sample_value(
            "synergia_data_operation_failures_total", {"operation": "retention"}
        )
        == 0
    )
    logs = "\n".join(SafeJsonFormatter().format(r) for r in caplog.records)
    assert marker not in logs and str(correlation) in logs
    assert str(actor) not in logs


def test_worker_metrics_survive_cli_process_exit(setup, database, monkeypatch):
    _, _, _, actor, _ = setup
    before, _ = collect(database, monkeypatch)
    labels = {"environment": "test", "result": "succeeded"}
    old = before.get_sample_value("synergia_ai_assistance_retention_runs_total", labels)
    command = [
        sys.executable,
        str(ROOT / "scripts/expire_ai_assistance.py"),
        "--actor-id",
        str(actor),
        "--batch-size",
        "1",
    ]
    result = subprocess.run(
        command,
        env={
            **os.environ,
            "DATABASE_URL": database,
            "PYTHONPATH": str(ROOT / "backend"),
        },
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout)["count"] >= 0
    after, _ = collect(database, monkeypatch)
    assert (
        after.get_sample_value("synergia_ai_assistance_retention_runs_total", labels)
        == old + 1
    )
    assert "ai.assistance.maintenance.finished" in result.stderr
    assert database not in result.stderr


def test_repeated_correlation_never_runs_a_second_batch(setup, database, monkeypatch):
    repo, _, _, actor, _ = setup
    correlation = uuid4()
    run_maintenance(repo, "retention", actor, correlation, dry_run=False)
    monkeypatch.setattr(repo, "expire", lambda *a, **k: pytest.fail("duplicate batch"))
    with pytest.raises(ValueError, match="already_started"):
        run_maintenance(repo, "retention", actor, correlation, dry_run=False)
    with psycopg.connect(database) as connection:
        assert not record_event(
            connection,
            "retention",
            actor,
            correlation,
            "failed",
            elapsed_ms=1,
            code="maintenance_failed",
        )
    assert [r[0] for r in rows(database, correlation)] == ["started", "succeeded"]


def test_rollback_keeps_immutable_history_and_reapply_works(setup, database):
    repo, _, _, actor, _ = setup
    correlation = uuid4()
    run_maintenance(repo, "retention", actor, correlation, dry_run=False)
    with psycopg.connect(database) as connection:
        connection.execute(
            (
                ROOT
                / "database/rollbacks/0040_add_ai_assistance_observability.down.sql"
            ).read_text(),
            prepare=False,
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM synergia.data_operation_events "
                "WHERE correlation_id=%s",
                (correlation,),
            ).fetchone()[0]
            == 2
        )
        connection.execute(
            (
                ROOT / "database/migrations/0040_add_ai_assistance_observability.sql"
            ).read_text(),
            prepare=False,
        )
        connection.rollback()
    with psycopg.connect(database) as connection:
        with pytest.raises(psycopg.errors.RestrictViolation):
            connection.execute(
                "DELETE FROM synergia.data_operation_events WHERE correlation_id=%s",
                (correlation,),
            )


def test_unavailable_db_is_not_reported_as_zero_failures(monkeypatch, caplog):
    from app.ai_assistance_repository import PostgresAiAssistanceRepository

    url = "postgresql://PRIVATE_191@127.0.0.1:1/unavailable"
    repo = PostgresAiAssistanceRepository(url)
    logger = logging.getLogger("synergia.telemetry")
    logger.addHandler(caplog.handler)
    try:
        with pytest.raises(psycopg.Error):
            run_maintenance(repo, "retention", uuid4(), uuid4(), dry_run=False)
    finally:
        logger.removeHandler(caplog.handler)
    registry, text = collect(url, monkeypatch)
    assert (
        registry.get_sample_value(
            "synergia_ai_assistance_collection_success", {"environment": "test"}
        )
        == 0
    )
    assert "synergia_ai_assistance_retention_runs_total" not in text
    assert "PRIVATE_191" not in "\n".join(
        SafeJsonFormatter().format(r) for r in caplog.records
    )


def test_started_without_terminal_result_remains_detectable(
    setup, database, monkeypatch
):
    _, _, _, actor, _ = setup
    with psycopg.connect(database) as connection:
        record_event(connection, "retention", actor, uuid4(), "started")
    registry, _ = collect(database, monkeypatch)
    assert (
        registry.get_sample_value(
            "synergia_ai_assistance_retention_unfinished_runs", {"environment": "test"}
        )
        >= 1
    )
