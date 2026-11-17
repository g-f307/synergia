from __future__ import annotations

# SQL contracts stay visually aligned with their selected columns.
# ruff: noqa: E501
import math
import os
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.authorization import (
    ActorContext,
    require_execution_permission,
    require_permission,
)
from app.errors import ApiError, ErrorResponse
from app.execution import ExecutionState
from app.execution_filters import ExecutionQueryFilters, build_execution_predicate
from app.execution_filters import normalize_execution_period as _normalize_period
from app.execution_projection import ExecutionOutcome, legacy_lifecycle_sql
from app.execution_summary import (
    ExecutionOutcomeResponse,
    ExecutionSummary,
    read_execution_aggregation,
    start_execution_snapshot,
)
from app.pipeline_issue_query import pipeline_issue_query

router = APIRouter(prefix="/executions", tags=["execution-monitoring"])
ERRORS = {
    403: {"model": ErrorResponse, "description": "Evidência não permitida"},
    404: {"model": ErrorResponse, "description": "Recurso não encontrado"},
    422: {"model": ErrorResponse, "description": "Filtros inválidos"},
}


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class ExecutionCatalogItem(ExecutionOutcomeResponse):
    execution_id: str
    organization_id: UUID | None
    lifecycle: Literal["active", "completed", "partial", "failed"] = Field(
        deprecated=True, description="Legado; usar outcome para situações e métricas."
    )
    attempt: int
    source: str | None
    file_types: list[str]
    file_count: int
    rows_read: int
    error_count: int
    warning_count: int
    started_at: datetime
    finished_at: datetime | None


class ExecutionCatalogPage(BaseModel):
    items: list[ExecutionCatalogItem]
    pagination: Pagination
    sort: str
    generated_at: datetime


class Divergence(BaseModel):
    id: int
    source: str
    severity: Literal["error", "warning"]
    code: str
    scope: str
    workorder_number: str | None = None
    sheet_name: str | None = None
    row_number: int | None = None
    column_name: str | None = None
    reason: str
    details: dict[str, Any]
    occurred_at: datetime


class DivergencePage(BaseModel):
    items: list[Divergence]
    pagination: Pagination
    sort: str


class Classification(BaseModel):
    classification_id: str
    workorder_number: str
    lot_number: str | None = None
    serial_number: str | None = None
    rule_id: str
    rule_catalog_version: str
    state: str
    entity_type: str
    entity_id: str
    justification: str
    reason: str | None = None
    data_quality: str
    priority: str
    priority_score: int
    responsible_area: str | None = None
    classified_at: datetime
    evidence: dict[str, Any]


class PendingDetail(BaseModel):
    id: int
    workorder_number: str
    lot_number: str | None = None
    serial_number: str | None = None
    category: str
    reason: str | None = None
    status: str
    rule_id: str | None = None
    rule_catalog_version: str | None = None
    priority: str | None = None
    priority_score: int | None = None
    responsible_area: str | None = None
    evidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class Evidence(BaseModel):
    evidence_id: int
    evidence_type: Literal["source_file"] = "source_file"
    safe_name: str
    media_type: str | None = None
    size_bytes: int | None = None
    sha256: str
    available: bool


class ClassificationPage(BaseModel):
    items: list[Classification]
    pagination: Pagination
    sort: str


class PendingPage(BaseModel):
    items: list[PendingDetail]
    pagination: Pagination
    sort: str


class EvidencePage(BaseModel):
    items: list[Evidence]
    pagination: Pagination
    sort: str


class MonitoringRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def record_evidence_export(
        self, execution_id: str, evidence_id: int, actor: ActorContext,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO synergia.audit_events (
                    execution_id, entity_type, entity_id, event_type,
                    correlation_id, payload
                ) VALUES (%s, 'source_file', %s, 'artifact.export_prepared',
                          %s, %s)""",
                (execution_id, str(evidence_id), actor.correlation_id, Jsonb({
                    "actor_type": "user", "actor_identifier": str(actor.user_id),
                    "actor_session_id": str(actor.session_id), "version": 1,
                })),
            )

    def execution_exists(self, execution_id: str) -> bool:
        with self._connect() as connection:
            return connection.execute(
                "SELECT EXISTS(SELECT 1 FROM synergia.executions WHERE id=%s) AS found",
                (execution_id,),
            ).fetchone()["found"]

    def catalog(
        self,
        *,
        organization_scopes: frozenset[UUID] | None,
        organization_id: UUID | None,
        status: str | None,
        lifecycle: str | None,
        source: str | None,
        file_type: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
        execution_id: str | None,
        page: int,
        page_size: int,
        sort: str,
        outcome: ExecutionOutcome | None = None,
    ) -> tuple[list[dict], int]:
        if organization_scopes is not None and not organization_scopes:
            return [], 0
        predicate = build_execution_predicate(
            ExecutionQueryFilters(
                organization_id=organization_id,
                status=status,
                lifecycle=lifecycle,
                outcome=outcome,
                source=source,
                file_type=file_type,
                date_from=date_from,
                date_to=date_to,
                execution_id=execution_id,
            ),
            organization_scopes=organization_scopes,
        )
        where, params = predicate.where, predicate.parameters
        lifecycle_sql = legacy_lifecycle_sql("e", "status")
        direction = "DESC" if sort == "newest" else "ASC"
        with self._connect() as connection:
            start_execution_snapshot(connection)
            total = connection.execute(
                f"SELECT count(*) AS total FROM synergia.executions e WHERE {where}",
                params,
            ).fetchone()["total"]
            rows = connection.execute(
                f"""SELECT e.id AS execution_id,e.organization_id,e.status,
                           {lifecycle_sql} AS lifecycle,e.attempt,e.source,
                           COALESCE(files.file_types,ARRAY[]::text[]) AS file_types,
                           COALESCE(files.file_count,0) AS file_count,
                           COALESCE(summary.rows_read,0) AS rows_read,
                           COALESCE(summary.error_count,0) AS error_count,
                           COALESCE(summary.warning_count,0) AS warning_count,
                           e.started_at,e.finished_at
                    FROM synergia.executions e
                    LEFT JOIN LATERAL (
                        SELECT array_agg(DISTINCT sf.extension ORDER BY sf.extension)
                                   FILTER (WHERE sf.extension IS NOT NULL) AS file_types,
                               count(*) AS file_count
                        FROM synergia.source_files sf WHERE sf.execution_id=e.id
                    ) files ON TRUE
                    LEFT JOIN synergia.pipeline_summaries summary
                      ON summary.execution_id=e.id
                    WHERE {where}
                    ORDER BY e.started_at {direction},e.id {direction}
                    LIMIT %s OFFSET %s""",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return [dict(row) for row in rows], total

    def summary(
        self, filters: ExecutionQueryFilters,
        *, organization_scopes: frozenset[UUID] | None,
    ) -> ExecutionSummary:
        with self._connect() as connection:
            start_execution_snapshot(connection)
            return read_execution_aggregation(
                connection, filters, organization_scopes=organization_scopes,
                permission="execution.read",
            ).summary

    def divergences(
        self,
        execution_id: str,
        *,
        source: str | None,
        severity: str | None,
        code: str | None,
        workorder: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
        page: int,
        page_size: int,
        sort: str,
    ) -> tuple[list[dict], int]:
        query = pipeline_issue_query(
            execution_id, projection="execution", organization_scopes=None,
            source=source, severity=severity, code=code, workorder=workorder,
            date_from=date_from, date_to=date_to, sort=sort,
        )
        with self._connect() as connection:
            start_execution_snapshot(connection)
            return query.page(connection, page=page, page_size=page_size)

    def classifications(
        self, execution_id: str, *, page: int, page_size: int, sort: str
    ) -> tuple[list[dict], int]:
        direction = "DESC" if sort == "newest" else "ASC"
        with self._connect() as connection:
            total = connection.execute(
                "SELECT count(*) AS total FROM synergia.classifications WHERE execution_id=%s",
                (execution_id,),
            ).fetchone()["total"]
            rows = connection.execute(
                """SELECT c.classification_id,w.workorder_number,l.lot_number,
                          s.serial_number,c.rule_id,c.rule_catalog_version,c.state,
                          c.entity_type,c.entity_id,c.justification,c.reason,
                          c.data_quality,c.priority,c.priority_score,c.responsible_area,
                          c.classified_at,c.evidence
                   FROM synergia.classifications c JOIN synergia.workorders w ON w.id=c.workorder_id
                   LEFT JOIN synergia.lots l ON l.id=c.lot_id
                   LEFT JOIN synergia.serials s ON s.id=c.serial_id
                   WHERE c.execution_id=%s
                   ORDER BY c.classified_at """
                + direction
                + ",c.classification_id "
                + direction
                + " LIMIT %s OFFSET %s",
                (execution_id, page_size, (page - 1) * page_size),
            ).fetchall()
        return [dict(row) for row in rows], total

    def pending(
        self, execution_id: str, *, page: int, page_size: int, sort: str
    ) -> tuple[list[dict], int]:
        direction = "DESC" if sort == "newest" else "ASC"
        with self._connect() as connection:
            total = connection.execute(
                "SELECT count(*) AS total FROM synergia.pending_items WHERE execution_id=%s",
                (execution_id,),
            ).fetchone()["total"]
            rows = connection.execute(
                """SELECT p.id,w.workorder_number,l.lot_number,s.serial_number,
                          p.category,p.reason,p.status,p.rule_id,p.rule_catalog_version,
                          p.priority,p.priority_score,p.responsible_area,p.evidence,
                          p.created_at,p.updated_at
                   FROM synergia.pending_items p JOIN synergia.workorders w ON w.id=p.workorder_id
                   LEFT JOIN synergia.lots l ON l.id=p.lot_id LEFT JOIN synergia.serials s ON s.id=p.serial_id
                   WHERE p.execution_id=%s
                   ORDER BY p.created_at """
                + direction
                + ",p.id "
                + direction
                + " LIMIT %s OFFSET %s",
                (execution_id, page_size, (page - 1) * page_size),
            ).fetchall()
        return [dict(row) for row in rows], total

    def evidences(
        self, execution_id: str, *, page: int, page_size: int, sort: str
    ) -> tuple[list[dict], int]:
        direction = "DESC" if sort == "newest" else "ASC"
        with self._connect() as connection:
            total = connection.execute(
                """SELECT count(*) AS total FROM synergia.source_files sf
                   JOIN synergia.file_inspections fi ON fi.id=sf.inspection_id
                   WHERE sf.execution_id=%s AND fi.decision='accepted'""",
                (execution_id,),
            ).fetchone()["total"]
            rows = connection.execute(
                """SELECT sf.id AS evidence_id,sf.extension,sf.detected_media_type AS media_type,
                          sf.size_bytes,sf.content_hash AS sha256,sf.storage_key
                   FROM synergia.source_files sf JOIN synergia.file_inspections fi ON fi.id=sf.inspection_id
                   WHERE sf.execution_id=%s AND fi.decision='accepted'
                   ORDER BY sf.id """
                + direction
                + " LIMIT %s OFFSET %s",
                (execution_id, page_size, (page - 1) * page_size),
            ).fetchall()
        root = Path(os.getenv("IMPORT_STORAGE_DIR", "/tmp/synergia-imports")).resolve()
        items = []
        for row in rows:
            item = dict(row)
            storage_key = item.pop("storage_key", None)
            path = (root / storage_key).resolve() if storage_key else None
            item["safe_name"] = f"evidence-{row['evidence_id']}.{row['extension']}"
            item["available"] = bool(
                path is not None and root in path.parents and path.is_file()
            )
            items.append(item)
        return items, total

    def evidence_file(self, execution_id: str, evidence_id: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT sf.id,sf.storage_key,sf.extension,
                          sf.detected_media_type AS media_type,fi.decision
                   FROM synergia.source_files sf
                   JOIN synergia.file_inspections fi ON fi.id=sf.inspection_id
                   WHERE sf.execution_id=%s AND sf.id=%s""",
                (execution_id, evidence_id),
            ).fetchone()
        return dict(row) if row else None


