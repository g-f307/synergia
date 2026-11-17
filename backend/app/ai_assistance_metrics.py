"""Read-only persisted aggregates. Scraping never calls a model or a worker."""

from __future__ import annotations

import os

import psycopg
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from psycopg.rows import dict_row

from app.ai_assistance_config import AiAssistanceConfig


def environment():
    value = os.getenv("SYNERGIA_ENV", "development")
    return (
        value
        if value in {"development", "test", "homologation", "production"}
        else "unknown"
    )


def _gauge(name, help_text, env, value):
    metric = GaugeMetricFamily(
        "synergia_ai_assistance_" + name, help_text, labels=["environment"]
    )
    metric.add_metric([env], max(float(value or 0), 0))
    return metric


class AiAssistanceCollector:
    def collect(self):
        env = environment()
        try:
            config = AiAssistanceConfig.from_environment(os.environ)
            enabled, generation = (
                config.enabled,
                config.enabled and config.generation_enabled,
            )
        except ValueError:
            enabled = generation = False
        yield _gauge("enabled", "General assistance flag.", env, enabled)
        yield _gauge(
            "generation_enabled", "New generation admission flag.", env, generation
        )
        url = os.getenv("DATABASE_URL", "").strip()
        if not url:
            yield _gauge(
                "collection_success",
                "Persisted assistance metrics could be read.",
                env,
                0,
            )
            return
        try:
            with psycopg.connect(
                url, connect_timeout=2, row_factory=dict_row
            ) as connection:
                connection.execute("SET TRANSACTION READ ONLY")
                connection.execute("SET LOCAL statement_timeout='2s'")
                leases = connection.execute(
                    """SELECT count(*) AS pending,
                    count(*) FILTER (
                        WHERE reservation_until <= clock_timestamp()) AS expired,
                    COALESCE(max(extract(epoch FROM
                        clock_timestamp()-created_at)),0) AS age
                    FROM synergia.ai_assistances WHERE state='processing'"""
                ).fetchone()
                events = connection.execute(
                    """SELECT action,state,count(*) AS total,
                    max(extract(epoch FROM occurred_at)) AS stamp
                    FROM synergia.ai_assistance_events
                    WHERE action IN ('expired','completed','rejected','integrity_error')
                    GROUP BY action,state"""
                ).fetchall()
                runs = connection.execute(
                    """SELECT dataset,outcome,count(*) AS total,
                    max(extract(epoch FROM occurred_at)) AS stamp,
                    COALESCE(sum(record_count),0) AS records
                    FROM synergia.data_operation_events
                    WHERE dataset IN (
                        'ai_assistance_results','ai_assistance_reservations')
                    GROUP BY dataset,outcome"""
                ).fetchall()
                unfinished = connection.execute(
                    """SELECT s.dataset,count(*) AS total
                    FROM synergia.data_operation_events s
                    WHERE s.dataset IN (
                        'ai_assistance_results','ai_assistance_reservations')
                      AND s.outcome='started' AND NOT EXISTS (
                        SELECT 1 FROM synergia.data_operation_events f
                        WHERE f.correlation_id=s.correlation_id AND f.dataset=s.dataset
                          AND f.outcome IN ('succeeded','failed')) GROUP BY s.dataset"""
                ).fetchall()
        except (psycopg.Error, OSError):
            yield _gauge(
                "collection_success",
                "Persisted assistance metrics could be read.",
                env,
                0,
            )
            return
        yield _gauge(
            "collection_success", "Persisted assistance metrics could be read.", env, 1
        )
        yield _gauge(
            "pending_reservations",
            "Processing leases, including expired leases; not an inference queue.",
            env,
            leases["pending"],
        )
        yield _gauge(
            "expired_reservations",
            "Expired processing leases awaiting release.",
            env,
            leases["expired"],
        )
        yield _gauge(
            "oldest_reservation_age_seconds",
            "Oldest processing lease age.",
            env,
            leases["age"],
        )
        counts = {(r["action"], r["state"]): r["total"] for r in events}
        recovered = CounterMetricFamily(
            "synergia_ai_assistance_reservations_recovered",
            "Durably released expired processing leases.",
            labels=["environment"],
        )
        recovered.add_metric([env], counts.get(("expired", "processing"), 0))
        yield recovered
        integrity = CounterMetricFamily(
            "synergia_ai_assistance_persisted_integrity_errors",
            "Durable read-integrity incidents.",
            labels=["environment"],
        )
        integrity.add_metric(
            [env], sum(r["total"] for r in events if r["action"] == "integrity_error")
        )
        yield integrity
        completions = CounterMetricFamily(
            "synergia_ai_assistance_persisted_completions",
            "Durable concluded generations, not HTTP outcomes.",
            labels=["environment"],
        )
        completions.add_metric(
            [env],
            sum(r["total"] for r in events if r["action"] in {"completed", "rejected"}),
        )
        yield completions
        yield _gauge(
            "last_completion_timestamp_seconds",
            "Last durable completed/rejected event; zero if none.",
            env,
            max(
                (
                    r["stamp"]
                    for r in events
                    if r["action"] in {"completed", "rejected"}
                ),
                default=0,
            ),
        )
        for operation, dataset in (
            ("retention", "ai_assistance_results"),
            ("recovery", "ai_assistance_reservations"),
        ):
            by_result = {r["outcome"]: r for r in runs if r["dataset"] == dataset}
            metric = CounterMetricFamily(
                "synergia_ai_assistance_" + operation + "_runs",
                "Durable effective maintenance runs; dry-runs excluded.",
                labels=["environment", "result"],
            )
            for result in ("started", "succeeded", "failed"):
                metric.add_metric(
                    [env, result], by_result.get(result, {}).get("total", 0)
                )
            yield metric
            for result, suffix in (
                ("started", "last_started"),
                ("succeeded", "last_success"),
                ("failed", "last_failure"),
            ):
                yield _gauge(
                    operation + "_" + suffix + "_timestamp_seconds",
                    "Last durable worker transition.",
                    env,
                    by_result.get(result, {}).get("stamp", 0),
                )
            yield _gauge(
                operation + "_unfinished_runs",
                "Started worker runs without durable terminal result.",
                env,
                next((r["total"] for r in unfinished if r["dataset"] == dataset), 0),
            )
            deleted = CounterMetricFamily(
                "synergia_ai_assistance_" + operation + "_removed_records",
                "Records removed by committed worker batches.",
                labels=["environment"],
            )
            deleted.add_metric([env], by_result.get("succeeded", {}).get("records", 0))
            yield deleted
