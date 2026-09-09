from __future__ import annotations

# Reporting SQL is kept as readable, aligned blocks.
# ruff: noqa: E501, I001

import hashlib
import json
import math
import os
from collections import Counter
from collections.abc import Generator
from datetime import date, datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, Query, Request, status
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.authorization import (
    ActorContext,
    AuthorizationRepo,
    require_permission,
)
from app.errors import ApiError, ErrorResponse

router = APIRouter(prefix="/reports", tags=["reports"])
ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Ação não autorizada"},
    404: {"model": ErrorResponse, "description": "Recurso não encontrado"},
    409: {"model": ErrorResponse, "description": "Estado incompatível"},
    422: {"model": ErrorResponse, "description": "Parâmetros inválidos"},
    500: {"model": ErrorResponse, "description": "Falha de geração registrada"},
}

ReportType = Literal["workorder_consolidated", "oqc_summary"]
ReportState = Literal["generating", "succeeded", "failed", "cancelled"]
Completeness = Literal["complete", "partial"]


class ReportGenerationCancelled(Exception):
    pass


class ReportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date | None = None
    date_to: date | None = None
    state: str | None = Field(default=None, max_length=80)
    workorder_number: str | None = Field(default=None, max_length=200)
    lot_number: str | None = Field(default=None, max_length=200)
    priority: Literal["critical", "high", "normal", "low"] | None = None

    @model_validator(mode="after")
    def validate_period(self) -> ReportFilters:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from deve ser anterior ou igual a date_to")
        return self


class CreateReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_type: ReportType
    execution_id: str = Field(min_length=1, max_length=200)
    organization_id: UUID
    reference_at: datetime
    filters: ReportFilters = Field(default_factory=ReportFilters)

    @model_validator(mode="after")
    def validate_reference_timezone(self) -> CreateReportRequest:
        if self.reference_at.tzinfo is None:
            raise ValueError("reference_at deve incluir fuso horário")
        allowed_states = {
            "workorder_consolidated": {
                "pending",
                "validated",
                "consolidated",
                "failed",
            },
            "oqc_summary": {
                "pending",
                "approved",
                "partially_approved",
                "rejected",
                "not_applicable",
            },
        }
        if (
            self.filters.state
            and self.filters.state not in allowed_states[self.report_type]
        ):
            raise ValueError("state não é aplicável ao tipo de relatório")
        if self.report_type == "workorder_consolidated" and (
            self.filters.lot_number or self.filters.priority
        ):
            raise ValueError(
                "lot_number e priority são aplicáveis somente ao sumário OQC"
            )
        return self


class CancelReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def normalize_reason(self) -> CancelReportRequest:
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("reason deve conter texto")
        return self


class ReportVersionResponse(BaseModel):
    report_id: UUID
    version_id: UUID
    version: int
    report_type: ReportType
    state: ReportState
    completeness: Completeness | None = None
    organization_id: UUID
    execution_id: str
    requested_by_user_id: UUID
    reference_at: datetime
    filters: dict[str, Any]
    schema_version: str
    created_at: datetime
    completed_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    cancellation_reason: str | None = None


class ReportDataResponse(ReportVersionResponse):
    data: dict[str, Any] | None = None


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class ReportPage(BaseModel):
    items: list[ReportVersionResponse]
    pagination: Pagination


class ReportRepository(Protocol):
    def generate(
        self,
        payload: CreateReportRequest,
        actor: ActorContext,
        report_id: UUID | None = None,
    ) -> dict: ...
    def list_reports(
        self,
        organization_ids: frozenset[UUID] | None,
        report_type: str | None,
        state: str | None,
        execution_id: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]: ...
    def list_versions(
        self,
        report_id: UUID,
        organization_ids: frozenset[UUID] | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]: ...
    def get_version(
        self,
        report_id: UUID,
        version: int | None,
        organization_ids: frozenset[UUID] | None,
        audit_actor: ActorContext | None = None,
    ) -> dict | None: ...
    def cancel(
        self,
        report_id: UUID,
        version: int,
        actor: ActorContext,
        reason: str,
    ) -> dict | None: ...


