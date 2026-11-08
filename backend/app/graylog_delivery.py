"""Durable source checkpoints and bounded delivery, independent of HTTP requests."""

from __future__ import annotations

import random
from contextlib import contextmanager
from datetime import timedelta

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.audit import ORIGINS, sanitize_event
from app.errors import ApiError
from app.graylog import GraylogError, stable_id, to_gelf

LOCK_ID = 7_347_319_178


class GraylogRepository:
    def __init__(self, database_url):
        self.database_url = database_url

    @contextmanager
    def locked(self):
        with psycopg.connect(
            self.database_url,
            autocommit=True,
            connect_timeout=3,
            row_factory=dict_row,
        ) as connection:
            connection.execute("SET statement_timeout = '5s'")
            acquired = connection.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired",
                (LOCK_ID,),
            ).fetchone()["acquired"]
            if not acquired:
                raise GraylogError("collector_busy")
            try:
                yield connection
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))

    @staticmethod
    def bind(connection, config):
        with connection.transaction():
            connection.execute(
                """INSERT INTO synergia.graylog_control (destination_hash)
                VALUES (%s) ON CONFLICT DO NOTHING""",
                (config.destination_hash(),),
            )
            current = connection.execute(
                "SELECT destination_hash FROM synergia.graylog_control"
            ).fetchone()["destination_hash"]
            if current != config.destination_hash():
                raise GraylogError("destination_or_scope_changed")

    @staticmethod
    def history(connection, key, action, code, operator=None, evidence=None):
        connection.execute(
            """INSERT INTO synergia.graylog_delivery_history
            (event_key, action, code, operator_id, evidence_id)
            VALUES (%s, %s, %s, %s, %s)""",
            (key, action, code, operator, evidence),
        )

    def recover(self, connection):
        # Persisted intent without a result can have been accepted remotely.
        with connection.transaction():
            rows = connection.execute(
                """UPDATE synergia.graylog_deliveries SET state = 'uncertain',
                last_code = 'interrupted_intent', updated_at = clock_timestamp()
                WHERE state = 'inflight' RETURNING event_key"""
            ).fetchall()
            for row in rows:
                self.history(
                    connection, row["event_key"], "uncertain", "interrupted_intent"
                )

    @staticmethod
    def candidates(connection, batch_size):
        return connection.execute(
            """SELECT * FROM synergia.graylog_deliveries
            WHERE state = 'pending' AND next_attempt_at <= clock_timestamp()
            ORDER BY created_at, event_key COLLATE "C" LIMIT %s""",
            (batch_size,),
        ).fetchall()

    def prepare(self, connection, row, config):
        key = row["event_key"]
        event_id = stable_id(row["origin"], key, row["occurred_at"])
        if row["attempts"] >= config.max_attempts:
            self.finish(
                connection,
                key,
                "exhausted",
                "attempt_budget_exhausted",
                event_id=event_id,
            )
            return None
        # Reapply scope/field policy to every attempt. Never trust a queued payload
        # to bypass sanitization. Missing/deleted sources remain blocked for review.
        source = (
            row["source_snapshot"]
            or connection.execute(
                """SELECT * FROM synergia.audit_event_catalog
            WHERE origin = %s AND id = %s""",
                (row["origin"], key),
            ).fetchone()
        )
        try:
            if source is None:
                raise GraylogError("source_unavailable")
            payload = to_gelf(source, config)
        except (GraylogError, ApiError, ValidationError, KeyError, TypeError) as exc:
            # Invalid source content is durable and visible; it never goes to GELF.
            # Report only our stable code, never Pydantic/source exception text.
            code = (
                str(exc) if isinstance(exc, GraylogError) else "source_contract_invalid"
            )
            self.finish(connection, key, "blocked", code, event_id=event_id)
            return None
        with connection.transaction():
            connection.execute(
                """UPDATE synergia.graylog_deliveries SET state = 'inflight',
                payload = %s, event_id = %s, attempts = attempts + 1,
                updated_at = clock_timestamp(), last_code = 'intent'
                WHERE event_key = %s AND state = 'pending'""",
                (Jsonb(payload), event_id, key),
            )
            self.history(connection, key, "intent", "intent")
        return payload

    def finish(self, connection, key, state, code, *, delay=0, event_id=None):
        with connection.transaction():
            connection.execute(
                """UPDATE synergia.graylog_deliveries SET state = %s,
                last_code = %s, updated_at = clock_timestamp(),
                event_id = COALESCE(event_id, %s),
                accepted_at = CASE WHEN %s = 'accepted' THEN clock_timestamp()
                                   ELSE accepted_at END,
                next_attempt_at = clock_timestamp() + %s * interval '1 second'
                WHERE event_key = %s""",
                (state, code, event_id, state, delay, key),
            )
            self.history(connection, key, state, code)

    def backfill(self, connection, origin, start, end, limit, operator, evidence):
        if origin not in ORIGINS or not timedelta(0) < end - start <= timedelta(
            days=31
        ):
            raise GraylogError("window_invalid")
        with connection.transaction():
            connection.execute(
                """INSERT INTO synergia.graylog_scan_windows
                (origin, window_start, window_end, operator_id, evidence_id)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (origin, start, end, operator, evidence),
            )
            window = connection.execute(
                """SELECT * FROM synergia.graylog_scan_windows
                WHERE origin = %s AND window_start = %s AND window_end = %s
                FOR UPDATE""",
                (origin, start, end),
            ).fetchone()
            if window["completed"]:
                return 0, True
            rows = connection.execute(
                """SELECT * FROM synergia.audit_event_catalog
                WHERE origin = %s AND occurred_at >= %s AND occurred_at < %s
                AND (%s::timestamptz IS NULL OR
                    (occurred_at, id COLLATE "C") > (%s, %s COLLATE "C"))
                ORDER BY occurred_at, id COLLATE "C" LIMIT %s""",
                (
                    origin,
                    start,
                    end,
                    window["cursor_time"],
                    window["cursor_time"],
                    window["cursor_key"],
                    limit,
                ),
            ).fetchall()
            for row in rows:
                try:
                    snapshot = sanitize_event(row).model_dump(mode="json")
                    state = "pending"
                except (ApiError, ValidationError, KeyError, TypeError):
                    snapshot, state = None, "blocked"
                inserted = connection.execute(
                    """INSERT INTO synergia.graylog_deliveries
                    (event_key, origin, occurred_at, source_snapshot, event_id, state,
                     last_code)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING""",
                    (
                        row["id"],
                        origin,
                        row["occurred_at"],
                        Jsonb(snapshot) if snapshot is not None else None,
                        stable_id(origin, row["id"], row["occurred_at"]),
                        state,
                        "source_contract_invalid" if state == "blocked" else None,
                    ),
                )
                if state == "blocked" and inserted.rowcount:
                    self.history(
                        connection, row["id"], "blocked", "source_contract_invalid"
                    )
            completed = len(rows) < limit
            connection.execute(
                """UPDATE synergia.graylog_scan_windows SET cursor_time = %s,
                cursor_key = %s, completed = %s
                WHERE origin = %s AND window_start = %s AND window_end = %s""",
                (
                    rows[-1]["occurred_at"] if rows else window["cursor_time"],
                    rows[-1]["id"] if rows else window["cursor_key"],
                    completed,
                    origin,
                    start,
                    end,
                ),
            )
        return len(rows), completed

    def reconcile(self, connection, event_id, resolution, operator, evidence):
        if resolution not in {"confirm_received", "confirm_absent", "requeue"}:
            raise GraylogError("resolution_invalid")
        with connection.transaction():
            row = connection.execute(
                """SELECT * FROM synergia.graylog_deliveries
                WHERE event_id = %s FOR UPDATE""",
                (event_id,),
            ).fetchone()
            if row is None:
                raise GraylogError("event_not_found")
            if (
                resolution == "confirm_received"
                and row["state"] in {"uncertain", "accepted"}
                and row["confirmed_at"] is None
            ):
                target = "accepted"
            elif resolution == "confirm_absent" and row["state"] == "uncertain":
                target = "pending"
            elif resolution == "requeue" and row["state"] in {"blocked", "exhausted"}:
                target = "pending"
            else:
                raise GraylogError("reconciliation_state_invalid")
            connection.execute(
                """UPDATE synergia.graylog_deliveries SET state = %s,
                attempts = CASE WHEN %s = 'pending' THEN 0 ELSE attempts END,
                payload = NULL, last_code = %s,
                next_attempt_at = clock_timestamp(), updated_at = clock_timestamp(),
                accepted_at = CASE WHEN %s = 'accepted' THEN clock_timestamp()
                                   ELSE accepted_at END,
                confirmed_at = CASE WHEN %s = 'confirm_received' THEN clock_timestamp()
                                    ELSE confirmed_at END
                WHERE event_key = %s""",
                (target, target, resolution, target, resolution, row["event_key"]),
            )
            self.history(
                connection, row["event_key"], resolution, resolution, operator, evidence
            )

    @staticmethod
    def status(connection):
        counts = {
            state: 0
            for state in (
                "pending",
                "inflight",
                "accepted",
                "uncertain",
                "blocked",
                "exhausted",
            )
        }
        for row in connection.execute(
            "SELECT state, count(*) AS total FROM synergia.graylog_deliveries "
            "GROUP BY state"
        ):
            counts[row["state"]] = row["total"]
        return counts


def run_batch(repository, config, transport, *, jitter=random.uniform):
    if not config.enabled:
        return {"status": "disabled", "processed": 0}
    result = {"status": "completed", "processed": 0, "accepted": 0}
    with repository.locked() as connection:
        repository.bind(connection, config)
        repository.recover(connection)
        for row in repository.candidates(connection, config.batch_size):
            payload = repository.prepare(connection, row, config)
            if payload is None:
                continue
            # Intent is committed before the first byte can leave the process.
            delivered = transport.send(payload)
            state, code = delivered.state, delivered.code
            attempt = row["attempts"] + 1
            if state == "pending" and attempt >= config.max_attempts:
                state = "exhausted"
            delay = min(config.retry_seconds * 2 ** (attempt - 1), 3600)
            delay = min(3600, delay + jitter(0, delay / 4))
            repository.finish(connection, row["event_key"], state, code, delay=delay)
            result["processed"] += 1
            result["accepted"] += state == "accepted"
        result["queue"] = repository.status(connection)
        connection.execute(
            "UPDATE synergia.graylog_control SET last_run_at = clock_timestamp()"
        )
    return result
