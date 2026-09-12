from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from app.rate_limiting import PostgresRateLimiter, RatePolicy

pytestmark = [pytest.mark.integration, pytest.mark.real_rate_limit]


def test_atomic_limit_concurrency_audit_and_isolation() -> None:
    database_url = os.environ["DATABASE_URL"]
    limiter = PostgresRateLimiter(database_url, "integration-secret-" + "x" * 32)
    operation = f"test-{uuid4().hex}"
    policy = RatePolicy(operation, 5, 60, True)

    def consume() -> int | None:
        return limiter.consume(policy, "user", "same-user", uuid4(), "POST")

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda _: consume(), range(10)))

    assert results.count(None) == 5
    assert len([value for value in results if value is not None]) == 5
    assert limiter.consume(policy, "user", "other-user", uuid4(), "POST") is None

    with psycopg.connect(database_url) as connection:
        bucket = connection.execute(
            """
            SELECT request_count, denied_count
            FROM synergia.rate_limit_buckets
            WHERE operation = %s AND dimension = 'user' AND key_hash = %s
            """,
            (operation, limiter.digest("same-user")),
        ).fetchone()
        events = connection.execute(
            """
            SELECT count(*), bool_and(route_group = %s)
            FROM synergia.rate_limit_events WHERE operation = %s
            """,
            (operation, operation),
        ).fetchone()
    assert bucket == (10, 5)
    assert events == (5, True)


def test_expired_window_recovers_without_changing_key() -> None:
    database_url = os.environ["DATABASE_URL"]
    limiter = PostgresRateLimiter(database_url, "integration-secret-" + "y" * 32)
    operation = f"recovery-{uuid4().hex}"
    policy = RatePolicy(operation, 1, 60, True)
    assert limiter.consume(policy, "origin", "192.0.2.1", None, "POST") is None
    assert limiter.consume(policy, "origin", "192.0.2.1", None, "POST") is not None
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            UPDATE synergia.rate_limit_buckets
            SET window_expires_at = now() - interval '1 second',
                window_started_at = now() - interval '61 seconds'
            WHERE operation = %s
            """,
            (operation,),
        )
    assert limiter.consume(policy, "origin", "192.0.2.1", None, "POST") is None
