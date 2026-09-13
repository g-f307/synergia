from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from app.imports import PostgresImportRepository
from app.observability.config import ObservabilityConfig
from app.observability.health import probe_postgresql
from app.observability.metrics import render_metrics
from app.observability.telemetry import bind_correlation_id, reset_correlation_id

pytestmark = pytest.mark.integration


def test_postgresql_probe_reports_failure_and_recovery(monkeypatch, tmp_path) -> None:
    available_url = os.environ["DATABASE_URL"]
    failed = probe_postgresql(
        ObservabilityConfig(
            "postgresql://invalid:invalid@127.0.0.1:1/invalid",
            tmp_path,
            "",
            probe_timeout_seconds=1,
        )
    )
    recovered = probe_postgresql(
        ObservabilityConfig(available_url, tmp_path, "", probe_timeout_seconds=2)
    )
    assert (failed.status, recovered.status) == ("unavailable", "healthy")


def test_correlation_is_persisted_in_execution_and_automatic_audit() -> None:
    execution_id = str(uuid4())
    correlation_id = uuid4()
    token = bind_correlation_id(correlation_id)
    try:
        PostgresImportRepository(os.environ["DATABASE_URL"]).start(
            execution_id, "N-FP", "technical", "observability-test"
        )
    finally:
        reset_correlation_id(token)

    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            execution_correlation = connection.execute(
                "SELECT correlation_id FROM synergia.executions WHERE id = %s",
                (execution_id,),
            ).fetchone()[0]
            audit_correlations = connection.execute(
                """
                SELECT correlation_id FROM synergia.audit_events
                WHERE execution_id = %s
                """,
                (execution_id,),
            ).fetchall()
        assert execution_correlation == correlation_id
        assert audit_correlations
        assert all(row[0] == correlation_id for row in audit_correlations)
    finally:
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            connection.execute(
                "DELETE FROM synergia.audit_events WHERE execution_id = %s",
                (execution_id,),
            )
            connection.execute(
                """
                DELETE FROM synergia.execution_state_transitions
                WHERE execution_id = %s
                """,
                (execution_id,),
            )
            connection.execute(
                "DELETE FROM synergia.executions WHERE id = %s", (execution_id,)
            )


def test_persistent_metrics_collect_from_the_current_schema(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL"])
    output = render_metrics().decode()
    assert (
        'synergia_observability_collection_success{collector="postgresql"} 1.0'
        in output
    )
