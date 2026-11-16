"""Finite workers recorded in immutable audit, independent of API uptime."""

from __future__ import annotations

import time
from uuid import UUID

import psycopg

from app.ai_assistance_repository import AssistancePersistenceError
from app.ai_assistance_telemetry import log_event
from app.observability.telemetry import bind_correlation_id, reset_correlation_id

DATASETS = {
    "retention": "ai_assistance_results",
    "recovery": "ai_assistance_reservations",
}


def record_event(
    connection,
    operation,
    actor_id,
    correlation_id,
    outcome,
    *,
    count=None,
    elapsed_ms=None,
    code=None,
):
    if operation not in DATASETS or outcome not in {"started", "succeeded", "failed"}:
        raise ValueError("invalid maintenance event")
    if code not in {
        None,
        "maintenance_failed",
        "configuration_invalid",
        "database_unavailable",
        "actor_not_found",
    }:
        raise ValueError("invalid maintenance code")
    return (
        connection.execute(
            """INSERT INTO synergia.data_operation_events
        (operation,outcome,dataset,actor_identifier,correlation_id,
         reason_code,record_count,duration_ms)
        VALUES ('retention',%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING RETURNING id""",
            (
                outcome,
                DATASETS[operation],
                str(actor_id),
                correlation_id,
                code,
                count,
                elapsed_ms,
            ),
        ).fetchone()
        is not None
    )


def terminal_event(connection, operation, actor_id, correlation_id, count, started):
    inserted = record_event(
        connection,
        operation,
        actor_id,
        correlation_id,
        "succeeded",
        count=count,
        elapsed_ms=max(0, int((time.monotonic() - started) * 1000)),
    )
    if not inserted:
        raise RuntimeError("maintenance_commit_conflict")


def run_maintenance(
    repository, operation, actor_id, correlation_id, *, batch_size=100, dry_run=True
):
    correlation_id = UUID(str(correlation_id))
    token = bind_correlation_id(correlation_id)
    try:
        return _run_maintenance(
            repository,
            operation,
            actor_id,
            correlation_id,
            batch_size=batch_size,
            dry_run=dry_run,
        )
    finally:
        reset_correlation_id(token)


def _run_maintenance(
    repository, operation, actor_id, correlation_id, *, batch_size=100, dry_run=True
):
    if (
        operation not in DATASETS
        or type(batch_size) is not int
        or not 1 <= batch_size <= 1000
    ):
        raise ValueError("invalid maintenance request")
    method = (
        repository.expire
        if operation == "retention"
        else repository.recover_reservations
    )
    if dry_run:
        result = method(actor_id, correlation_id, batch_size=batch_size, dry_run=True)
        log_event(
            "ai.assistance.maintenance.preview",
            result="preview",
            correlation_id=correlation_id,
        )
        return result
    started = time.monotonic()
    admitted = False
    try:
        with psycopg.connect(repository.database_url, connect_timeout=2) as connection:
            connection.execute("SET LOCAL statement_timeout='2s'")
            # Refuse a nonexistent actor before recording a work intent.
            if (
                connection.execute(
                    "SELECT id FROM synergia.identity_users WHERE id=%s FOR KEY SHARE",
                    (actor_id,),
                ).fetchone()
                is None
            ):
                raise AssistancePersistenceError("actor_not_found")
            if not record_event(
                connection, operation, actor_id, correlation_id, "started"
            ):
                raise ValueError("maintenance_already_started")
        admitted = True
        result = method(
            actor_id,
            correlation_id,
            batch_size=batch_size,
            dry_run=False,
            _maintenance_started=started,
        )
    except Exception as exc:
        code = (
            "database_unavailable"
            if isinstance(exc, psycopg.Error | OSError)
            else "maintenance_failed"
        )
        if (
            isinstance(exc, AssistancePersistenceError)
            and str(exc) == "actor_not_found"
        ):
            code = "actor_not_found"
        if admitted:
            try:
                with psycopg.connect(
                    repository.database_url, connect_timeout=2
                ) as connection:
                    connection.execute("SET LOCAL statement_timeout='2s'")
                    record_event(
                        connection,
                        operation,
                        actor_id,
                        correlation_id,
                        "failed",
                        elapsed_ms=max(0, int((time.monotonic() - started) * 1000)),
                        code=code,
                    )
            except (psycopg.Error, OSError):
                # An unavailable DB cannot audit its own failure: safe log/exit
                # plus the existing DB/collector alert remain necessary.
                pass
        log_event(
            "ai.assistance.maintenance.finished",
            result="failure",
            code=code,
            duration=time.monotonic() - started,
            correlation_id=correlation_id,
        )
        raise
    log_event(
        "ai.assistance.maintenance.finished",
        result="success",
        duration=time.monotonic() - started,
        correlation_id=correlation_id,
    )
    return result
