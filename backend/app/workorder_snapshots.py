"""Authorized current/history Workorder projection, shared with future aggregates."""

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import psycopg

from app.execution_filters import ExecutionQueryFilters, build_execution_predicate
from app.execution_summary import start_execution_snapshot

WorkorderView = Literal["current", "history"]
WorkorderSort = Literal["updated_desc", "identifier_asc"]

_COLUMNS = (
    "snapshot_id",
    "organization_id",
    "business_organization_id",
    "organization_name",
    "organization_code",
    "execution_id",
    "workorder_number",
    "source_file_id",
    "processing_status",
    "updated_at",
    "planned_quantity",
    "produced_quantity",
    "received_quantity",
    "released_quantity",
    "pending_quantity",
    "retained_quantity",
    "partially_released",
)


@dataclass(frozen=True)
class WorkorderSnapshotQuery:
    """Expose the selected SQL relation, rather than merging snapshots in Python.

    ``cte`` defines ``workorder_snapshots`` and can precede an aggregate using
    the same ``parameters``. ``page`` starts a read-only repeatable-read snapshot
    and must be the first data operation in its transaction.
    """

    cte: str
    parameters: tuple[object, ...]
    view: WorkorderView

    def page(
        self,
        connection: psycopg.Connection,
        *,
        page: int,
        page_size: int,
        sort: WorkorderSort,
    ) -> tuple[list[dict[str, Any]], int]:
        if type(page) is not int or page < 1:
            raise ValueError("invalid Workorder page")
        if type(page_size) is not int or page_size < 1:
            raise ValueError("invalid Workorder page size")
        if sort not in {"updated_desc", "identifier_asc"}:
            raise ValueError("invalid Workorder sort")
        # Preserve the legacy history ordering. Current winners have already
        # been chosen by updated_at/id, independently of their execution IDs.
        if self.view == "history":
            ordering = (
                "updated_at DESC, execution_id DESC, snapshot_id DESC"
                if sort == "updated_desc"
                else "workorder_number ASC, execution_id ASC, snapshot_id ASC"
            )
        else:
            ordering = (
                "updated_at DESC, snapshot_id DESC"
                if sort == "updated_desc"
                else "workorder_number ASC, snapshot_id ASC"
            )
        start_execution_snapshot(connection)
        total = connection.execute(
            self.cte + " SELECT count(*) AS total FROM workorder_snapshots",
            self.parameters,
        ).fetchone()["total"]
        rows = connection.execute(
            self.cte
            + " SELECT * FROM workorder_snapshots ORDER BY "
            + ordering
            + " LIMIT %s OFFSET %s",
            (*self.parameters, page_size, (page - 1) * page_size),
        ).fetchall()
        return [dict(row) for row in rows], total


def workorder_snapshot_query(
    *,
    organization_scopes: frozenset[UUID] | None,
    filters: ExecutionQueryFilters | None = None,
    view: WorkorderView = "history",
    workorder_number: str | None = None,
) -> WorkorderSnapshotQuery:
    """Apply IAM, publication and execution filters before ranking versions.

    Scope ``None`` means global IAM access, never access to unknown IAM. The
    workbook's organization is projected under a separate name and is not an
    authorization key. Explicit execution/per-period filters intentionally
    select the most recent snapshot *inside* that eligible set.
    """
    if view not in {"current", "history"}:
        raise ValueError("invalid Workorder view")
    predicate = build_execution_predicate(
        filters or ExecutionQueryFilters(), organization_scopes=organization_scopes
    )
    where = [predicate.where, "e.status IN ('completed', 'completed_with_errors')"]
    parameters = list(predicate.parameters)
    if workorder_number is not None:
        where.append("w.workorder_number = %s")
        parameters.append(workorder_number)
    current_filter = "WHERE snapshot_rank = 1" if view == "current" else ""
    cte = f"""WITH ranked_workorder_snapshots AS (
        SELECT w.id AS snapshot_id, e.organization_id,
               w.organization_id AS business_organization_id,
               iam.display_name AS organization_name, o.organization_code,
               w.execution_id, w.workorder_number, w.source_file_id,
               w.processing_status, w.updated_at,
               w.planned_quantity, w.produced_quantity, w.received_quantity,
               w.released_quantity, w.pending_quantity, w.retained_quantity,
               w.partially_released,
               row_number() OVER (
                   PARTITION BY e.organization_id, w.workorder_number
                   ORDER BY w.updated_at DESC, w.id DESC
               ) AS snapshot_rank
        FROM synergia.workorders w
        JOIN synergia.executions e ON e.id = w.execution_id
        JOIN synergia.iam_organizations iam ON iam.id = e.organization_id
        LEFT JOIN synergia.organizations o
          ON o.id = w.organization_id AND o.execution_id = w.execution_id
        WHERE {" AND ".join(where)}
    ), workorder_snapshots AS (
        SELECT {", ".join(_COLUMNS)} FROM ranked_workorder_snapshots
        {current_filter}
    )"""
    return WorkorderSnapshotQuery(cte, tuple(parameters), view)
