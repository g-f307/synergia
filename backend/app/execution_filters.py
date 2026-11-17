"""Shared, parameterized execution predicates for catalog and aggregates.

Queries must alias executions as ``e``. Authorization scopes are mandatory
arguments, independent of the requested filters and of any specific permission.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from app.errors import ApiError
from app.execution_projection import (
    ExecutionOutcome,
    LegacyLifecycle,
    legacy_lifecycle_sql,
    outcome_sql,
)


def normalize_execution_period(
    date_from: datetime | None, date_to: datetime | None
) -> tuple[datetime | None, datetime | None]:
    if any(
        value is not None and value.utcoffset() is None
        for value in (date_from, date_to)
    ):
        raise ApiError(
            422,
            "timezone_required",
            "Os limites do período devem incluir o fuso horário",
        )
    try:
        start = date_from.astimezone(UTC) if date_from else None
        end = date_to.astimezone(UTC) if date_to else None
    except (OverflowError, ValueError):
        raise ApiError(
            422, "invalid_period", "Período fora do intervalo de instantes suportado"
        ) from None
    if start is not None and end is not None and start > end:
        raise ApiError(
            422, "invalid_period", "O início do período deve anteceder o fim"
        )
    return start, end


@dataclass(frozen=True)
class ExecutionQueryFilters:
    organization_id: UUID | None = None
    status: str | None = None
    lifecycle: LegacyLifecycle | None = None
    outcome: ExecutionOutcome | None = None
    source: str | None = None
    file_type: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    execution_id: str | None = None

    def __post_init__(self) -> None:
        start, end = normalize_execution_period(self.date_from, self.date_to)
        object.__setattr__(self, "date_from", start)
        object.__setattr__(self, "date_to", end)
        if self.file_type is not None:
            object.__setattr__(self, "file_type", self.file_type.lower().lstrip("."))
        if self.outcome is not None:
            object.__setattr__(self, "outcome", ExecutionOutcome(self.outcome))


@dataclass(frozen=True)
class ExecutionPredicate:
    where: str
    parameters: tuple[object, ...]


def indicator_execution_filters(
    *,
    organization_id: UUID | None,
    source: str | None,
    file_type: str | None,
    date_from: date | None,
    date_to: date | None,
    started_from: datetime | None,
    started_to: datetime | None,
    status: str | None = None,
    outcome: ExecutionOutcome | None = None,
    lifecycle: LegacyLifecycle | None = None,
    execution_id: str | None = None,
) -> ExecutionQueryFilters:
    if (date_from is not None or date_to is not None) and (
        started_from is not None or started_to is not None
    ):
        raise ApiError(
            422,
            "ambiguous_execution_period",
            "Use datas legadas ou limites de instante, não ambos",
        )
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ApiError(
            422, "invalid_period", "date_from deve ser anterior ou igual a date_to"
        )
    return ExecutionQueryFilters(
        organization_id=organization_id,
        source=source,
        file_type=file_type,
        date_from=started_from,
        date_to=started_to,
        status=status,
        outcome=outcome,
        lifecycle=lifecycle,
        execution_id=execution_id,
    )


def build_execution_predicate(
    filters: ExecutionQueryFilters,
    *,
    organization_scopes: frozenset[UUID] | None,
) -> ExecutionPredicate:
    # Even global actors cannot be authorized for an unknown IAM organization.
    clauses = ["e.organization_id IS NOT NULL"]
    parameters: list[object] = []
    if organization_scopes is not None:
        if not organization_scopes:
            return ExecutionPredicate("FALSE", ())
        clauses.append("e.organization_id = ANY(%s)")
        parameters.append(sorted(organization_scopes, key=str))
    if filters.organization_id is not None:
        clauses.append("e.organization_id = %s")
        parameters.append(filters.organization_id)
    for expression, value in (
        ("e.status = %s", filters.status),
        ("e.source = %s", filters.source),
        ("e.started_at >= %s", filters.date_from),
        ("e.started_at <= %s", filters.date_to),
        ("e.id = %s", filters.execution_id),
    ):
        if value is not None:
            clauses.append(expression)
            parameters.append(value)
    if filters.file_type is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM synergia.source_files filtered "
            "WHERE filtered.execution_id=e.id AND filtered.extension=%s)"
        )
        parameters.append(filters.file_type)
    if filters.lifecycle is not None:
        clauses.append(f"({legacy_lifecycle_sql('e', 'status')}) = %s")
        parameters.append(filters.lifecycle)
    if filters.outcome is not None:
        clauses.append(f"({outcome_sql('e', 'status')}) = %s")
        parameters.append(filters.outcome.value)
    return ExecutionPredicate(" AND ".join(clauses), tuple(parameters))
