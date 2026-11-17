"""Shared persisted-issue filters and ordering, with explicit consumer projections."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg


@dataclass(frozen=True)
class PipelineIssueQuery:
    relations: str
    where: str
    parameters: tuple[Any, ...]
    columns: str
    ordering: str

    def page(self, connection, *, page: int, page_size: int) -> tuple[list[dict], int]:
        total = connection.execute(
            f"SELECT count(*) AS total {self.relations} WHERE {self.where}",
            self.parameters,
        ).fetchone()["total"]
        rows = connection.execute(
            self.select_sql() + " LIMIT %s OFFSET %s",
            (*self.parameters, page_size, (page - 1) * page_size),
        ).fetchall()
        return [dict(row) for row in rows], total

    def select_sql(self) -> str:
        return (
            f"SELECT {self.columns} {self.relations} WHERE {self.where} "
            f"ORDER BY {self.ordering}"
        )


def pipeline_issue_query(
    execution_id: str,
    *,
    projection: Literal["execution", "import"],
    organization_scopes: frozenset[UUID] | None,
    sort: Literal["oldest", "newest"],
    severity: str | None = None,
    source: str | None = None,
    code: str | None = None,
    workorder: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> PipelineIssueQuery:
    clauses = ["pi.execution_id=%s"]
    parameters: list[Any] = [execution_id]
    workorder_expression = (
        "COALESCE(pi.details->>'workorder_number', "
        "nr.normalized_values->>'workorder_number')"
    )
    if projection == "execution":
        # Legacy evidence consumer retains its own artifact.read dependency.
        relations = (
            "FROM synergia.pipeline_issues pi "
            "JOIN synergia.source_files sf ON sf.id=pi.source_file_id "
            "LEFT JOIN synergia.normalized_records nr "
            "ON nr.imported_record_id=pi.imported_record_id"
        )
        columns = (
            "pi.id,sf.source,pi.severity,pi.code,pi.scope,"
            f"{workorder_expression} AS workorder_number,pi.sheet_name,"
            "pi.row_number,pi.column_name,pi.reason,pi.details,"
            "pi.created_at AS occurred_at"
        )
    else:
        # No names, values, details, storage paths or normalized-record joins.
        # A malformed historical file reference cannot expose another execution.
        relations = (
            "FROM synergia.executions e "
            "JOIN synergia.pipeline_issues pi ON pi.execution_id=e.id "
            "LEFT JOIN synergia.source_files sf ON sf.id=pi.source_file_id "
            "AND sf.execution_id=e.id"
        )
        clauses.append("e.organization_id IS NOT NULL")
        if organization_scopes is not None:
            clauses.append("e.organization_id=ANY(%s::uuid[])")
            parameters.append(sorted(organization_scopes, key=str))
        columns = (
            "pi.id,sf.id AS source_file_id,sf.extension,pi.severity,pi.code,"
            "pi.scope,pi.sheet_name,pi.row_number,pi.column_name,"
            "pi.created_at AS occurred_at"
        )
        if workorder is not None:
            raise ValueError("Import issues cannot filter private workorder values")
    for expression, value in (
        ("sf.source=%s", source),
        ("pi.severity=%s", severity),
        ("pi.code=%s", code),
        ("pi.created_at >= %s", date_from),
        ("pi.created_at <= %s", date_to),
        (f"{workorder_expression}=%s", workorder),
    ):
        if value is not None:
            clauses.append(expression)
            parameters.append(value)
    direction = "DESC" if sort == "newest" else "ASC"
    return PipelineIssueQuery(
        relations,
        " AND ".join(clauses),
        tuple(parameters),
        columns,
        f"pi.created_at {direction},pi.id {direction}",
    )


def import_execution_visible(
    connection: psycopg.Connection,
    execution_id: str,
    organization_scopes: frozenset[UUID] | None,
) -> bool:
    """Check the root before counting, joining file metadata or paginating."""
    scopes = (
        None if organization_scopes is None else sorted(organization_scopes, key=str)
    )
    return (
        connection.execute(
            "SELECT 1 FROM synergia.executions WHERE id=%s "
            "AND organization_id IS NOT NULL "
            "AND (%s::uuid[] IS NULL OR organization_id=ANY(%s::uuid[]))",
            (execution_id, scopes, scopes),
        ).fetchone()
        is not None
    )