def get_monitoring_repository() -> Generator[MonitoringRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL não configurada")
    yield MonitoringRepository(database_url)


Repository = Annotated[MonitoringRepository, Depends(get_monitoring_repository)]


def _ensure_execution(repository: MonitoringRepository, execution_id: str) -> None:
    if not repository.execution_exists(execution_id):
        raise ApiError(
            404,
            "execution_not_found",
            "Execução não encontrada",
            {"execution_id": execution_id},
        )


def _page(
    model,
    items: list[dict],
    page: int,
    page_size: int,
    total: int,
    sort: str,
    **extra: Any,
):
    return model(
        items=items,
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total=total,
            pages=math.ceil(total / page_size) if total else 0,
        ),
        sort=sort,
        **extra,
    )


def execution_query_filters(
    organization_id: UUID | None = None,
    status: ExecutionState | None = None,
    lifecycle: Annotated[
        Literal["active", "completed", "partial", "failed"] | None,
        Query(deprecated=True, description="Filtro legado; preferir outcome."),
    ] = None,
    outcome: ExecutionOutcome | None = None,
    source: str | None = None,
    file_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    execution_id: str | None = None,
) -> ExecutionQueryFilters:
    return ExecutionQueryFilters(
        organization_id=organization_id, status=status.value if status else None,
        lifecycle=lifecycle, outcome=outcome, source=source, file_type=file_type,
        date_from=date_from, date_to=date_to, execution_id=execution_id,
    )


