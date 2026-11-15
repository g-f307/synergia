"""Shared sliding rate and in-flight limits for assistance requests."""

from contextlib import contextmanager
from math import ceil

import psycopg

from app.errors import ApiError
from app.rate_limiting import PostgresRateLimiter


class AssistanceLimits:
    def __init__(self, database_url: str, secret: str):
        if len(secret.encode()) < 32:
            raise ValueError("invalid rate limit configuration")
        self.database_url = database_url
        self.limiter = PostgresRateLimiter(database_url, secret)

    def _key(self, kind, value):
        digest = self.limiter.digest(f"ai-assistance:{kind}:{value}")
        lock = int.from_bytes(bytes.fromhex(digest[:16]), "big", signed=True)
        return digest, lock

    def consume(self, actor, organization_id):
        keys = [
            (kind, *self._key(kind, value))
            for kind, value in (
                ("user", actor.user_id),
                ("organization", organization_id),
            )
        ]
        with psycopg.connect(self.database_url) as connection:
            for lock in sorted(key[2] for key in keys):
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
            # Bounded cleanup prevents indefinite growth without a separate worker.
            connection.execute("""DELETE FROM synergia.ai_assistance_rate_attempts
                WHERE ctid IN (SELECT ctid FROM synergia.ai_assistance_rate_attempts
                WHERE occurred_at < clock_timestamp() - interval '10 minutes'
                LIMIT 1000)""")
            for kind, digest, _ in keys:
                count, retry = connection.execute(
                    """SELECT count(*),
                    extract(epoch from min(occurred_at) + interval '10 minutes'
                            - clock_timestamp())
                    FROM synergia.ai_assistance_rate_attempts
                    WHERE dimension=%s AND key_hash=%s
                      AND occurred_at > clock_timestamp() - interval '10 minutes'""",
                    (kind, digest),
                ).fetchone()
                if count >= 10:
                    raise ApiError(
                        429,
                        "rate_limit_exceeded",
                        "Limite de solicitações excedido",
                        headers={"Retry-After": str(max(1, ceil(retry)))},
                    )
            for kind, digest, _ in keys:
                connection.execute(
                    """INSERT INTO synergia.ai_assistance_rate_attempts
                    (dimension, key_hash) VALUES (%s, %s)""",
                    (kind, digest),
                )

    @contextmanager
    def generation(self, actor, organization_id):
        self.consume(actor, organization_id)
        # Session locks are shared across workers with no open transaction while
        # inference runs. Closing the connection releases locks on all exits.
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            for kind, value in (
                ("user", actor.user_id),
                ("organization", organization_id),
            ):
                _, key = self._key(f"flight-{kind}", value)
                if not connection.execute(
                    "SELECT pg_try_advisory_lock(%s)", (key,)
                ).fetchone()[0]:
                    raise ApiError(
                        409, "ai_assistance_in_progress", "Geração em andamento"
                    )
            yield
