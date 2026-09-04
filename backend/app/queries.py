from __future__ import annotations

# Complex reporting queries are kept readable as aligned SQL blocks.
# ruff: noqa: E501
import math
import os
from collections.abc import Generator
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, Query, Request, status
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

from app.authorization import (
    ActorContext,
    AuthorizationRepo,
    require_execution_permission,
    require_lot_permission,
    require_permission,
    require_resource_permission,
)
from app.business_rules import RULE_CATALOG
from app.errors import ApiError, ErrorResponse
from app.execution import PIPELINE_VERSION, reprocessing_fingerprint

router = APIRouter(tags=["queries"])
ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Recurso não encontrado"},
    409: {"model": ErrorResponse, "description": "Estado incompatível"},
    422: {"model": ErrorResponse, "description": "Parâmetros inválidos"},
    500: {"model": ErrorResponse, "description": "Falha interna padronizada"},
}


class ReprocessingConflict(Exception):
    pass


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class OperationalSearchItem(BaseModel):
    entity_type: Literal["workorder", "lot", "serial"]
    identifier: str
    execution_id: str
    workorder_number: str
    lot_number: str | None = None
    serial_number: str | None = None
    organization_code: str | None = None
    processing_status: str | None = None
    updated_at: datetime


class OperationalSearchPage(BaseModel):
    items: list[OperationalSearchItem]
    pagination: Pagination
    sort: Literal["updated_desc", "identifier_asc"]
    entity_type: Literal["workorder", "lot", "serial"]
    query: str
    source: str = "synergia.operational"
    generated_at: datetime


class ExecutionStateEvent(BaseModel):
    from_state: str | None = None
    to_state: str
    reason: str
    state_version: int
    occurred_at: datetime


class ExecutionCounts(BaseModel):
    files: int = 0
    files_received: int = 0
    files_accepted: int = 0
    files_rejected: int = 0
    rows_read: int = 0
    valid_records: int = 0
    rejected_records: int = 0
    normalized_records: int = 0
    workorders: int = 0
    lots: int = 0
    serials: int = 0
    classifications: int = 0
    pending_items: int = 0
    errors: int = 0
    warnings: int = 0


class ExecutionResponse(BaseModel):
    execution_id: str
    status: str
    source: str | None = None
    attempt: int
    reprocessed_from_execution_id: str | None = None
    actor_type: str | None = None
    actor_identifier: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    failure_reason: str | None = None
    pipeline_version: str
    rule_catalog_version: str
    state_version: int
    updated_at: datetime | None = None
    lifecycle: Literal["active", "completed", "partial", "failed"] | None = None
    state_history: list[ExecutionStateEvent] = Field(default_factory=list)
    counts: ExecutionCounts = Field(default_factory=ExecutionCounts)


class WorkorderResponse(BaseModel):
    execution_id: str
    workorder_number: str
    organization_code: str | None = None
    processing_status: str
    planned_quantity: int | None = None
    produced_quantity: int | None = None
    received_quantity: int | None = None
    released_quantity: int | None = None
    pending_quantity: int | None = None
    retained_quantity: int | None = None
    partially_released: bool | None = None
    lots: list[str]
    serials: list[str]
    updated_at: datetime


class LotResponse(BaseModel):
    execution_id: str
    workorder_number: str
    lot_number: str
    serials: list[str]
    updated_at: datetime


class SerialResponse(BaseModel):
    execution_id: str
    workorder_number: str
    lot_number: str | None = None
    serial_number: str
    container_number: str | None = None
    updated_at: datetime


class PendingItemResponse(BaseModel):
    id: int
    execution_id: str
    workorder_number: str
    lot_number: str | None = None
    serial_number: str | None = None
    category: str
    reason: str | None = None
    status: str
    priority_score: int
    priority: str
    responsible_area: str | None = None
    created_at: datetime
    updated_at: datetime


class PendingPage(BaseModel):
    items: list[PendingItemResponse]
    pagination: Pagination
    sort: str


class HistoryEventResponse(BaseModel):
    id: int
    execution_id: str
    entity_type: str
    entity_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime


class HistoryPage(BaseModel):
    items: list[HistoryEventResponse]
    pagination: Pagination
    sort: str


class HoldResponse(BaseModel):
    id: int
    serial_number: str | None = None
    reason: str | None = None
    status: str
    post_release: bool
    created_at: datetime
    updated_at: datetime


class OqcDecisionResponse(BaseModel):
    id: int
    lot_number: str | None = None
    serial_number: str | None = None
    decision_state: str
    reason: str | None = None
    decided_at: datetime | None = None
    updated_at: datetime


