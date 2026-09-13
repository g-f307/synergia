from __future__ import annotations

# Operational aggregation SQL is intentionally kept in readable aligned blocks.
# ruff: noqa: E501
import logging
import os
from collections.abc import Iterable
from typing import Any

import psycopg
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    GCCollector,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    generate_latest,
)
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from psycopg.rows import dict_row

from app.observability.telemetry import safe_log

REGISTRY = CollectorRegistry()
ProcessCollector(registry=REGISTRY)
PlatformCollector(registry=REGISTRY)
GCCollector(registry=REGISTRY)

HTTP_REQUESTS = Counter(
    "synergia_http_requests",
    "HTTP requests handled by the API.",
    ("method", "route", "status_class"),
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "synergia_http_request_duration_seconds",
    "HTTP request duration by stable route template.",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    registry=REGISTRY,
)
DEPENDENCY_UP = Gauge(
    "synergia_dependency_up",
    "Whether an operational dependency is available.",
    ("component",),
    registry=REGISTRY,
)
DEPENDENCY_DEGRADED = Gauge(
    "synergia_dependency_degraded",
    "Whether an operational dependency is available but degraded.",
    ("component",),
    registry=REGISTRY,
)

_SAFE_STATES = {
    "execution": frozenset(
        {
            "pending",
            "validating",
            "validation_failed",
            "normalizing",
            "consolidating",
            "applying_rules",
            "completed",
            "completed_with_errors",
            "failed",
            "reprocessing",
            "duplicate",
            "cancelled",
        }
    ),
    "inspection": frozenset({"accepted", "rejected"}),
    "report": frozenset({"generating", "succeeded", "failed", "cancelled"}),
    "notification": frozenset({"unread", "read", "suppressed", "failed"}),
    "email": frozenset({"queued", "processing", "retry", "sent", "skipped", "failed"}),
    "approval": frozenset(
        {"draft", "submitted", "in_review", "approved", "rejected", "returned"}
    ),
}
_SAFE_OUTCOMES = {
    "execution": _SAFE_STATES["execution"],
    "inspection": _SAFE_STATES["inspection"],
    "report": frozenset(
        {
            "generation_started",
            "generation_succeeded",
            "generation_failed",
            "generation_cancelled",
            "consulted",
            "exported",
            "export_failed",
        }
    ),
    "notification": frozenset(
        {
            "created",
            "delivered",
            "consolidated",
            "read",
            "suppressed",
            "delivery_failed",
        }
    ),
    "email": frozenset({"started", "sent", "retry", "failed"}),
    "approval": frozenset(
        {
            "created",
            "submitted",
            "assigned",
            "reassigned",
            "approved",
            "rejected",
            "returned",
            "resubmitted",
        }
    ),
    "reprocessing": frozenset({"requested"}),
}
_SAFE_RATE_OPERATIONS = frozenset(
    {
        "login",
        "refresh",
        "upload",
        "search",
        "reprocess",
        "report_generate",
        "report_export",
        "decision",
    }
)
_SAFE_RATE_DIMENSIONS = frozenset(
    {"origin", "identifier", "user", "session", "organization", "credential"}
)


def _bounded(value: Any, allowed: frozenset[str]) -> str:
    normalized = str(value or "unknown").removeprefix("report.").removeprefix(
        "notification."
    )
    return normalized if normalized in allowed else "other"


def observe_http_request(
    method: str, route: str, status_code: int, duration_seconds: float
) -> None:
    safe_method = method if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"} else "OTHER"
    safe_route = route if route.startswith("/") and len(route) <= 120 else "unmatched"
    status_class = f"{status_code // 100}xx" if 100 <= status_code <= 599 else "unknown"
    HTTP_REQUESTS.labels(safe_method, safe_route, status_class).inc()
    HTTP_DURATION.labels(safe_method, safe_route).observe(max(duration_seconds, 0))


def record_dependency(component: str, status: str) -> None:
    if component not in {"configuration", "postgresql", "storage", "email_worker"}:
        return
    DEPENDENCY_UP.labels(component).set(1 if status in {"healthy", "disabled"} else 0)
    DEPENDENCY_DEGRADED.labels(component).set(1 if status == "degraded" else 0)