class PostgresReportRepository:
    SCHEMA_VERSION = "1.0.0"
    TERMINAL_EXECUTIONS = {"completed", "completed_with_errors"}

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _metadata(row: dict) -> dict:
        return {
            "report_id": row["report_id"],
            "version_id": row["id"],
            "version": row["version"],
            "report_type": row["report_type"],
            "state": row["state"],
            "completeness": row["completeness"],
            "organization_id": row["organization_id"],
            "execution_id": row["execution_id"],
            "requested_by_user_id": row["requested_by_user_id"],
            "reference_at": row["reference_at"],
            "filters": row["filters"],
            "schema_version": row["schema_version"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "failure_code": row["failure_code"],
            "failure_message": row["failure_message"],
            "cancellation_reason": row["cancellation_reason"],
        }

    def _create_generation(
        self, payload: CreateReportRequest, actor: ActorContext, report_id: UUID | None
    ) -> dict:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, status, organization_id FROM synergia.executions WHERE id = %s FOR SHARE",
                (payload.execution_id,),
            )
            execution = cursor.fetchone()
            if (
                execution is None
                or execution["organization_id"] != payload.organization_id
            ):
                raise ApiError(404, "resource_not_found", "Recurso não encontrado")
            if execution["status"] not in self.TERMINAL_EXECUTIONS:
                raise ApiError(
                    409,
                    "execution_not_reportable",
                    "A execução ainda não possui resultado consolidado",
                )

            if report_id is None:
                report_id = uuid4()
                cursor.execute(
                    """
                    INSERT INTO synergia.reports (id, report_type, organization_id, created_by_user_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        report_id,
                        payload.report_type,
                        payload.organization_id,
                        actor.user_id,
                    ),
                )
                version = 1
            else:
                cursor.execute(
                    """
                    SELECT report_type, organization_id FROM synergia.reports
                    WHERE id = %s FOR UPDATE
                    """,
                    (report_id,),
                )
                report = cursor.fetchone()
                if (
                    report is None
                    or report["organization_id"] != payload.organization_id
                ):
                    raise ApiError(404, "resource_not_found", "Recurso não encontrado")
                if report["report_type"] != payload.report_type:
                    raise ApiError(
                        409,
                        "report_type_immutable",
                        "O tipo do relatório não pode ser alterado",
                    )
                cursor.execute(
                    "SELECT coalesce(max(version), 0) + 1 AS version FROM synergia.report_versions WHERE report_id = %s",
                    (report_id,),
                )
                version = cursor.fetchone()["version"]

            version_id = uuid4()
            completeness = (
                "partial"
                if execution["status"] == "completed_with_errors"
                else "complete"
            )
            cursor.execute(
                """
                INSERT INTO synergia.report_versions (
                    id, report_id, version, execution_id, organization_id,
                    requested_by_user_id, requested_by_session_id, reference_at,
                    filters, schema_version, state, completeness, correlation_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          'generating', %s, %s)
                RETURNING *
                """,
                (
                    version_id,
                    report_id,
                    version,
                    payload.execution_id,
                    payload.organization_id,
                    actor.user_id,
                    actor.session_id,
                    payload.reference_at,
                    Jsonb(payload.filters.model_dump(mode="json", exclude_none=True)),
                    self.SCHEMA_VERSION,
                    completeness,
                    actor.correlation_id,
                ),
            )
            row = cursor.fetchone()
            cursor.execute(
                """
                INSERT INTO synergia.report_events (
                    report_version_id, event_type, actor_user_id, correlation_id, payload
                ) VALUES (%s, 'report.generation_started', %s, %s, %s)
                """,
                (
                    version_id,
                    actor.user_id,
                    actor.correlation_id,
                    Jsonb({"version": version}),
                ),
            )
            return self._metadata({**row, "report_type": payload.report_type})

    @staticmethod
    def _filter_sql(
        filters: ReportFilters, alias: str, reference_at: datetime
    ) -> tuple[list[str], list[Any]]:
        clauses: list[str] = [f"{alias}.updated_at <= %s"]
        params: list[Any] = [reference_at]
        if filters.date_from:
            clauses.append(f"{alias}.updated_at::date >= %s")
            params.append(filters.date_from)
        if filters.date_to:
            clauses.append(f"{alias}.updated_at::date <= %s")
            params.append(filters.date_to)
        if filters.workorder_number:
            clauses.append("w.workorder_number = %s")
            params.append(filters.workorder_number)
        return clauses, params

    def _workorder_data(self, cursor, payload: CreateReportRequest) -> dict:
        clauses, params = self._filter_sql(payload.filters, "w", payload.reference_at)
        clauses.insert(0, "w.execution_id = %s")
        params.insert(0, payload.execution_id)
        if payload.filters.state:
            clauses.append("w.processing_status = %s")
            params.append(payload.filters.state)
        cursor.execute(
            f"""
            SELECT w.workorder_number, o.organization_code, w.processing_status,
                   w.planned_quantity, w.produced_quantity, w.received_quantity,
                   w.released_quantity, w.pending_quantity, w.retained_quantity,
                   w.partially_released,
                   coalesce(array_agg(DISTINCT l.lot_number) FILTER (WHERE l.id IS NOT NULL), '{{}}') AS lots,
                   count(DISTINCT s.id) AS serial_count,
                   count(DISTINCT p.id) FILTER (WHERE p.status = 'open') AS open_pending_count
            FROM synergia.workorders w
            LEFT JOIN synergia.organizations o ON o.id = w.organization_id
            LEFT JOIN synergia.lots l
              ON l.workorder_id = w.id AND l.execution_id = w.execution_id
             AND l.updated_at <= %s
            LEFT JOIN synergia.serials s
              ON s.workorder_id = w.id AND s.execution_id = w.execution_id
             AND s.updated_at <= %s
            LEFT JOIN synergia.pending_items p
              ON p.workorder_id = w.id AND p.execution_id = w.execution_id
             AND p.updated_at <= %s
            WHERE {" AND ".join(clauses)}
            GROUP BY w.id, o.organization_code
            ORDER BY w.workorder_number
            """,
            [payload.reference_at, payload.reference_at, payload.reference_at, *params],
        )
        rows = list(cursor.fetchall())
        return {
            "kind": "workorder_consolidated",
            "count": len(rows),
            "workorders": rows,
        }

    def _oqc_data(self, cursor, payload: CreateReportRequest) -> dict:
        clauses, params = self._filter_sql(payload.filters, "q", payload.reference_at)
        clauses.insert(0, "q.execution_id = %s")
        params.insert(0, payload.execution_id)
        if payload.filters.state:
            clauses.append("q.decision_state = %s")
            params.append(payload.filters.state)
        if payload.filters.lot_number:
            clauses.append("l.lot_number = %s")
            params.append(payload.filters.lot_number)
        if payload.filters.priority:
            clauses.append("p.priority = %s")
            params.append(payload.filters.priority)
        cursor.execute(
            f"""
            SELECT w.workorder_number, l.lot_number, o.organization_code,
                   q.decision_state, q.reason,
                   p.priority, p.priority_score, p.reason AS pending_reason,
                   p.status AS pending_status
            FROM synergia.oqc_decisions q
            JOIN synergia.workorders w ON w.id = q.workorder_id AND w.execution_id = q.execution_id
            LEFT JOIN synergia.lots l ON l.id = q.lot_id AND l.execution_id = q.execution_id
            LEFT JOIN synergia.organizations o ON o.id = w.organization_id
            LEFT JOIN synergia.pending_items p
              ON p.workorder_id = q.workorder_id AND p.execution_id = q.execution_id
             AND p.lot_id IS NOT DISTINCT FROM q.lot_id
             AND p.serial_id IS NOT DISTINCT FROM q.serial_id
             AND p.updated_at <= %s
            WHERE {" AND ".join(clauses)}
            ORDER BY coalesce(p.priority_score, 0) DESC, w.workorder_number, l.lot_number
            """,
            [payload.reference_at, *params],
        )
        rows = list(cursor.fetchall())

        def counts(field: str) -> dict[str, int]:
            return dict(
                sorted(
                    Counter(
                        str(row[field]) if row[field] is not None else "not_informed"
                        for row in rows
                    ).items()
                )
            )

        return {
            "kind": "oqc_summary",
            "count": len(rows),
            "distinct_lots": len(
                {row["lot_number"] for row in rows if row["lot_number"] is not None}
            ),
            "by_reason": counts("reason"),
            "by_priority": counts("priority"),
            "by_organization": counts("organization_code"),
            "items": rows,
        }

    def generate(
        self,
        payload: CreateReportRequest,
        actor: ActorContext,
        report_id: UUID | None = None,
    ) -> dict:
        metadata = self._create_generation(payload, actor, report_id)
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                data = (
                    self._workorder_data(cursor, payload)
                    if payload.report_type == "workorder_consolidated"
                    else self._oqc_data(cursor, payload)
                )
                cursor.execute(
                    """
                    INSERT INTO synergia.report_artifacts (
                        report_version_id, artifact_type, media_type,
                        content, content_hash
                    ) VALUES (%s, 'data', 'application/json', %s, %s)
                    """,
                    (
                        metadata["version_id"],
                        Jsonb(data),
                        hashlib.sha256(
                            json.dumps(
                                data,
                                sort_keys=True,
                                separators=(",", ":"),
                                default=str,
                            ).encode()
                        ).hexdigest(),
                    ),
                )
                cursor.execute(
                    """
                    UPDATE synergia.report_versions SET state = 'succeeded', completed_at = now()
                    WHERE id = %s AND state = 'generating' RETURNING *
                    """,
                    (metadata["version_id"],),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ReportGenerationCancelled
                cursor.execute(
                    """INSERT INTO synergia.report_events
                    (report_version_id, event_type, actor_user_id, correlation_id, payload)
                    VALUES (%s, 'report.generation_succeeded', %s, %s, %s)""",
                    (
                        metadata["version_id"],
                        actor.user_id,
                        actor.correlation_id,
                        Jsonb({"item_count": data["count"]}),
                    ),
                )
                return {
                    **self._metadata({**row, "report_type": metadata["report_type"]}),
                    "data": data,
                }
        except ReportGenerationCancelled:
            cancelled = self.get_version(
                metadata["report_id"], metadata["version"], None
            )
            if cancelled is None:
                raise ApiError(
                    500,
                    "report_generation_state_lost",
                    "O estado persistido da geração não foi localizado",
                )
            return cancelled
        except Exception as exc:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE synergia.report_versions SET state = 'failed', completed_at = now(),
                    failure_code = 'generation_failed', failure_message = %s
                    WHERE id = %s AND state = 'generating'""",
                    ("Falha interna durante a geração", metadata["version_id"]),
                )
                cursor.execute(
                    """INSERT INTO synergia.report_events
                    (report_version_id, event_type, actor_user_id, correlation_id, payload)
                    VALUES (%s, 'report.generation_failed', %s, %s, %s)""",
                    (
                        metadata["version_id"],
                        actor.user_id,
                        actor.correlation_id,
                        Jsonb({"code": "generation_failed"}),
                    ),
                )
            raise ApiError(
                500,
                "report_generation_failed",
                "A falha de geração foi registrada",
                {
                    "report_id": str(metadata["report_id"]),
                    "version": metadata["version"],
                },
            ) from exc

    @staticmethod
    def _scope(
        organization_ids: frozenset[UUID] | None, alias: str = "v"
    ) -> tuple[str, list[Any]]:
        if organization_ids is None:
            return "", []
        return f" AND {alias}.organization_id = ANY(%s)", [list(organization_ids)]

    def list_reports(
        self, organization_ids, report_type, state, execution_id, page, page_size
    ):
        scope, scope_params = self._scope(organization_ids)
        filters = ["v.version_rank = 1"]
        values: list[Any] = []
        if report_type:
            filters.append("v.report_type = %s")
            values.append(report_type)
        if state:
            filters.append("v.state = %s")
            values.append(state)
        if execution_id:
            filters.append("v.execution_id = %s")
            values.append(execution_id)
        values.extend(scope_params)
        where = " AND ".join(filters) + scope
        base = """WITH ranked AS (SELECT rv.*, r.report_type,
                  row_number() OVER (PARTITION BY rv.report_id ORDER BY rv.version DESC) AS version_rank
                  FROM synergia.report_versions rv JOIN synergia.reports r ON r.id = rv.report_id), v AS
                  (SELECT * FROM ranked)"""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"{base} SELECT count(*) AS total FROM v WHERE {where}", values
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"{base} SELECT * FROM v WHERE {where} ORDER BY created_at DESC, report_id LIMIT %s OFFSET %s",
                [*values, page_size, (page - 1) * page_size],
            )
            return [self._metadata(row) for row in cursor.fetchall()], total

    def list_versions(self, report_id, organization_ids, page, page_size):
        scope, params = self._scope(organization_ids, "rv")
        values = [report_id, *params]
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*) AS total FROM synergia.report_versions rv WHERE rv.report_id = %s{scope}",
                values,
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""SELECT rv.*, r.report_type FROM synergia.report_versions rv
                JOIN synergia.reports r ON r.id = rv.report_id WHERE rv.report_id = %s{scope}
                ORDER BY rv.version DESC LIMIT %s OFFSET %s""",
                [*values, page_size, (page - 1) * page_size],
            )
            return [self._metadata(row) for row in cursor.fetchall()], total

    def get_version(self, report_id, version, organization_ids, audit_actor=None):
        scope, params = self._scope(organization_ids, "rv")
        version_filter = " AND rv.version = %s" if version is not None else ""
        values: list[Any] = [report_id]
        if version is not None:
            values.append(version)
        values.extend(params)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT rv.*, r.report_type, a.content AS data
                FROM synergia.report_versions rv JOIN synergia.reports r ON r.id = rv.report_id
                LEFT JOIN synergia.report_artifacts a ON a.report_version_id = rv.id AND a.artifact_type = 'data'
                WHERE rv.report_id = %s{version_filter}{scope}
                ORDER BY rv.version DESC LIMIT 1""",
                values,
            )
            row = cursor.fetchone()
            if row and audit_actor:
                cursor.execute(
                    """INSERT INTO synergia.report_events
                    (report_version_id, event_type, actor_user_id, correlation_id, payload)
                    VALUES (%s, 'report.consulted', %s, %s, '{}'::jsonb)""",
                    (row["id"], audit_actor.user_id, audit_actor.correlation_id),
                )
            return {**self._metadata(row), "data": row["data"]} if row else None

    def cancel(self, report_id, version, actor, reason):
        scope, params = self._scope(actor.scope_filter("report.cancel"), "rv")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT rv.*, r.report_type
                FROM synergia.report_versions rv
                JOIN synergia.reports r ON r.id = rv.report_id
                WHERE rv.report_id = %s AND rv.version = %s{scope}
                FOR UPDATE""",
                [report_id, version, *params],
            )
            row = cursor.fetchone()
            if row is None:
                return None
            if row["state"] != "generating":
                raise ApiError(
                    409,
                    "report_not_generating",
                    "Somente uma geração em andamento pode ser cancelada",
                )
            cursor.execute(
                """UPDATE synergia.report_versions
                SET state = 'cancelled', completed_at = now(),
                    cancellation_reason = %s
                WHERE id = %s RETURNING *""",
                (reason, row["id"]),
            )
            cancelled = cursor.fetchone()
            cursor.execute(
                """INSERT INTO synergia.report_events
                (report_version_id, event_type, actor_user_id, correlation_id, payload)
                VALUES (%s, 'report.generation_cancelled', %s, %s, %s)""",
                (
                    row["id"],
                    actor.user_id,
                    actor.correlation_id,
                    Jsonb({"reason": reason}),
                ),
            )
            return self._metadata({**cancelled, "report_type": row["report_type"]})


def get_report_repository() -> Generator[ReportRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ApiError(
            503, "database_not_configured", "Persistência de relatórios indisponível"
        )
    yield PostgresReportRepository(database_url)


def _page(items: list[dict], total: int, page: int, page_size: int) -> ReportPage:
    return ReportPage(
        items=[ReportVersionResponse.model_validate(i) for i in items],
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total=total,
            pages=math.ceil(total / page_size) if total else 0,
        ),
    )


def _authorize_organization(
    payload: CreateReportRequest,
    actor: ActorContext,
    auth: AuthorizationRepo,
    request: Request,
) -> None:
    if not actor.allows("report.generate", payload.organization_id):
        auth.audit_denial(
            actor, "report.generate", request, organization_id=payload.organization_id
        )
        raise ApiError(404, "resource_not_found", "Recurso não encontrado")


@router.post(
    "",
    response_model=ReportDataResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Gerar um relatório persistente",
)
def create_report(
    payload: CreateReportRequest,
    request: Request,
    actor: Annotated[ActorContext, Depends(require_permission("report.generate"))],
    authorization: AuthorizationRepo,
    repository: ReportRepository = Depends(get_report_repository),
) -> ReportDataResponse:
    _authorize_organization(payload, actor, authorization, request)
    return ReportDataResponse.model_validate(repository.generate(payload, actor))


@router.post(
    "/{report_id}/versions",
    response_model=ReportDataResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Gerar nova versão sem sobrescrever o histórico",
)
def create_report_version(
    report_id: UUID,
    payload: CreateReportRequest,
    request: Request,
    actor: Annotated[ActorContext, Depends(require_permission("report.generate"))],
    authorization: AuthorizationRepo,
    repository: ReportRepository = Depends(get_report_repository),
) -> ReportDataResponse:
    _authorize_organization(payload, actor, authorization, request)
    return ReportDataResponse.model_validate(
        repository.generate(payload, actor, report_id)
    )


@router.get(
    "",
    response_model=ReportPage,
    responses=ERROR_RESPONSES,
    summary="Listar catálogo de relatórios",
)
def list_reports(
    actor: Annotated[ActorContext, Depends(require_permission("report.read"))],
    report_type: ReportType | None = None,
    state: ReportState | None = None,
    execution_id: str | None = None,
    organization_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    repository: ReportRepository = Depends(get_report_repository),
) -> ReportPage:
    scope = actor.scope_filter("report.read")
    if organization_id is not None:
        scope = (
            frozenset({organization_id})
            if actor.allows("report.read", organization_id)
            else frozenset()
        )
    items, total = repository.list_reports(
        scope,
        report_type,
        state,
        execution_id,
        page,
        page_size,
    )
    return _page(items, total, page, page_size)


@router.get(
    "/{report_id}/versions",
    response_model=ReportPage,
    responses=ERROR_RESPONSES,
    summary="Listar histórico de versões",
)
def list_report_versions(
    report_id: UUID,
    actor: Annotated[ActorContext, Depends(require_permission("report.read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    repository: ReportRepository = Depends(get_report_repository),
) -> ReportPage:
    items, total = repository.list_versions(
        report_id, actor.scope_filter("report.read"), page, page_size
    )
    if total == 0:
        raise ApiError(404, "resource_not_found", "Recurso não encontrado")
    return _page(items, total, page, page_size)


@router.get(
    "/{report_id}",
    response_model=ReportDataResponse,
    responses=ERROR_RESPONSES,
    summary="Consultar a versão mais recente de um relatório",
)
def get_report(
    report_id: UUID,
    actor: Annotated[ActorContext, Depends(require_permission("report.read"))],
    repository: ReportRepository = Depends(get_report_repository),
) -> ReportDataResponse:
    item = repository.get_version(
        report_id, None, actor.scope_filter("report.read"), actor
    )
    if item is None:
        raise ApiError(404, "resource_not_found", "Recurso não encontrado")
    return ReportDataResponse.model_validate(item)


@router.get(
    "/{report_id}/versions/{version}",
    response_model=ReportDataResponse,
    responses=ERROR_RESPONSES,
    summary="Consultar dados de uma versão específica",
)
def get_report_version(
    report_id: UUID,
    version: int,
    actor: Annotated[ActorContext, Depends(require_permission("report.read"))],
    repository: ReportRepository = Depends(get_report_repository),
) -> ReportDataResponse:
    item = repository.get_version(
        report_id, version, actor.scope_filter("report.read"), actor
    )
    if item is None:
        raise ApiError(404, "resource_not_found", "Recurso não encontrado")
    return ReportDataResponse.model_validate(item)


@router.post(
    "/{report_id}/versions/{version}/cancel",
    response_model=ReportVersionResponse,
    responses=ERROR_RESPONSES,
    summary="Cancelar uma geração de relatório em andamento",
)
def cancel_report_version(
    report_id: UUID,
    version: int,
    payload: CancelReportRequest,
    actor: Annotated[ActorContext, Depends(require_permission("report.cancel"))],
    repository: ReportRepository = Depends(get_report_repository),
) -> ReportVersionResponse:
    item = repository.cancel(report_id, version, actor, payload.reason)
    if item is None:
        raise ApiError(404, "resource_not_found", "Recurso não encontrado")
    return ReportVersionResponse.model_validate(item)