CatalogFilters = Annotated[ExecutionQueryFilters, Depends(execution_query_filters)]


@router.get(
    "/summary", response_model=ExecutionSummary,
    responses={401: {"model": ErrorResponse}, **ERRORS},
    summary="Agregar todas as execuções do recorte autorizado",
    description=(
        "Não usa paginação. Total inclui active/completed/partial/skipped_duplicate/"
        "failed/cancelled/unknown. Datas exigem fuso, são normalizadas em UTC e "
        "ambos os limites são inclusivos. O escopo deriva somente de execution.read."
    ),
)
def get_execution_summary(
    actor: Annotated[ActorContext, Depends(require_permission("execution.read"))],
    repository: Repository,
    filters: CatalogFilters,
) -> ExecutionSummary:
    return repository.summary(filters, organization_scopes=actor.scope_filter("execution.read"))


@router.get(
    "", response_model=ExecutionCatalogPage, responses=ERRORS,
    summary="Listar execuções autorizadas",
)
def list_executions(
    repository: Repository,
    actor: Annotated[ActorContext, Depends(require_permission("execution.read"))],
    filters: CatalogFilters,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Literal["oldest", "newest"] = "newest",
) -> ExecutionCatalogPage:
    items, total = repository.catalog(
        organization_scopes=actor.scope_filter("execution.read"),
        organization_id=filters.organization_id,
        status=filters.status,
        lifecycle=filters.lifecycle,
        outcome=filters.outcome,
        source=filters.source,
        file_type=filters.file_type,
        date_from=filters.date_from,
        date_to=filters.date_to,
        execution_id=filters.execution_id,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    return _page(
        ExecutionCatalogPage,
        items,
        page,
        page_size,
        total,
        sort,
        generated_at=datetime.now(UTC),
    )


@router.get(
    "/{execution_id}/divergences", response_model=DivergencePage, responses=ERRORS,
    dependencies=[Depends(require_execution_permission("artifact.read"))],
)
def list_divergences(
    execution_id: str,
    repository: Repository,
    source: str | None = None,
    severity: Literal["error", "warning"] | None = None,
    code: str | None = None,
    workorder: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Literal["oldest", "newest"] = "oldest",
) -> DivergencePage:
    _ensure_execution(repository, execution_id)
    date_from, date_to = _normalize_period(date_from, date_to)
    items, total = repository.divergences(
        execution_id,
        source=source,
        severity=severity,
        code=code,
        workorder=workorder,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    return DivergencePage(
        items=items,
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total=total,
            pages=math.ceil(total / page_size) if total else 0,
        ),
        sort=sort,
    )


@router.get(
    "/{execution_id}/classifications",
    response_model=ClassificationPage,
    responses=ERRORS,
    dependencies=[Depends(require_execution_permission("execution.read"))],
)
def list_classifications(
    execution_id: str,
    repository: Repository,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=1000)] = 20,
    sort: Literal["oldest", "newest"] = "oldest",
) -> ClassificationPage:
    _ensure_execution(repository, execution_id)
    items, total = repository.classifications(
        execution_id, page=page, page_size=page_size, sort=sort
    )
    return _page(ClassificationPage, items, page, page_size, total, sort)


