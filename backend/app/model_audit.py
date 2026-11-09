"""Persist only model execution metadata; never prompts, responses or evidence."""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg

from app.errors import ApiError


class ModelAuditRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def record(self, actor, operation_id, action, *, duration_ms=None, fallback=False):
        from app.ai_quality import MODEL, MODEL_DIGEST

        if not self.database_url:
            raise ApiError(503, "model_audit_unavailable", "Auditoria indisponivel")
        try:
            with psycopg.connect(self.database_url, connect_timeout=3) as connection:
                connection.execute("SET LOCAL statement_timeout = '3s'")
                connection.execute(
                    """INSERT INTO synergia.observability_events
                    (id, action, actor_user_id, correlation_id, operation_id,
                     model_name, model_digest, duration_ms, fallback)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        uuid4(),
                        action,
                        actor.user_id,
                        actor.correlation_id,
                        operation_id,
                        MODEL,
                        MODEL_DIGEST,
                        duration_ms,
                        fallback,
                    ),
                )
        except (psycopg.Error, OSError) as exc:
            raise ApiError(
                503, "model_audit_unavailable", "Auditoria indisponivel"
            ) from exc


def get_model_audit_repository():
    database_url = os.getenv("DATABASE_URL", "").strip()
    return ModelAuditRepository(database_url)
