"""Bounded read-only projection of the existing execution repositories' tables."""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.ai_assistance_context_models import Section


class ContextReadSession(Protocol):
    def subject(
        self, execution_id: str, scopes: frozenset[UUID] | None
    ) -> dict | None: ...
    def counts(self, execution_id: str, organization_id: UUID) -> dict: ...
    def items(
        self, section: Section, execution_id: str, organization_id: UUID
    ) -> list: ...


class ContextReader(Protocol):
    def snapshot(self) -> AbstractContextManager[ContextReadSession]: ...


SUBJECT_SQL = """SELECT e.id AS execution_id, e.organization_id, e.source, e.status,
    e.attempt, e.pipeline_version, e.rule_catalog_version, e.started_at, e.finished_at
    FROM synergia.executions e WHERE e.id = %s
    AND (%s::uuid[] IS NULL OR e.organization_id = ANY(%s::uuid[]))
    AND e.organization_id IS NOT NULL"""

COLLECTION_SQL = {
    "divergences": """SELECT t.id, t.severity, t.code, t.scope,
        t.created_at AS occurred_at FROM synergia.pipeline_issues t
        JOIN synergia.executions e ON e.id = t.execution_id
        WHERE t.execution_id = %s AND e.organization_id = %s
        ORDER BY CASE t.severity WHEN 'error' THEN 0 ELSE 1 END,
                 t.created_at, t.id LIMIT 21""",
    "pending_items": """SELECT t.id, t.rule_id, t.status, t.priority_score, t.created_at
        FROM synergia.pending_items t
        JOIN synergia.executions e ON e.id = t.execution_id
        WHERE t.execution_id = %s AND e.organization_id = %s
        ORDER BY t.priority_score DESC NULLS LAST, t.created_at, t.id LIMIT 21""",
    "classifications": """SELECT t.classification_id AS id, t.rule_id, t.state,
        t.data_quality, t.priority_score, t.classified_at
        FROM synergia.classifications t
        JOIN synergia.executions e ON e.id = t.execution_id
        WHERE t.execution_id = %s AND e.organization_id = %s
        ORDER BY t.classified_at, t.classification_id COLLATE "C" LIMIT 21""",
    "evidences": """SELECT t.id, t.extension, t.size_bytes, t.content_hash AS sha256,
        (fi.decision = 'accepted' AND fi.discarded_at IS NULL
         AND t.storage_key IS NOT NULL) IS TRUE AS available
        FROM synergia.source_files t
        JOIN synergia.executions e ON e.id = t.execution_id
        LEFT JOIN synergia.file_inspections fi
          ON fi.id = t.inspection_id AND fi.execution_id = t.execution_id
        WHERE t.execution_id = %s AND e.organization_id = %s
        ORDER BY t.id LIMIT 21""",
    "state_history": """SELECT t.id, t.from_state, t.to_state, t.state_version,
        t.occurred_at FROM synergia.execution_state_transitions t
        JOIN synergia.executions e ON e.id = t.execution_id
        WHERE t.execution_id = %s AND e.organization_id = %s
        ORDER BY t.occurred_at DESC, t.id DESC LIMIT 11""",
}

# Same counters as PostgresQueryRepository.get_execution, with a tenant-bound
# outer execution. Each scalar subquery is independent of collection cardinality.
COUNT_SOURCES = {
    "files": ("file_inspections", "count(*)", ""),
    "files_received": ("file_inspections", "count(*)", ""),
    "files_accepted": ("file_inspections", "count(*)", " AND decision='accepted'"),
    "files_rejected": ("file_inspections", "count(*)", " AND decision='rejected'"),
    "rows_read": ("pipeline_summaries", "COALESCE(sum(rows_read),0)", ""),
    "valid_records": ("pipeline_summaries", "COALESCE(sum(valid_records),0)", ""),
    "rejected_records": ("pipeline_summaries", "COALESCE(sum(rejected_records),0)", ""),
    "normalized_records": ("normalized_records", "count(*)", ""),
    "workorders": ("workorders", "count(*)", ""),
    "lots": ("lots", "count(*)", ""),
    "serials": ("serials", "count(*)", ""),
    "classifications": ("classifications", "count(*)", ""),
    "pending_items": ("pending_items", "count(*)", ""),
    "errors": ("pipeline_issues", "count(*)", " AND severity='error'"),
    "warnings": ("pipeline_issues", "count(*)", " AND severity='warning'"),
}
COUNTS_SQL = (
    "SELECT "
    + ", ".join(
        f"(SELECT {aggregate} FROM synergia.{table} t "
        f"WHERE t.execution_id=e.id{suffix}) AS {name}"
        for name, (table, aggregate, suffix) in COUNT_SOURCES.items()
    )
    + " FROM synergia.executions e WHERE e.id=%s AND e.organization_id=%s"
)


class PostgresContextSession:
    def __init__(self, connection):
        self.connection = connection

    def subject(self, execution_id: str, scopes: frozenset[UUID] | None) -> dict | None:
        organizations = None if scopes is None else sorted(scopes, key=str)
        return self.connection.execute(
            SUBJECT_SQL, (execution_id, organizations, organizations)
        ).fetchone()

    def counts(self, execution_id: str, organization_id: UUID) -> dict:
        return self.connection.execute(
            COUNTS_SQL, (execution_id, organization_id)
        ).fetchone()

    def items(self, section: Section, execution_id: str, organization_id: UUID) -> list:
        return self.connection.execute(
            COLLECTION_SQL[section], (execution_id, organization_id)
        ).fetchall()


class PostgresContextReader:
    def __init__(self, database_url: str):
        self.database_url = database_url

    @contextmanager
    def snapshot(self) -> Iterator[PostgresContextSession]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            # Subject authorization and every detail share the same MVCC snapshot.
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            yield PostgresContextSession(connection)
