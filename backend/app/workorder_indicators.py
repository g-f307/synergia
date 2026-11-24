"""Known quantities over authorized current Workorders, without merging versions."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.execution_filters import ExecutionQueryFilters
from app.workorder_snapshots import workorder_snapshot_query

QuantityKey = Literal["planned", "produced", "received", "released"]
CoverageState = Literal["complete", "partial", "missing", "empty"]
_QUANTITIES: tuple[QuantityKey, ...] = ("planned", "produced", "received", "released")


@dataclass(frozen=True)
class QuantityCoverage:
    known_sum: int | None
    known_count: int
    total_count: int
    coverage_percent: float | None
    state: CoverageState


@dataclass(frozen=True)
class CurrentWorkorderIndicators:
    total: int
    partially_released: int
    quantities_coverage: dict[QuantityKey, QuantityCoverage]


def read_current_workorder_indicators(
    connection: psycopg.Connection,
    *,
    organization_scopes: frozenset[UUID] | None,
    filters: ExecutionQueryFilters | None = None,
) -> CurrentWorkorderIndicators:
    """Aggregate the #195 selected relation in one SQL statement.

    The repository owns the connection/transaction. Start its read-only
    repeatable-read snapshot before the first query (including legacy period
    normalization), as for execution aggregates. This reader neither starts
    nor commits a transaction and can share that snapshot with legacy totals.
    """
    selected = workorder_snapshot_query(
        organization_scopes=organization_scopes, filters=filters, view="current"
    )
    # Identifiers below come exclusively from the closed, internal quantity set.
    aggregates = ", ".join(
        f"SUM({key}_quantity) AS {key}_known_sum, "
        f"COUNT(*) FILTER (WHERE {key}_quantity IS NOT NULL) AS {key}_known_count"
        for key in _QUANTITIES
    )
    with connection.cursor(row_factory=dict_row) as cursor:
        row = cursor.execute(
            selected.cte + " SELECT COUNT(*) AS total_count, "
            "COUNT(*) FILTER (WHERE partially_released) AS partially_released, "
            + aggregates
            + " FROM workorder_snapshots",
            selected.parameters,
        ).fetchone()
    total = row["total_count"]
    coverage = {}
    for key in _QUANTITIES:
        known = row[f"{key}_known_count"]
        state: CoverageState
        if total == 0:
            state = "empty"
        elif known == 0:
            state = "missing"
        elif known < total:
            state = "partial"
        else:
            state = "complete"
        coverage[key] = QuantityCoverage(
            known_sum=row[f"{key}_known_sum"],
            known_count=known,
            total_count=total,
            coverage_percent=100 * known / total if total else None,
            state=state,
        )
    return CurrentWorkorderIndicators(
        total=total,
        partially_released=row["partially_released"],
        quantities_coverage=coverage,
    )