class PostgresOperationalCollector:
    """Expose bounded aggregates from persisted operational state and events."""

    def collect(self) -> Iterable[Any]:
        collection = GaugeMetricFamily(
            "synergia_observability_collection_success",
            "Whether a persistent metrics collection completed.",
            labels=["collector"],
        )
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            collection.add_metric(["postgresql"], 0)
            yield collection
            return
        try:
            timeout = int(os.getenv("OBSERVABILITY_PROBE_TIMEOUT_SECONDS", "2"))
            with psycopg.connect(
                database_url,
                connect_timeout=max(1, timeout),
                row_factory=dict_row,
            ) as connection:
                states = connection.execute(
                    """
                    SELECT 'execution' AS journey, status AS value, count(*) AS total
                    FROM synergia.executions GROUP BY status
                    UNION ALL
                    SELECT 'inspection', decision, count(*)
                    FROM synergia.file_inspections GROUP BY decision
                    UNION ALL
                    SELECT 'report', state, count(*)
                    FROM synergia.report_versions GROUP BY state
                    UNION ALL
                    SELECT 'notification', state, count(*)
                    FROM synergia.notifications GROUP BY state
                    UNION ALL
                    SELECT 'email', state, count(*)
                    FROM synergia.email_deliveries GROUP BY state
                    UNION ALL
                    SELECT 'approval', state, count(*)
                    FROM synergia.approval_requests GROUP BY state
                    """
                ).fetchall()
                events = connection.execute(
                    """
                    SELECT 'execution' AS journey, status AS value, count(*) AS total
                    FROM synergia.executions
                    WHERE status IN ('completed', 'completed_with_errors',
                                     'validation_failed', 'failed', 'duplicate', 'cancelled')
                    GROUP BY status
                    UNION ALL
                    SELECT 'inspection', decision, count(*)
                    FROM synergia.file_inspections GROUP BY decision
                    UNION ALL
                    SELECT 'report', replace(event_type, 'report.', ''), count(*)
                    FROM synergia.report_events GROUP BY event_type
                    UNION ALL
                    SELECT 'notification', replace(event_type, 'notification.', ''), count(*)
                    FROM synergia.notification_events GROUP BY event_type
                    UNION ALL
                    SELECT 'email', outcome, count(*)
                    FROM synergia.email_delivery_attempts GROUP BY outcome
                    UNION ALL
                    SELECT 'approval', event_type, count(*)
                    FROM synergia.approval_events GROUP BY event_type
                    UNION ALL
                    SELECT 'reprocessing', 'requested', count(*)
                    FROM synergia.execution_idempotency WHERE request_type = 'reprocess'
                    """
                ).fetchall()
                queues = connection.execute(
                    """
                    SELECT 'execution' AS queue, status AS value, count(*) AS total
                    FROM synergia.executions
                    WHERE status IN ('pending', 'validating', 'normalizing',
                                     'consolidating', 'applying_rules', 'reprocessing')
                    GROUP BY status
                    UNION ALL
                    SELECT 'report', state, count(*) FROM synergia.report_versions
                    WHERE state = 'generating' GROUP BY state
                    UNION ALL
                    SELECT 'email', state, count(*) FROM synergia.email_deliveries
                    WHERE state IN ('queued', 'processing', 'retry') GROUP BY state
                    UNION ALL
                    SELECT 'approval', state, count(*) FROM synergia.approval_requests
                    WHERE state IN ('draft', 'submitted', 'in_review', 'returned')
                    GROUP BY state
                    """
                ).fetchall()
                ages = connection.execute(
                    """
                    SELECT 'execution' AS queue,
                           COALESCE(EXTRACT(EPOCH FROM now() - min(started_at)), 0) AS seconds
                    FROM synergia.executions
                    WHERE status IN ('pending', 'validating', 'normalizing',
                                     'consolidating', 'applying_rules', 'reprocessing')
                    UNION ALL
                    SELECT 'report', COALESCE(EXTRACT(EPOCH FROM now() - min(created_at)), 0)
                    FROM synergia.report_versions WHERE state = 'generating'
                    UNION ALL
                    SELECT 'email', COALESCE(EXTRACT(EPOCH FROM now() -
                           min(COALESCE(claimed_at, available_at))), 0)
                    FROM synergia.email_deliveries
                    WHERE state IN ('queued', 'processing', 'retry')
                    UNION ALL
                    SELECT 'approval', COALESCE(EXTRACT(EPOCH FROM now() - min(updated_at)), 0)
                    FROM synergia.approval_requests
                    WHERE state IN ('draft', 'submitted', 'in_review', 'returned')
                    """
                ).fetchall()
                durations = connection.execute(
                    """
                    SELECT 'execution' AS journey,
                           COALESCE(avg(EXTRACT(EPOCH FROM finished_at - started_at)), 0) AS average,
                           COALESCE(max(EXTRACT(EPOCH FROM finished_at - started_at)), 0) AS maximum
                    FROM synergia.executions WHERE finished_at IS NOT NULL
                    UNION ALL
                    SELECT 'report',
                           COALESCE(avg(EXTRACT(EPOCH FROM completed_at - created_at)), 0),
                           COALESCE(max(EXTRACT(EPOCH FROM completed_at - created_at)), 0)
                    FROM synergia.report_versions WHERE completed_at IS NOT NULL
                    UNION ALL
                    SELECT 'email',
                           COALESCE(avg(EXTRACT(EPOCH FROM sent_at - created_at)), 0),
                           COALESCE(max(EXTRACT(EPOCH FROM sent_at - created_at)), 0)
                    FROM synergia.email_deliveries WHERE sent_at IS NOT NULL
                    UNION ALL
                    SELECT 'approval',
                           COALESCE(avg(EXTRACT(EPOCH FROM decided_at - created_at)), 0),
                           COALESCE(max(EXTRACT(EPOCH FROM decided_at - created_at)), 0)
                    FROM synergia.approval_requests WHERE decided_at IS NOT NULL
                    """
                ).fetchall()
                import_rows = connection.execute(
                    """
                    SELECT COALESCE(sum(rows_read), 0) AS rows_read,
                           COALESCE(sum(valid_records), 0) AS valid_records,
                           COALESCE(sum(rejected_records), 0) AS rejected_records,
                           COALESCE(sum(normalized_records), 0) AS normalized_records
                    FROM synergia.pipeline_summaries
                    """
                ).fetchone()
                rate_denials = connection.execute(
                    """
                    SELECT operation, dimension, count(*) AS total
                    FROM synergia.rate_limit_events GROUP BY operation, dimension
                    """
                ).fetchall()
        except (psycopg.Error, OSError, ValueError) as exc:
            collection.add_metric(["postgresql"], 0)
            safe_log(
                logging.ERROR,
                "observability.collection.failed",
                component="postgresql",
                exception_type=type(exc).__name__,
            )
            yield collection
            return

        collection.add_metric(["postgresql"], 1)
        yield collection

        state_metric = GaugeMetricFamily(
            "synergia_operational_records",
            "Current persisted records by journey and bounded state.",
            labels=["journey", "state"],
        )
        for row in states:
            journey = row["journey"]
            state_metric.add_metric(
                [journey, _bounded(row["value"], _SAFE_STATES[journey])], row["total"]
            )
        yield state_metric

        event_metric = CounterMetricFamily(
            "synergia_operational_events",
            "Persisted operational outcomes by journey.",
            labels=["journey", "outcome"],
        )
        for row in events:
            journey = row["journey"]
            event_metric.add_metric(
                [journey, _bounded(row["value"], _SAFE_OUTCOMES[journey])], row["total"]
            )
        yield event_metric

        queue_metric = GaugeMetricFamily(
            "synergia_queue_depth",
            "Current queue depth by bounded state.",
            labels=["queue", "state"],
        )
        for row in queues:
            queue = row["queue"]
            queue_metric.add_metric(
                [queue, _bounded(row["value"], _SAFE_STATES[queue])], row["total"]
            )
        yield queue_metric

        age_metric = GaugeMetricFamily(
            "synergia_queue_oldest_age_seconds",
            "Age in seconds of the oldest queued item.",
            labels=["queue"],
        )
        for row in ages:
            age_metric.add_metric([row["queue"]], max(float(row["seconds"]), 0))
        yield age_metric

        duration_metric = GaugeMetricFamily(
            "synergia_operation_duration_seconds",
            "Persisted operation duration summary.",
            labels=["journey", "statistic"],
        )
        for row in durations:
            duration_metric.add_metric([row["journey"], "average"], float(row["average"]))
            duration_metric.add_metric([row["journey"], "maximum"], float(row["maximum"]))
        yield duration_metric

        row_metric = CounterMetricFamily(
            "synergia_import_rows",
            "Persisted import row volume by outcome.",
            labels=["outcome"],
        )
        for key in ("rows_read", "valid_records", "rejected_records", "normalized_records"):
            row_metric.add_metric([key], int(import_rows[key]))
        yield row_metric

        denial_metric = CounterMetricFamily(
            "synergia_rate_limit_denials",
            "Persisted rate-limit denials without subject identifiers.",
            labels=["operation", "dimension"],
        )
        for row in rate_denials:
            denial_metric.add_metric(
                [
                    _bounded(row["operation"], _SAFE_RATE_OPERATIONS),
                    _bounded(row["dimension"], _SAFE_RATE_DIMENSIONS),
                ],
                row["total"],
            )
        yield denial_metric


REGISTRY.register(PostgresOperationalCollector())


def render_metrics() -> bytes:
    return generate_latest(REGISTRY)
