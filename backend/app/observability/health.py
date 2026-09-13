from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from app.observability.config import ObservabilityConfig
from app.observability.metrics import record_dependency


@dataclass(frozen=True)
class ComponentStatus:
    component: str
    status: str
    critical: bool
    duration_ms: float
    reason: str | None = None

    def public(self) -> dict:
        return {key: value for key, value in asdict(self).items() if value is not None}


def _result(
    component: str,
    status: str,
    critical: bool,
    started_at: float,
    reason: str | None = None,
) -> ComponentStatus:
    record_dependency(component, status)
    return ComponentStatus(
        component=component,
        status=status,
        critical=critical,
        duration_ms=round((perf_counter() - started_at) * 1000, 3),
        reason=reason,
    )


def probe_postgresql(config: ObservabilityConfig) -> ComponentStatus:
    started_at = perf_counter()
    if not config.database_url:
        return _result(
            "postgresql", "unavailable", True, started_at, "not_configured"
        )
    try:
        with psycopg.connect(
            config.database_url,
            connect_timeout=config.probe_timeout_seconds,
        ) as connection:
            ready = connection.execute(
                """
                SELECT to_regclass('synergia.executions') IS NOT NULL
                   AND to_regclass('synergia.audit_events') IS NOT NULL
                   AND EXISTS (
                       SELECT 1 FROM information_schema.columns
                       WHERE table_schema = 'synergia'
                         AND table_name = 'audit_events'
                         AND column_name = 'correlation_id'
                   )
                """
            ).fetchone()[0]
    except (psycopg.Error, OSError):
        return _result("postgresql", "unavailable", True, started_at, "probe_failed")
    if not ready:
        return _result(
            "postgresql", "unavailable", True, started_at, "schema_unavailable"
        )
    return _result("postgresql", "healthy", True, started_at)


def probe_storage(config: ObservabilityConfig) -> ComponentStatus:
    started_at = perf_counter()
    target: Path | None = None
    try:
        config.storage_root.mkdir(parents=True, exist_ok=True)
        target = config.storage_root / f".health-{uuid4().hex}"
        target.write_bytes(b"synergia-health")
        if target.read_bytes() != b"synergia-health":
            raise OSError("storage probe mismatch")
    except OSError:
        return _result("storage", "unavailable", True, started_at, "probe_failed")
    finally:
        if target is not None:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
    return _result("storage", "healthy", True, started_at)


def probe_email_worker(config: ObservabilityConfig) -> ComponentStatus:
    started_at = perf_counter()
    from app.email_delivery import EmailConfig

    try:
        email_config = EmailConfig.from_env()
    except (TypeError, ValueError):
        return _result(
            "email_worker", "degraded", False, started_at, "invalid_configuration"
        )
    if not email_config.enabled:
        return _result("email_worker", "disabled", False, started_at)
    if not config.database_url:
        return _result(
            "email_worker", "degraded", False, started_at, "state_unavailable"
        )
    try:
        with psycopg.connect(
            config.database_url,
            connect_timeout=config.probe_timeout_seconds,
            row_factory=dict_row,
        ) as connection:
            state = connection.execute(
                """
                SELECT
                    count(*) FILTER (
                        WHERE state = 'processing'
                          AND claimed_at < now() - make_interval(secs => %s)
                    ) AS stale,
                    count(*) FILTER (
                        WHERE state IN ('queued', 'retry')
                          AND available_at < now() - make_interval(secs => %s)
                    ) AS overdue
                FROM synergia.email_deliveries
                """,
                (config.worker_stale_seconds, config.queue_degraded_seconds),
            ).fetchone()
    except (psycopg.Error, OSError):
        return _result(
            "email_worker", "degraded", False, started_at, "state_unavailable"
        )
    if state and (state["stale"] or state["overdue"]):
        return _result(
            "email_worker", "degraded", False, started_at, "queue_stalled"
        )
    return _result("email_worker", "healthy", False, started_at)


def critical_health(config: ObservabilityConfig) -> list[ComponentStatus]:
    return [probe_postgresql(config), probe_storage(config)]


def complete_health(config: ObservabilityConfig) -> list[ComponentStatus]:
    return [*critical_health(config), probe_email_worker(config)]
