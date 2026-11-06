"""Database-only aggregates; scraping never contacts Graylog or reads its secret."""

from __future__ import annotations

import os

import psycopg
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily


class GraylogCollector:
    def collect(self):
        success = GaugeMetricFamily(
            "synergia_graylog_collection_success",
            "Collector state could be read.",
        )
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            success.add_metric([], 0)
            yield success
            return
        try:
            with psycopg.connect(database_url, connect_timeout=2) as connection:
                connection.execute("SET LOCAL statement_timeout = '2s'")
                counts = connection.execute(
                    "SELECT state, count(*) FROM synergia.graylog_deliveries "
                    "GROUP BY state"
                ).fetchall()
                age = connection.execute(
                    """SELECT COALESCE(max(EXTRACT(EPOCH FROM
                    clock_timestamp() - occurred_at)), 0)
                    FROM synergia.graylog_deliveries WHERE state <> 'accepted'"""
                ).fetchone()[0]
                events = connection.execute(
                    """SELECT action, count(*) FROM synergia.graylog_delivery_history
                    GROUP BY action"""
                ).fetchall()
                last_run = connection.execute(
                    "SELECT EXTRACT(EPOCH FROM last_run_at) "
                    "FROM synergia.graylog_control"
                ).fetchone()
        except (psycopg.Error, OSError):
            success.add_metric([], 0)
            yield success
            return
        success.add_metric([], 1)
        yield success
        queue = GaugeMetricFamily(
            "synergia_graylog_queue",
            "Persisted deliveries by state.",
            labels=["state"],
        )
        by_state = dict(counts)
        for state in (
            "pending",
            "inflight",
            "accepted",
            "uncertain",
            "blocked",
            "exhausted",
        ):
            queue.add_metric([state], by_state.get(state, 0))
        yield queue
        lag = GaugeMetricFamily(
            "synergia_graylog_oldest_age_seconds", "Oldest unaccepted event."
        )
        lag.add_metric([], max(0, float(age)))
        yield lag
        outcomes = CounterMetricFamily(
            "synergia_graylog_delivery_results",
            "Persisted delivery transitions.",
            labels=["result"],
        )
        by_action = dict(events)
        for action in (
            "intent",
            "accepted",
            "pending",
            "blocked",
            "uncertain",
            "exhausted",
            "confirm_received",
            "confirm_absent",
            "requeue",
        ):
            outcomes.add_metric([action], by_action.get(action, 0))
        yield outcomes
        heartbeat = GaugeMetricFamily(
            "synergia_graylog_last_run_timestamp_seconds",
            "Last completed collector batch.",
        )
        heartbeat.add_metric([], float(last_run[0] or 0) if last_run else 0)
        yield heartbeat
