"""Canonical response models and authorized aggregation of persisted executions."""

from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.errors import ApiError
from app.execution_filters import ExecutionQueryFilters, build_execution_predicate
from app.execution_projection import (
    ExecutionOutcome,
    LegacyLifecycle,
    execution_outcome,
    outcome_sql,
)

SummaryPermission = Literal["execution.read", "dashboard.read"]


class ExecutionOutcomeResponse(BaseModel):
    status: str

    @computed_field(description="Situação canônica; desconhecidos nunca são sucesso.")
    @property
    def outcome(self) -> ExecutionOutcome:
        return execution_outcome(self.status)


class ExecutionOutcomeCounts(BaseModel):
    active: int = Field(default=0, ge=0)
    completed: int = Field(default=0, ge=0)
    partial: int = Field(default=0, ge=0)
    skipped_duplicate: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    cancelled: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)


class ExecutionSummaryFilters(BaseModel):
    organization_id: UUID | None = None
    source: str | None = None
    file_type: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    status: str | None = None
    lifecycle: LegacyLifecycle | None = Field(default=None, deprecated=True)
    outcome: ExecutionOutcome | None = None
    execution_id: str | None = None


class ExecutionSummaryScope(BaseModel):
    permission: SummaryPermission
    organization_ids: list[UUID] | None = Field(
        description="Organizações da permissão aplicada; null indica escopo global IAM."
    )


class ExecutionSourceSummary(BaseModel):
    source: str | None = Field(description="null mantém o grupo sem fonte informada.")
    total: int = Field(ge=0)
    by_outcome: ExecutionOutcomeCounts
    rows_read: int = Field(ge=0)
    latest_started_at: datetime


class ExecutionSummary(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "generated_at": "2026-11-01T12:00:00Z",
                    "scope": {
                        "permission": "execution.read",
                        "organization_ids": ["19300000-0000-4000-8000-000000000001"],
                    },
                    "filters": {
                        "organization_id": None,
                        "source": None,
                        "file_type": None,
                        "date_from": None,
                        "date_to": None,
                        "status": None,
                        "lifecycle": None,
                        "outcome": None,
                        "execution_id": None,
                    },
                    "total": 9,
                    "by_outcome": {
                        "active": 1,
                        "completed": 3,
                        "partial": 1,
                        "skipped_duplicate": 1,
                        "failed": 1,
                        "cancelled": 1,
                        "unknown": 1,
                    },
                    "by_source": [
                        {
                            "source": "OWM",
                            "total": 9,
                            "rows_read": 42,
                            "latest_started_at": "2026-11-01T12:00:00Z",
                            "by_outcome": {
                                "active": 1,
                                "completed": 3,
                                "partial": 1,
                                "skipped_duplicate": 1,
                                "failed": 1,
                                "cancelled": 1,
                                "unknown": 1,
                            },
                        }
                    ],
                }
            ]
        }
    )

    generated_at: datetime
    scope: ExecutionSummaryScope
    filters: ExecutionSummaryFilters
    total: int = Field(ge=0)
    by_outcome: ExecutionOutcomeCounts
    by_source: list[ExecutionSourceSummary]


@dataclass(frozen=True)
class ExecutionAggregation:
    summary: ExecutionSummary
    by_status: dict[str, int]


def start_execution_snapshot(connection: psycopg.Connection) -> None:
    """Call before the first data query of a repository-owned transaction."""
    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")


