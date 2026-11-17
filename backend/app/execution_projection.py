"""Read-only execution projections; persisted states remain unchanged."""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from psycopg import sql


class ExecutionOutcome(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PARTIAL = "partial"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


LegacyLifecycle = Literal["active", "completed", "partial", "failed"]

_OUTCOME_BY_STATUS: Mapping[str, ExecutionOutcome] = MappingProxyType(
    {
        "pending": ExecutionOutcome.ACTIVE,
        "validating": ExecutionOutcome.ACTIVE,
        "normalizing": ExecutionOutcome.ACTIVE,
        "consolidating": ExecutionOutcome.ACTIVE,
        "applying_rules": ExecutionOutcome.ACTIVE,
        "reprocessing": ExecutionOutcome.ACTIVE,
        "completed": ExecutionOutcome.COMPLETED,
        "completed_with_errors": ExecutionOutcome.PARTIAL,
        "duplicate": ExecutionOutcome.SKIPPED_DUPLICATE,
        "validation_failed": ExecutionOutcome.FAILED,
        "failed": ExecutionOutcome.FAILED,
        "cancelled": ExecutionOutcome.CANCELLED,
    }
)
_LEGACY_BY_OUTCOME: Mapping[ExecutionOutcome, LegacyLifecycle] = MappingProxyType(
    {
        ExecutionOutcome.ACTIVE: "active",
        ExecutionOutcome.COMPLETED: "completed",
        ExecutionOutcome.PARTIAL: "partial",
        ExecutionOutcome.SKIPPED_DUPLICATE: "completed",
        ExecutionOutcome.FAILED: "failed",
        ExecutionOutcome.CANCELLED: "failed",
        # Preserve the legacy fallback; new metrics must use outcome instead.
        ExecutionOutcome.UNKNOWN: "active",
    }
)


def execution_outcome(status: str | None) -> ExecutionOutcome:
    return _OUTCOME_BY_STATUS.get(status, ExecutionOutcome.UNKNOWN)


def legacy_lifecycle(status: str | None) -> LegacyLifecycle:
    """Compatibility adapter, including duplicate/cancelled/unknown semantics."""
    return _LEGACY_BY_OUTCOME[execution_outcome(status)]


def _projection_sql(
    column: tuple[str, ...], mapping: Mapping[str, str], default: str
) -> str:
    identifier = sql.Identifier(*(column or ("status",)))
    branches = sql.SQL(" ").join(
        sql.SQL("WHEN {} = {} THEN {}").format(
            identifier, sql.Literal(status), sql.Literal(value)
        )
        for status, value in mapping.items()
    )
    return (
        sql.SQL("CASE {} ELSE {} END")
        .format(branches, sql.Literal(default))
        .as_string()
    )


def outcome_sql(*column: str) -> str:
    """Build a SQL projection from the same mapping as the Python projection."""
    return _projection_sql(column, _OUTCOME_BY_STATUS, ExecutionOutcome.UNKNOWN)


def legacy_lifecycle_sql(*column: str) -> str:
    return _projection_sql(
        column,
        {status: legacy_lifecycle(status) for status in _OUTCOME_BY_STATUS},
        "active",
    )