@router.get(
    "/{execution_id}/pending-items",
    response_model=PendingPage,
    responses=ERRORS,
    dependencies=[Depends(require_execution_permission("execution.read"))],
)
def list_pending(
    execution_id: str,
    repository: Repository,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Literal["oldest", "newest"] = "oldest",
) -> PendingPage:
    _ensure_execution(repository, execution_id)
    items, total = repository.pending(
        execution_id, page=page, page_size=page_size, sort=sort
    )
    return _page(PendingPage, items, page, page_size, total, sort)


@router.get(
    "/{execution_id}/evidences", response_model=EvidencePage, responses=ERRORS,
    dependencies=[Depends(require_execution_permission("artifact.read"))],
)
def list_evidences(
    execution_id: str,
    repository: Repository,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Literal["oldest", "newest"] = "oldest",
) -> EvidencePage:
    _ensure_execution(repository, execution_id)
    items, total = repository.evidences(
        execution_id, page=page, page_size=page_size, sort=sort
    )
    return _page(EvidencePage, items, page, page_size, total, sort)


@router.get(
    "/{execution_id}/evidences/{evidence_id}/download",
    responses=ERRORS,
    response_class=FileResponse,
)
def download_evidence(
    execution_id: str, evidence_id: int,
    actor: Annotated[
        ActorContext, Depends(require_execution_permission("artifact.export"))
    ],
    repository: Repository,
) -> FileResponse:
    _ensure_execution(repository, execution_id)
    evidence = repository.evidence_file(execution_id, evidence_id)
    if evidence is None:
        raise ApiError(
            404,
            "evidence_not_found",
            "Evidência não encontrada",
            {"evidence_id": evidence_id},
        )
    if evidence["decision"] != "accepted" or not evidence.get("storage_key"):
        raise ApiError(
            403, "evidence_not_allowed", "A evidência não está liberada para download"
        )
    root = Path(os.getenv("IMPORT_STORAGE_DIR", "/tmp/synergia-imports")).resolve()
    path = (root / evidence["storage_key"]).resolve()
    if root not in path.parents or not path.is_file():
        raise ApiError(
            404,
            "evidence_not_found",
            "Evidência não encontrada",
            {"evidence_id": evidence_id},
        )
    repository.record_evidence_export(execution_id, evidence_id, actor)
    return FileResponse(
        path,
        media_type=evidence.get("media_type"),
        filename=f"evidence-{evidence_id}.{evidence['extension']}",
    )
