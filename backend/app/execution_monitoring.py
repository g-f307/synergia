from __future__ import annotations

# SQL contracts stay visually aligned with their selected columns.
# ruff: noqa: E501
import math
import os
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from psycopg.rows import dict_row
from pydantic import BaseModel

from app.authorization import require_execution_permission
from app.errors import ApiError, ErrorResponse

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

    def execution_exists(self, execution_id: str) -> bool:
        with self._connect() as connection:
            return connection.execute(
                "SELECT EXISTS(SELECT 1 FROM synergia.executions WHERE id=%s) AS found",
                (execution_id,),
            ).fetchone()["found"]

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
        clauses = ["pi.execution_id=%s"]
        params: list[Any] = [execution_id]
        for expression, value in (
            ("sf.source=%s", source),
            ("pi.severity=%s", severity),
            ("pi.code=%s", code),
            ("pi.created_at >= %s", date_from),
            ("pi.created_at <= %s", date_to),
        ):
            if value is not None:
                clauses.append(expression)
                params.append(value)
        workorder_expr = "COALESCE(pi.details->>'workorder_number', nr.normalized_values->>'workorder_number')"
        if workorder is not None:
            clauses.append(f"{workorder_expr}=%s")
            params.append(workorder)
        where = " AND ".join(clauses)
        direction = "DESC" if sort == "newest" else "ASC"
        joins = """JOIN synergia.source_files sf ON sf.id=pi.source_file_id
                   LEFT JOIN synergia.normalized_records nr ON nr.imported_record_id=pi.imported_record_id"""
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT count(*) AS total FROM synergia.pipeline_issues pi {joins} WHERE {where}",
                params,
            ).fetchone()["total"]
            rows = connection.execute(
                f"""SELECT pi.id,sf.source,pi.severity,pi.code,pi.scope,
                           {workorder_expr} AS workorder_number,pi.sheet_name,
                           pi.row_number,pi.column_name,pi.reason,pi.details,
                           pi.created_at AS occurred_at
                    FROM synergia.pipeline_issues pi {joins} WHERE {where}
                    ORDER BY pi.created_at {direction},pi.id {direction}
                    LIMIT %s OFFSET %s""",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return [dict(row) for row in rows], total

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


def _page(model, items: list[dict], page: int, page_size: int, total: int, sort: str):
    return model(
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
    if date_from and date_to and date_from > date_to:
        raise ApiError(
            422, "invalid_period", "O início do período deve anteceder o fim"
        )
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
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
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
    dependencies=[Depends(require_execution_permission("artifact.export"))],
)
def download_evidence(
    execution_id: str, evidence_id: int, repository: Repository
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
    return FileResponse(
        path,
        media_type=evidence.get("media_type"),
        filename=f"evidence-{evidence_id}.{evidence['extension']}",
    )