class ConsolidatedResultResponse(BaseModel):
    workorder: WorkorderResponse
    holds: list[HoldResponse]
    oqc_decisions: list[OqcDecisionResponse]
    pending_items: list[PendingItemResponse]
    classifications: list[dict[str, Any]] = Field(default_factory=list)
    rule_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class ReprocessRequest(BaseModel):
    technical_origin: str = Field(
        min_length=1,
        max_length=120,
        description="Origem técnica que solicitou o reprocessamento",
    )
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)
    pipeline_version: str = Field(default=PIPELINE_VERSION, min_length=1, max_length=40)
    rule_catalog_version: str = Field(
        default=RULE_CATALOG["version"], min_length=1, max_length=40
    )

    @field_validator("technical_origin")
    @classmethod
    def normalize_technical_origin(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("technical_origin deve conter texto")
        return normalized


class ReprocessResponse(BaseModel):
    execution_id: str
    status: str
    attempt: int
    reprocessed_from_execution_id: str
    previous_execution_id: str
    pipeline_version: str
    rule_catalog_version: str
    idempotent_replay: bool


class IndicatorsResponse(BaseModel):
    generated_at: datetime
    source: str
    organizations: list[dict[str, str]]
    filters: dict[str, str | None]
    executions: dict[str, int]
    workorders: dict[str, int]
    pending_items: dict[str, int]
    quantities: dict[str, int]


class IndicatorRelatedPage(BaseModel):
    items: list[dict[str, Any]]
    pagination: Pagination
    entity: Literal["executions", "workorders", "pending-items"]


class QueryRepository(Protocol):
    def search_operational(
        self,
        *,
        entity_type: str,
        query: str,
        page: int,
        page_size: int,
        sort: str,
        organization_ids: frozenset | None = None,
    ) -> tuple[list[dict], int]: ...

    def get_execution(self, execution_id: str) -> dict | None: ...

    def get_workorder(
        self, workorder_number: str, execution_id: str | None = None
    ) -> dict | None: ...

    def get_lot(
        self,
        lot_number: str,
        workorder_number: str | None = None,
        organization_ids: frozenset | None = None,
        execution_id: str | None = None,
    ) -> dict | None: ...

    def get_serial(
        self, serial_number: str, execution_id: str | None = None
    ) -> dict | None: ...

    def list_pending(
        self,
        *,
        status_filter: str | None,
        category: str | None,
        workorder_number: str | None,
        execution_id: str | None,
        page: int,
        page_size: int,
        sort: str,
        organization_ids: frozenset | None = None,
    ) -> tuple[list[dict], int]: ...

    def get_pending(self, pending_id: int) -> dict | None: ...

    def list_history(
        self,
        *,
        execution_id: str | None,
        entity_type: str | None,
        entity_id: str | None,
        event_type: str | None,
        page: int,
        page_size: int,
        sort: str,
        organization_ids: frozenset | None = None,
    ) -> tuple[list[dict], int]: ...

    def get_consolidated(
        self, workorder_number: str, execution_id: str | None = None
    ) -> dict | None: ...

    def request_reprocessing(
        self,
        execution_id: str,
        new_execution_id: str,
        technical_origin: str,
        request_key: str,
        pipeline_version: str,
        rule_catalog_version: str,
        actor: ActorContext | None = None,
    ) -> dict | None: ...

    def indicators(
        self,
        organization_ids: frozenset | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict: ...

    def indicator_related(
        self,
        entity: str,
        organization_ids: frozenset | None,
        date_from: date | None,
        date_to: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]: ...


class PostgresQueryRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def search_operational(
        self,
        *,
        entity_type: str,
        query: str,
        page: int,
        page_size: int,
        sort: str,
        organization_ids: frozenset | None = None,
    ) -> tuple[list[dict], int]:
        definitions = {
            "workorder": (
                "synergia.workorders w",
                "w.workorder_number",
                "NULL::text",
                "NULL::text",
                "w.id",
                "w.updated_at",
            ),
            "lot": (
                "synergia.lots x JOIN synergia.workorders w ON w.id = x.workorder_id",
                "x.lot_number",
                "x.lot_number",
                "NULL::text",
                "x.id",
                "x.updated_at",
            ),
            "serial": (
                "synergia.serials x JOIN synergia.workorders w ON w.id = x.workorder_id",
                "x.serial_number",
                "l.lot_number",
                "x.serial_number",
                "x.id",
                "x.updated_at",
            ),
        }
        table, identifier, lot_number, serial_number, row_id, updated_at = definitions[
            entity_type
        ]
        serial_lot_join = (
            "LEFT JOIN synergia.lots l ON l.id = x.lot_id"
            if entity_type == "serial"
            else ""
        )
        filters = [f"{identifier} = %s"]
        parameters: list[Any] = [query]
        if organization_ids is not None:
            filters.append("e.organization_id = ANY(%s)")
            parameters.append(list(organization_ids))
        where = " AND ".join(filters)
        order = (
            f"{identifier} ASC, w.execution_id ASC, {row_id} ASC"
            if sort == "identifier_asc"
            else f"{updated_at} DESC, w.execution_id DESC, {row_id} DESC"
        )
        base = f"""
            FROM {table}
            {serial_lot_join}
            JOIN synergia.executions e ON e.id = w.execution_id
            LEFT JOIN synergia.organizations o ON o.id = w.organization_id
            WHERE {where}
        """
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT count(*) AS total {base}", parameters
            ).fetchone()["total"]
            rows = connection.execute(
                f"""
                SELECT %s AS entity_type, {identifier} AS identifier,
                       w.execution_id, w.workorder_number,
                       {lot_number} AS lot_number,
                       {serial_number} AS serial_number,
                       o.organization_code, w.processing_status,
                       {updated_at} AS updated_at
                {base}
                ORDER BY {order}
                LIMIT %s OFFSET %s
                """,
                [entity_type, *parameters, page_size, (page - 1) * page_size],
            ).fetchall()
        return [dict(row) for row in rows], total

    @staticmethod
    def _record_reprocessing_event(
        connection,
        *,
        execution_id: str,
        previous_execution_id: str,
        root_execution_id: str,
        attempt: int,
        pipeline_version: str,
        rule_catalog_version: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO synergia.audit_events (
                execution_id, entity_type, entity_id, event_type, payload
            ) VALUES (%s, 'execution', %s, 'reprocessing_requested', %s)
            """,
            (
                execution_id,
                execution_id,
                Jsonb(
                    {
                        "previous_execution_id": previous_execution_id,
                        "root_execution_id": root_execution_id,
                        "attempt": attempt,
                        "pipeline_version": pipeline_version,
                        "rule_catalog_version": rule_catalog_version,
                    }
                ),
            ),
        )

    def get_execution(self, execution_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id AS execution_id, status, source, attempt,
                       reprocessed_from_id AS reprocessed_from_execution_id,
                       actor_type, actor_identifier, started_at, finished_at,
                       failure_reason, pipeline_version, rule_catalog_version,
                       state_version, updated_at,
                       CASE
                         WHEN status IN ('completed','duplicate') THEN 'completed'
                         WHEN status = 'completed_with_errors' THEN 'partial'
                         WHEN status IN ('failed','validation_failed','cancelled') THEN 'failed'
                         ELSE 'active'
                       END AS lifecycle
                FROM synergia.executions
                WHERE id = %s
                """,
                (execution_id,),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["state_history"] = connection.execute(
                """SELECT from_state,to_state,reason,state_version,occurred_at
                   FROM synergia.execution_state_transitions WHERE execution_id=%s
                   ORDER BY occurred_at,id""",
                (execution_id,),
            ).fetchall()
            result["counts"] = connection.execute(
                """SELECT
                     (SELECT count(*) FROM synergia.file_inspections WHERE execution_id=%s) AS files,
                     (SELECT count(*) FROM synergia.file_inspections WHERE execution_id=%s) AS files_received,
                     (SELECT count(*) FROM synergia.file_inspections WHERE execution_id=%s AND decision='accepted') AS files_accepted,
                     (SELECT count(*) FROM synergia.file_inspections WHERE execution_id=%s AND decision='rejected') AS files_rejected,
                     COALESCE((SELECT sum(rows_read) FROM synergia.pipeline_summaries WHERE execution_id=%s),0) AS rows_read,
                     COALESCE((SELECT sum(valid_records) FROM synergia.pipeline_summaries WHERE execution_id=%s),0) AS valid_records,
                     COALESCE((SELECT sum(rejected_records) FROM synergia.pipeline_summaries WHERE execution_id=%s),0) AS rejected_records,
                     (SELECT count(*) FROM synergia.normalized_records WHERE execution_id=%s) AS normalized_records,
                     (SELECT count(*) FROM synergia.workorders WHERE execution_id=%s) AS workorders,
                     (SELECT count(*) FROM synergia.lots WHERE execution_id=%s) AS lots,
                     (SELECT count(*) FROM synergia.serials WHERE execution_id=%s) AS serials,
                     (SELECT count(*) FROM synergia.classifications WHERE execution_id=%s) AS classifications,
                     (SELECT count(*) FROM synergia.pending_items WHERE execution_id=%s) AS pending_items,
                     (SELECT count(*) FROM synergia.pipeline_issues WHERE execution_id=%s AND severity='error') AS errors,
                     (SELECT count(*) FROM synergia.pipeline_issues WHERE execution_id=%s AND severity='warning') AS warnings""",
                (execution_id,) * 15,
            ).fetchone()
            return result

    def get_workorder(
        self, workorder_number: str, execution_id: str | None = None
    ) -> dict | None:
        filters = ["w.workorder_number = %s"]
        parameters: list[Any] = [workorder_number]
        if execution_id:
            filters.append("w.execution_id = %s")
            parameters.append(execution_id)
        where = " AND ".join(filters)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT w.execution_id, w.workorder_number,
                       o.organization_code, w.processing_status,
                       w.planned_quantity, w.produced_quantity,
                       w.received_quantity, w.released_quantity,
                       w.pending_quantity, w.retained_quantity,
                       w.partially_released, w.updated_at, w.id
                FROM synergia.workorders w
                LEFT JOIN synergia.organizations o ON o.id = w.organization_id
                WHERE {where}
                ORDER BY w.updated_at DESC, w.id DESC
                LIMIT 1
                """,
                parameters,
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["lots"] = [
                item["lot_number"]
                for item in connection.execute(
                    "SELECT lot_number FROM synergia.lots "
                    "WHERE workorder_id = %s ORDER BY lot_number",
                    (row["id"],),
                ).fetchall()
            ]
            result["serials"] = [
                item["serial_number"]
                for item in connection.execute(
                    "SELECT serial_number FROM synergia.serials "
                    "WHERE workorder_id = %s ORDER BY serial_number",
                    (row["id"],),
                ).fetchall()
            ]
            result.pop("id")
            return result

    def get_lot(
        self,
        lot_number: str,
        workorder_number: str | None = None,
        organization_ids: frozenset | None = None,
        execution_id: str | None = None,
    ) -> dict | None:
        filters = ["l.lot_number = %s"]
        parameters: list[Any] = [lot_number]
        if workorder_number:
            filters.append("w.workorder_number = %s")
            parameters.append(workorder_number)
        if organization_ids is not None:
            filters.append("e.organization_id = ANY(%s)")
            parameters.append(list(organization_ids))
        if execution_id:
            filters.append("l.execution_id = %s")
            parameters.append(execution_id)
        where = " AND ".join(filters)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT l.execution_id, w.workorder_number, l.lot_number,
                       l.updated_at, l.id
                FROM synergia.lots l
                JOIN synergia.workorders w ON w.id = l.workorder_id
                JOIN synergia.executions e ON e.id = l.execution_id
                WHERE {where}
                ORDER BY l.updated_at DESC, l.id DESC
                LIMIT 1
                """,
                parameters,
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["serials"] = [
                item["serial_number"]
                for item in connection.execute(
                    "SELECT serial_number FROM synergia.serials "
                    "WHERE lot_id = %s ORDER BY serial_number",
                    (row["id"],),
                ).fetchall()
            ]
            result.pop("id")
            return result

    def get_serial(
        self, serial_number: str, execution_id: str | None = None
    ) -> dict | None:
        filters = ["s.serial_number = %s"]
        parameters: list[Any] = [serial_number]
        if execution_id:
            filters.append("s.execution_id = %s")
            parameters.append(execution_id)
        with self._connect() as connection:
            return connection.execute(
                f"""
                SELECT s.execution_id, w.workorder_number, l.lot_number,
                       s.serial_number, s.container_number, s.updated_at
                FROM synergia.serials s
                JOIN synergia.workorders w ON w.id = s.workorder_id
                LEFT JOIN synergia.lots l ON l.id = s.lot_id
                WHERE {" AND ".join(filters)}
                ORDER BY s.updated_at DESC, s.id DESC
                LIMIT 1
                """,
                parameters,
            ).fetchone()

    @staticmethod
    def _pending_base() -> str:
        return """
            FROM synergia.pending_items p
            JOIN synergia.workorders w ON w.id = p.workorder_id
            JOIN synergia.executions e ON e.id = p.execution_id
            LEFT JOIN synergia.lots l ON l.id = p.lot_id
            LEFT JOIN synergia.serials s ON s.id = p.serial_id
        """

    def list_pending(
        self,
        *,
        status_filter: str | None,
        category: str | None,
        workorder_number: str | None,
        execution_id: str | None,
        page: int,
        page_size: int,
        sort: str,
        organization_ids: frozenset | None = None,
    ) -> tuple[list[dict], int]:
        filters: list[str] = []
        parameters: list[Any] = []
        if organization_ids is not None:
            filters.append("e.organization_id = ANY(%s)")
            parameters.append(list(organization_ids))
        if status_filter:
            filters.append("p.status = %s")
            parameters.append(status_filter)
        if category:
            filters.append("p.category = %s")
            parameters.append(category)
        if workorder_number:
            filters.append("w.workorder_number = %s")
            parameters.append(workorder_number)
        if execution_id:
            filters.append("p.execution_id = %s")
            parameters.append(execution_id)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        order = {
            "oldest": "p.created_at ASC, p.id ASC",
            "newest": "p.created_at DESC, p.id DESC",
            "category": "p.category ASC, p.created_at ASC, p.id ASC",
        }[sort]
        base = self._pending_base()
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT count(*) AS total {base} {where}", parameters
            ).fetchone()["total"]
            rows = connection.execute(
                f"""
                SELECT p.id, p.execution_id, w.workorder_number,
                       l.lot_number, s.serial_number, p.category, p.reason,
                       p.status, p.priority_score, p.priority,
                       p.responsible_area, p.created_at, p.updated_at
                {base} {where}
                ORDER BY {order}
                LIMIT %s OFFSET %s
                """,
                [*parameters, page_size, (page - 1) * page_size],
            ).fetchall()
        return [self._decorate_pending(dict(row)) for row in rows], total

    def get_pending(self, pending_id: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT p.id, p.execution_id, w.workorder_number,
                       l.lot_number, s.serial_number, p.category, p.reason,
                       p.status, p.priority_score, p.priority,
                       p.responsible_area, p.created_at, p.updated_at
                {self._pending_base()}
                WHERE p.id = %s
                """,
                (pending_id,),
            ).fetchone()
        return self._decorate_pending(dict(row)) if row else None

    @staticmethod
    def _decorate_pending(item: dict) -> dict:
        rule = RULE_CATALOG["rules"].get(item["category"], {})
        score = item.get("priority_score")
        if score is None:
            score = int(rule.get("priority", 0))
        item["priority_score"] = score
        if item.get("priority") is None:
            item["priority"] = (
                "critical"
                if score >= 90
                else "high"
                if score >= 60
                else "normal"
                if score >= 30
                else "low"
            )
        if item.get("responsible_area") is None:
            item["responsible_area"] = rule.get("responsible_area")
        return item

    def list_history(
        self,
        *,
        execution_id: str | None,
        entity_type: str | None,
        entity_id: str | None,
        event_type: str | None,
        page: int,
        page_size: int,
        sort: str,
        organization_ids: frozenset | None = None,
    ) -> tuple[list[dict], int]:
        filters: list[str] = []
        parameters: list[Any] = []
        if organization_ids is not None:
            filters.append("e.organization_id = ANY(%s)")
            parameters.append(list(organization_ids))
        for column, value in (
            ("a.execution_id", execution_id),
            ("a.entity_type", entity_type),
            ("a.entity_id", entity_id),
            ("a.event_type", event_type),
        ):
            if value:
                filters.append(f"{column} = %s")
                parameters.append(value)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        order = (
            "a.occurred_at ASC, a.id ASC"
            if sort == "oldest"
            else "a.occurred_at DESC, a.id DESC"
        )
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT count(*) AS total FROM synergia.audit_events a JOIN synergia.executions e ON e.id = a.execution_id {where}",
                parameters,
            ).fetchone()["total"]
            rows = connection.execute(
                f"""
                SELECT a.id, a.execution_id, a.entity_type, a.entity_id, a.event_type,
                       a.payload, a.occurred_at
                FROM synergia.audit_events a JOIN synergia.executions e ON e.id = a.execution_id {where}
                ORDER BY {order}
                LIMIT %s OFFSET %s
                """,
                [*parameters, page_size, (page - 1) * page_size],
            ).fetchall()
        return [dict(row) for row in rows], total

    def get_consolidated(
        self, workorder_number: str, execution_id: str | None = None
    ) -> dict | None:
        workorder = self.get_workorder(workorder_number, execution_id)
        if workorder is None:
            return None
        execution_id = workorder["execution_id"]
        with self._connect() as connection:
            holds = connection.execute(
                """
                SELECT h.id, h.reason, h.status, h.post_release,
                       h.created_at, h.updated_at, s.serial_number
                FROM synergia.holds h
                JOIN synergia.workorders w ON w.id = h.workorder_id
                LEFT JOIN synergia.serials s ON s.id = h.serial_id
                WHERE w.workorder_number = %s AND h.execution_id = %s
                ORDER BY h.created_at, h.id
                """,
                (workorder_number, execution_id),
            ).fetchall()
            decisions = connection.execute(
                """
                SELECT q.id, q.decision_state, q.reason, q.decided_at,
                       q.updated_at, l.lot_number, s.serial_number
                FROM synergia.oqc_decisions q
                JOIN synergia.workorders w ON w.id = q.workorder_id
                LEFT JOIN synergia.lots l ON l.id = q.lot_id
                LEFT JOIN synergia.serials s ON s.id = q.serial_id
                WHERE w.workorder_number = %s AND q.execution_id = %s
                ORDER BY q.updated_at, q.id
                """,
                (workorder_number, execution_id),
            ).fetchall()
            classifications = connection.execute(
                """
                SELECT c.classification_id, c.rule_id,
                       c.rule_catalog_version, c.state, c.entity_type,
                       c.entity_id, c.justification, c.reason, c.data_quality,
                       c.priority, c.priority_score, c.responsible_area,
                       c.occurred_at, c.classified_at, c.evidence,
                       l.lot_number, s.serial_number
                FROM synergia.classifications c
                JOIN synergia.workorders w ON w.id = c.workorder_id
                LEFT JOIN synergia.lots l ON l.id = c.lot_id
                LEFT JOIN synergia.serials s ON s.id = c.serial_id
                WHERE w.workorder_number = %s AND c.execution_id = %s
                ORDER BY c.classified_at, c.classification_id
                """,
                (workorder_number, execution_id),
            ).fetchall()
            evaluations = connection.execute(
                """
                SELECT r.id, r.rule_id, r.rule_catalog_version, r.result,
                       r.justification, r.evidence, r.created_at
                FROM synergia.rule_evaluations r
                JOIN synergia.workorders w ON w.id = r.workorder_id
                WHERE w.workorder_number = %s AND r.execution_id = %s
                ORDER BY r.id
                """,
                (workorder_number, execution_id),
            ).fetchall()
            provenance = connection.execute(
                """
                SELECT p.id, p.field_name, p.source, p.sheet_name,
                       p.row_number, p.observed_value, p.source_file_id,
                       p.created_at
                FROM synergia.consolidated_field_provenance p
                JOIN synergia.workorders w ON w.id = p.workorder_id
                WHERE w.workorder_number = %s AND p.execution_id = %s
                ORDER BY p.field_name, p.source_file_id, p.row_number, p.id
                """,
                (workorder_number, execution_id),
            ).fetchall()
        pending, _ = self.list_pending(
            status_filter=None,
            category=None,
            workorder_number=workorder_number,
            execution_id=execution_id,
            page=1,
            page_size=2_147_483_647,
            sort="oldest",
        )
        return {
            "workorder": workorder,
            "holds": [dict(item) for item in holds],
            "oqc_decisions": [dict(item) for item in decisions],
            "pending_items": pending,
            "classifications": [dict(item) for item in classifications],
            "rule_evaluations": [dict(item) for item in evaluations],
            "provenance": [dict(item) for item in provenance],
        }

    def request_reprocessing(
        self,
        execution_id: str,
        new_execution_id: str,
        technical_origin: str,
        request_key: str,
        pipeline_version: str,
        rule_catalog_version: str,
        actor: ActorContext | None = None,
    ) -> dict | None:
        with self._connect() as connection:
            original = connection.execute(
                """
                SELECT id, status, COALESCE(reprocessed_from_id, id) AS root_id,
                       source, organization_id
                FROM synergia.executions
                WHERE id = %s
                """,
                (execution_id,),
            ).fetchone()
            if original is None:
                return None
            if original["status"] not in {
                "completed",
                "completed_with_errors",
                "validation_failed",
                "failed",
            }:
                raise ReprocessingConflict
            connection.execute(
                "SELECT id FROM synergia.executions WHERE id = %s FOR UPDATE",
                (original["root_id"],),
            ).fetchone()
            request_fingerprint = reprocessing_fingerprint(
                execution_id,
                request_key,
                pipeline_version,
                rule_catalog_version,
            )
            existing = connection.execute(
                """
                SELECT e.id AS execution_id, e.status, e.attempt,
                       e.reprocessed_from_id, i.source_execution_id,
                       e.pipeline_version, e.rule_catalog_version
                FROM synergia.execution_idempotency i
                JOIN synergia.executions e ON e.id = i.execution_id
                WHERE i.request_fingerprint = %s
                """,
                (request_fingerprint,),
            ).fetchone()
            if existing is not None:
                return {
                    "execution_id": existing["execution_id"],
                    "status": existing["status"],
                    "attempt": existing["attempt"],
                    "reprocessed_from_execution_id": existing["reprocessed_from_id"],
                    "previous_execution_id": existing["source_execution_id"],
                    "pipeline_version": existing["pipeline_version"],
                    "rule_catalog_version": existing["rule_catalog_version"],
                    "idempotent_replay": True,
                }
            attempt = connection.execute(
                """
                SELECT COALESCE(max(attempt), 0) + 1 AS next_attempt
                FROM synergia.executions
                WHERE id = %s OR reprocessed_from_id = %s
                """,
                (original["root_id"], original["root_id"]),
            ).fetchone()["next_attempt"]
            connection.execute(
                """
                INSERT INTO synergia.executions
                    (id, status, attempt, reprocessed_from_id, source,
                     actor_type, actor_identifier, pipeline_version,
                     rule_catalog_version, state_changed_by_type,
                     state_changed_by, state_change_reason, organization_id,
                     initiated_by_user_id, initiated_by_session_id)
                VALUES (%s, 'reprocessing', %s, %s, %s, 'user', %s,
                        %s, %s, 'user', %s, 'reprocessing_requested', %s, %s, %s)
                """,
                (
                    new_execution_id,
                    attempt,
                    original["root_id"],
                    original["source"],
                    str(actor.user_id) if actor else technical_origin,
                    pipeline_version,
                    rule_catalog_version,
                    str(actor.user_id) if actor else technical_origin,
                    original["organization_id"],
                    actor.user_id if actor else None,
                    actor.session_id if actor else None,
                ),
            )
            connection.execute(
                """
                INSERT INTO synergia.execution_idempotency (
                    request_fingerprint, request_type, execution_id,
                    source_execution_id, pipeline_version, rule_catalog_version
                ) VALUES (%s, 'reprocess', %s, %s, %s, %s)
                """,
                (
                    request_fingerprint,
                    new_execution_id,
                    execution_id,
                    pipeline_version,
                    rule_catalog_version,
                ),
            )
            self._record_reprocessing_event(
                connection,
                execution_id=new_execution_id,
                previous_execution_id=execution_id,
                root_execution_id=original["root_id"],
                attempt=attempt,
                pipeline_version=pipeline_version,
                rule_catalog_version=rule_catalog_version,
            )
        return {
            "execution_id": new_execution_id,
            "status": "reprocessing",
            "attempt": attempt,
            "reprocessed_from_execution_id": original["root_id"],
            "previous_execution_id": execution_id,
            "pipeline_version": pipeline_version,
            "rule_catalog_version": rule_catalog_version,
            "idempotent_replay": False,
        }

    def indicators(
        self,
        organization_ids: frozenset | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        filters: list[str] = []
        parameters: list[object] = []
        if organization_ids is not None:
            filters.append("e.organization_id = ANY(%s)")
            parameters.append(list(organization_ids))
        if date_from is not None:
            filters.append("e.started_at::date >= %s")
            parameters.append(date_from)
        if date_to is not None:
            filters.append("e.started_at::date <= %s")
            parameters.append(date_to)
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        sql_parameters = tuple(parameters)
        with self._connect() as connection:
            execution_rows = connection.execute(
                "SELECT status, count(*) AS total "
                f"FROM synergia.executions e{where} GROUP BY status",
                sql_parameters,
            ).fetchall()
            workorder = connection.execute(
                f"""
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE partially_released) AS partial,
                       COALESCE(sum(planned_quantity), 0) AS planned,
                       COALESCE(sum(produced_quantity), 0) AS produced,
                       COALESCE(sum(received_quantity), 0) AS received,
                       COALESCE(sum(released_quantity), 0) AS released
                FROM synergia.workorders w
                JOIN synergia.executions e ON e.id = w.execution_id
                {where}
                """,
                sql_parameters,
            ).fetchone()
            pending_rows = connection.execute(
                "SELECT p.status, count(*) AS total "
                "FROM synergia.pending_items p JOIN synergia.executions e ON e.id = p.execution_id "
                f"{where} GROUP BY p.status",
                sql_parameters,
            ).fetchall()
        return {
            "executions": {row["status"]: row["total"] for row in execution_rows},
            "workorders": {
                "total": workorder["total"],
                "partially_released": workorder["partial"],
            },
            "pending_items": {row["status"]: row["total"] for row in pending_rows},
            "quantities": {
                "planned": workorder["planned"],
                "produced": workorder["produced"],
                "received": workorder["received"],
                "released": workorder["released"],
            },
        }

    def indicator_related(
        self,
        entity: str,
        organization_ids: frozenset | None,
        date_from: date | None,
        date_to: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        filters: list[str] = []
        parameters: list[object] = []
        if organization_ids is not None:
            filters.append("e.organization_id = ANY(%s)")
            parameters.append(list(organization_ids))
        if date_from is not None:
            filters.append("e.started_at::date >= %s")
            parameters.append(date_from)
        if date_to is not None:
            filters.append("e.started_at::date <= %s")
            parameters.append(date_to)
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        definitions = {
            "executions": (
                "synergia.executions e",
                "e.id AS identifier, e.status, e.started_at AS occurred_at",
            ),
            "workorders": (
                "synergia.workorders w JOIN synergia.executions e ON e.id = w.execution_id",
                "w.workorder_number AS identifier, w.processing_status AS status, e.started_at AS occurred_at",
            ),
            "pending-items": (
                "synergia.pending_items p JOIN synergia.executions e ON e.id = p.execution_id JOIN synergia.workorders w ON w.id = p.workorder_id",
                "p.id::text AS identifier, p.status, p.created_at AS occurred_at, w.workorder_number",
            ),
        }
        source, columns = definitions[entity]
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT count(*) AS total FROM {source}{where}", parameters
            ).fetchone()["total"]
            rows = connection.execute(
                f"SELECT {columns} FROM {source}{where} ORDER BY occurred_at DESC, identifier DESC LIMIT %s OFFSET %s",
                [*parameters, page_size, (page - 1) * page_size],
            ).fetchall()
        return [dict(row) for row in rows], total


def get_query_repository() -> Generator[QueryRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL não configurada")
    yield PostgresQueryRepository(database_url)


def _not_found(resource: str, identifier: str | int) -> ApiError:
    return ApiError(
        404,
        f"{resource}_not_found",
        f"{resource.replace('_', ' ').capitalize()} não encontrado",
        {"identifier": identifier},
    )


def _pagination(page: int, page_size: int, total: int) -> Pagination:
    return Pagination(
        page=page,
        page_size=page_size,
        total=total,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get(
    "/search",
    response_model=OperationalSearchPage,
    summary="Buscar Workorder, lote ou serial persistido",
    responses=ERROR_RESPONSES,
)
def search_operational(
    actor: Annotated[ActorContext, Depends(require_permission("business.read"))],
    entity_type: Literal["workorder", "lot", "serial"] = Query(alias="type"),
    query: str = Query(min_length=1, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: Literal["updated_desc", "identifier_asc"] = Query(default="updated_desc"),
    repository: QueryRepository = Depends(get_query_repository),
) -> OperationalSearchPage:
    items, total = repository.search_operational(
        entity_type=entity_type,
        query=query,
        page=page,
        page_size=page_size,
        sort=sort,
        organization_ids=actor.scope_filter("business.read"),
    )
    return OperationalSearchPage(
        items=[OperationalSearchItem.model_validate(item) for item in items],
        pagination=_pagination(page, page_size, total),
        sort=sort,
        entity_type=entity_type,
        query=query,
        generated_at=datetime.now(UTC),
    )


@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionResponse,
    summary="Consultar uma execução",
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_execution_permission("execution.read"))],
)
def get_execution(
    execution_id: str,
    repository: QueryRepository = Depends(get_query_repository),
) -> ExecutionResponse:
    item = repository.get_execution(execution_id)
    if item is None:
        raise _not_found("execution", execution_id)
    return ExecutionResponse.model_validate(item)


@router.get(
    "/workorders/{workorder_number}",
    response_model=WorkorderResponse,
    summary="Consultar uma Workorder consolidada",
    responses=ERROR_RESPONSES,
    dependencies=[
        Depends(
            require_resource_permission(
                "business.read", "workorder", "workorder_number"
            )
        )
    ],
)
def get_workorder(
    workorder_number: str,
    execution_id: str | None = Query(
        default=None, description="Restringe a consulta a uma execução"
    ),
    repository: QueryRepository = Depends(get_query_repository),
) -> WorkorderResponse:
    item = repository.get_workorder(workorder_number, execution_id)
    if item is None:
        raise _not_found("workorder", workorder_number)
    return WorkorderResponse.model_validate(item)


@router.get(
    "/lots/{lot_number}",
    response_model=LotResponse,
    summary="Consultar um lote",
    responses=ERROR_RESPONSES,
)
def get_lot(
    lot_number: str,
    actor: Annotated[ActorContext, Depends(require_lot_permission("business.read"))],
    workorder_number: str | None = Query(
        default=None, description="Restringe o lote a uma Workorder"
    ),
    execution_id: str | None = Query(
        default=None, description="Mantém o detalhe na execução localizada"
    ),
    repository: QueryRepository = Depends(get_query_repository),
) -> LotResponse:
    item = repository.get_lot(
        lot_number,
        workorder_number,
        actor.scope_filter("business.read"),
        execution_id,
    )
    if item is None:
        raise _not_found("lot", lot_number)
    return LotResponse.model_validate(item)


@router.get(
    "/serials/{serial_number}",
    response_model=SerialResponse,
    summary="Consultar um serial",
    responses=ERROR_RESPONSES,
    dependencies=[
        Depends(require_resource_permission("business.read", "serial", "serial_number"))
    ],
)
def get_serial(
    serial_number: str,
    execution_id: str | None = Query(
        default=None, description="Mantém o detalhe na execução localizada"
    ),
    repository: QueryRepository = Depends(get_query_repository),
) -> SerialResponse:
    item = repository.get_serial(serial_number, execution_id)
    if item is None:
        raise _not_found("serial", serial_number)
    return SerialResponse.model_validate(item)


@router.get(
    "/pending-items",
    response_model=PendingPage,
    summary="Listar pendências com filtros e paginação",
    responses=ERROR_RESPONSES,
)
def list_pending_items(
    actor: Annotated[ActorContext, Depends(require_permission("pending.read"))],
    status_filter: Annotated[
        Literal["open", "resolved", "cancelled"] | None,
        Query(alias="status", description="Estado da pendência"),
    ] = "open",
    category: str | None = Query(default=None),
    workorder_number: str | None = Query(default=None),
    execution_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: Literal["oldest", "newest", "category"] = Query(default="oldest"),
    repository: QueryRepository = Depends(get_query_repository),
) -> PendingPage:
    items, total = repository.list_pending(
        status_filter=status_filter,
        category=category,
        workorder_number=workorder_number,
        execution_id=execution_id,
        page=page,
        page_size=page_size,
        sort=sort,
        organization_ids=actor.scope_filter("pending.read"),
    )
    return PendingPage(
        items=[PendingItemResponse.model_validate(item) for item in items],
        pagination=_pagination(page, page_size, total),
        sort=sort,
    )


@router.get(
    "/pending-items/{pending_id}",
    response_model=PendingItemResponse,
    summary="Consultar o detalhe de uma pendência",
    responses=ERROR_RESPONSES,
    dependencies=[
        Depends(require_resource_permission("pending.read", "pending", "pending_id"))
    ],
)
def get_pending_item(
    pending_id: int,
    repository: QueryRepository = Depends(get_query_repository),
) -> PendingItemResponse:
    item = repository.get_pending(pending_id)
    if item is None:
        raise _not_found("pending_item", pending_id)
    return PendingItemResponse.model_validate(item)


@router.get(
    "/history",
    response_model=HistoryPage,
    summary="Consultar histórico auditável",
    responses=ERROR_RESPONSES,
)
def list_history(
    actor: Annotated[ActorContext, Depends(require_permission("audit.read"))],
    execution_id: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: Literal["oldest", "newest"] = Query(default="newest"),
    repository: QueryRepository = Depends(get_query_repository),
) -> HistoryPage:
    items, total = repository.list_history(
        execution_id=execution_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        page=page,
        page_size=page_size,
        sort=sort,
        organization_ids=actor.scope_filter("audit.read"),
    )
    return HistoryPage(
        items=[HistoryEventResponse.model_validate(item) for item in items],
        pagination=_pagination(page, page_size, total),
        sort=sort,
    )


@router.get(
    "/workorders/{workorder_number}/consolidated-result",
    response_model=ConsolidatedResultResponse,
    summary="Consultar o resultado consolidado de uma Workorder",
    responses=ERROR_RESPONSES,
    dependencies=[
        Depends(
            require_resource_permission(
                "business.read", "workorder", "workorder_number"
            )
        )
    ],
)
def get_consolidated_result(
    workorder_number: str,
    execution_id: str | None = Query(
        default=None, description="Mantém o detalhe na execução localizada"
    ),
    repository: QueryRepository = Depends(get_query_repository),
) -> ConsolidatedResultResponse:
    item = repository.get_consolidated(workorder_number, execution_id)
    if item is None:
        raise _not_found("consolidated_result", workorder_number)
    return ConsolidatedResultResponse.model_validate(item)


@router.post(
    "/executions/{execution_id}/reprocess",
    response_model=ReprocessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Solicitar reprocessamento sem alterar a execução anterior",
    responses=ERROR_RESPONSES,
)
def request_reprocessing(
    execution_id: str,
    request: ReprocessRequest,
    actor: Annotated[
        ActorContext, Depends(require_execution_permission("execution.reprocess"))
    ],
    repository: QueryRepository = Depends(get_query_repository),
) -> ReprocessResponse:
    try:
        result = repository.request_reprocessing(
            execution_id,
            str(uuid4()),
            request.technical_origin,
            request.idempotency_key or request.technical_origin,
            request.pipeline_version,
            request.rule_catalog_version,
            actor,
        )
    except ReprocessingConflict as exc:
        raise ApiError(
            409,
            "execution_still_active",
            "A execução não está em um estado que permita reprocessamento",
            {"execution_id": execution_id},
        ) from exc
    if result is None:
        raise _not_found("execution", execution_id)
    return ReprocessResponse.model_validate(result)


@router.get(
    "/indicators",
    response_model=IndicatorsResponse,
    summary="Consultar indicadores operacionais básicos",
    responses=ERROR_RESPONSES,
)
def get_indicators(
    actor: Annotated[ActorContext, Depends(require_permission("dashboard.read"))],
    authorization_repository: AuthorizationRepo,
    repository: QueryRepository = Depends(get_query_repository),
    organization_id: Annotated[UUID | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> IndicatorsResponse:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ApiError(
            422, "invalid_period", "date_from deve ser anterior ou igual a date_to"
        )
    visible = authorization_repository.list_active_organizations(
        actor.scopes_for("dashboard.read")
    )
    selected = None
    if organization_id:
        selected = next(
            (item for item in visible if item["id"] == organization_id), None
        )
        if selected is None:
            raise ApiError(
                403, "organization_access_denied", "Organizacao nao autorizada"
            )
        organization_scope = frozenset({selected["id"]})
    else:
        organization_scope = actor.scope_filter("dashboard.read")
    indicators = repository.indicators(organization_scope, date_from, date_to)
    return IndicatorsResponse.model_validate(
        {
            **indicators,
            "generated_at": datetime.now(UTC),
            "source": "synergia.operational",
            "organizations": [
                {
                    "id": str(item["id"]),
                    "code": item["organization_code"],
                    "name": item["display_name"],
                }
                for item in visible
            ],
            "filters": {
                "organization_id": str(selected["id"]) if selected else None,
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
            },
        }
    )


@router.get(
    "/indicators/{entity}",
    response_model=IndicatorRelatedPage,
    summary="Listar registros relacionados aos indicadores",
    responses=ERROR_RESPONSES,
)
def get_indicator_related(
    entity: Literal["executions", "workorders", "pending-items"],
    request: Request,
    actor: Annotated[ActorContext, Depends(require_permission("dashboard.read"))],
    authorization_repository: AuthorizationRepo,
    repository: QueryRepository = Depends(get_query_repository),
    organization_id: Annotated[UUID | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> IndicatorRelatedPage:
    entity_permission = {
        "executions": "execution.read",
        "workorders": "business.read",
        "pending-items": "pending.read",
    }[entity]
    entity_scopes = actor.scopes_for(entity_permission)
    if not entity_scopes:
        authorization_repository.audit_denial(actor, entity_permission, request)
        raise ApiError(403, "access_denied", "Acao nao autorizada")
    dashboard_scopes = actor.scopes_for("dashboard.read")
    if None in dashboard_scopes:
        effective_scopes = entity_scopes
    elif None in entity_scopes:
        effective_scopes = dashboard_scopes
    else:
        effective_scopes = dashboard_scopes & entity_scopes
    if not effective_scopes:
        authorization_repository.audit_denial(actor, entity_permission, request)
        raise ApiError(403, "access_denied", "Acao nao autorizada")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ApiError(
            422, "invalid_period", "date_from deve ser anterior ou igual a date_to"
        )
    if organization_id is not None:
        visible = authorization_repository.list_active_organizations(effective_scopes)
        if not any(item["id"] == organization_id for item in visible):
            raise ApiError(
                403, "organization_access_denied", "Organizacao nao autorizada"
            )
        scope = frozenset({organization_id})
    else:
        scope = None if None in effective_scopes else frozenset(effective_scopes)
    items, total = repository.indicator_related(
        entity, scope, date_from, date_to, page, page_size
    )
    return IndicatorRelatedPage(
        items=items, pagination=_pagination(page, page_size, total), entity=entity
    )