def resolve_indicator_period(
    connection: psycopg.Connection,
    filters: ExecutionQueryFilters,
    date_from: date | None,
    date_to: date | None,
) -> ExecutionQueryFilters:
    """Adapt legacy database-calendar dates without redefining their timezone."""
    if date_from is None and date_to is None:
        return filters
    if filters.date_from is not None or filters.date_to is not None:
        raise ApiError(
            422,
            "ambiguous_execution_period",
            "Use datas legadas ou limites de instante, não ambos",
        )
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ApiError(
            422, "invalid_period", "O início do período deve anteceder o fim"
        )
    with connection.cursor(row_factory=dict_row) as cursor:
        row = cursor.execute(
            """WITH bounds AS (SELECT %s::date AS start_date, %s::date AS end_date)
            SELECT
                CASE WHEN start_date IS NOT NULL THEN
                    greatest(start_date::timestamp
                                 AT TIME ZONE current_setting('TimeZone'),
                             timestamptz '0001-01-01 00:00:00+00')
                        AT TIME ZONE 'UTC' END AS start,
                CASE WHEN end_date IS NOT NULL THEN
                    least(((end_date + 1)::timestamp
                                AT TIME ZONE current_setting('TimeZone'))
                              - interval '1 microsecond',
                          timestamptz '9999-12-31 23:59:59.999999+00')
                        AT TIME ZONE 'UTC' END AS finish
            FROM bounds""",
            (date_from, date_to),
        ).fetchone()
    # Fetch as UTC wall time so extreme calendar dates do not overflow a
    # connection timezone when adapting timestamps supported by Python.
    return replace(
        filters,
        date_from=row["start"].replace(tzinfo=UTC) if row["start"] else None,
        date_to=row["finish"].replace(tzinfo=UTC) if row["finish"] else None,
    )


def read_execution_aggregation(
    connection: psycopg.Connection,
    filters: ExecutionQueryFilters,
    *,
    organization_scopes: frozenset[UUID] | None,
    permission: SummaryPermission,
) -> ExecutionAggregation:
    """One grouped query, without pagination or multiplying source-file joins."""
    predicate = build_execution_predicate(
        filters, organization_scopes=organization_scopes
    )
    generated_at = datetime.now(UTC)
    with connection.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute(
            f"""WITH filtered AS (
                SELECT e.status, e.source, e.started_at,
                       {outcome_sql("e", "status")} AS outcome,
                       COALESCE(s.rows_read, 0) AS rows_read
                FROM synergia.executions e
                LEFT JOIN synergia.pipeline_summaries s ON s.execution_id = e.id
                WHERE {predicate.where}
            )
            SELECT source, outcome, status, count(*) AS total,
                   sum(rows_read) AS rows_read, max(started_at) AS latest_started_at
            FROM filtered GROUP BY source, outcome, status
            ORDER BY source NULLS LAST, outcome, status""",
            predicate.parameters,
        ).fetchall()
    counts = dict.fromkeys(ExecutionOutcome, 0)
    by_status: dict[str, int] = {}
    sources: dict[str | None, dict] = {}
    for row in rows:
        outcome, total = row["outcome"], row["total"]
        counts[outcome] += total
        by_status[row["status"]] = by_status.get(row["status"], 0) + total
        source = sources.setdefault(
            row["source"],
            {
                "source": row["source"],
                "total": 0,
                "by_outcome": dict.fromkeys(ExecutionOutcome, 0),
                "rows_read": 0,
                "latest_started_at": row["latest_started_at"].astimezone(UTC),
            },
        )
        source["total"] += total
        source["by_outcome"][outcome] += total
        source["rows_read"] += row["rows_read"]
        source["latest_started_at"] = max(
            source["latest_started_at"], row["latest_started_at"].astimezone(UTC)
        )
    return ExecutionAggregation(
        summary=ExecutionSummary(
            generated_at=generated_at,
            scope=ExecutionSummaryScope(
                permission=permission,
                organization_ids=(
                    sorted(organization_scopes, key=str)
                    if organization_scopes is not None
                    else None
                ),
            ),
            filters=ExecutionSummaryFilters.model_validate(asdict(filters)),
            total=sum(counts.values()),
            by_outcome=ExecutionOutcomeCounts.model_validate(counts),
            by_source=[
                ExecutionSourceSummary.model_validate(item) for item in sources.values()
            ],
        ),
        by_status=by_status,
    )
