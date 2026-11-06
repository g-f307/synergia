from __future__ import annotations

import csv
import io
import json
import math
import os
import re
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.authorization import ActorContext, AuthorizationRepo, require_permission
from app.errors import ApiError, ErrorResponse
from app.execution import ExecutionState

FORMAT_VERSION = "1.0.0"
MAX_EVENTS = 10_000
MAX_BYTES = 8 * 1024 * 1024
MAX_INTERVAL = timedelta(days=31)
ORIGINS = frozenset(
    {
        "audit_events",
        "identity_access_events",
        "report_events",
        "approval_events",
        "notification_events",
        "notification_template_events",
        "data_operation_events",
        "approval_policy_activation_events",
        "email_delivery_attempts",
        "email_delivery_reconciliations",
        "audit_export_events",
    }
)
STATES = frozenset(state.value for state in ExecutionState) | {
    "draft",
    "submitted",
    "in_review",
    "approved",
    "rejected",
    "returned",
    "queued",
    "processing",
    "sent",
    "retry",
}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
SENSITIVE = re.compile(
    r"(?i)(?:bearer|password|passwd|secret|cookie|token|eyJ[A-Za-z0-9_-]*\.)"
)
router = APIRouter(prefix="/audit/events", tags=["audit"])
RESPONSES = {
    code: {"model": ErrorResponse} for code in (401, 403, 413, 422, 429, 500, 503)
}


def safe_identifier(value: str) -> str:
    route = (
        len(value) <= 128
        and ".." not in value
        and re.fullmatch(r"/[A-Za-z0-9_/{}/-]+", value)
    )
    if not (IDENTIFIER.fullmatch(value) or route) or SENSITIVE.search(value):
        return "[redacted]"
    return value


class AuditQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor_id: UUID | None = None
    action: str | None = Field(
        default=None, max_length=96, pattern=r"^[a-z][a-z0-9_.]*$"
    )
    resource_type: str | None = Field(
        default=None, max_length=48, pattern=r"^[a-z][a-z0-9_]*$"
    )
    resource_id: str | None = Field(default=None, min_length=1, max_length=128)
    outcome: Literal["started", "success", "failure"] | None = None
    sort: Literal["oldest", "newest"] = "oldest"
    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=100, ge=1, le=100)
    format: Literal["json", "csv"] = "json"

    @field_validator("occurred_from", "occurred_to")
    @classmethod
    def aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.utcoffset() is None:
                raise ValueError("Informe o fuso horario explicitamente")
            return value.astimezone(UTC)
        return None

    @field_validator("resource_id")
    @classmethod
    def approved_identifier(cls, value: str | None) -> str | None:
        if value is not None and safe_identifier(value) == "[redacted]":
            raise ValueError("Identificador fora do contrato de auditoria")
        return value

    @model_validator(mode="after")
    def bounded_period(self) -> AuditQuery:
        if self.occurred_from is None:
            self.occurred_from = self.occurred_to - timedelta(days=1)
        interval = self.occurred_to - self.occurred_from
        if interval <= timedelta(0) or interval > MAX_INTERVAL:
            raise ValueError("O periodo deve ser positivo e de no maximo 31 dias")
        return self

    def filters(self) -> dict:
        return self.model_dump(mode="json", exclude={"page", "page_size", "format"})


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    occurred_at: datetime
    organization_id: UUID | None
    actor_id: UUID | None
    actor_type: Literal["user", "system", "unknown"]
    action: str = Field(max_length=96, pattern=r"^[a-z][a-z0-9_.]*$")
    resource_type: str = Field(max_length=48, pattern=r"^[a-z][a-z0-9_]*$")
    resource_id: str
    outcome: Literal["started", "success", "failure"]
    correlation_id: UUID | None
    metadata: dict
    origin: str


class AuditPage(BaseModel):
    format_version: str = FORMAT_VERSION
    timezone: str = "UTC"
    generated_at: datetime
    filters: dict
    items: list[AuditEvent]
    page: int
    page_size: int
    total: int
    pages: int
    sort: str


class AuditExportDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal["1.0.0"] = FORMAT_VERSION
    timezone: Literal["UTC"] = "UTC"
    generated_at: datetime
    event_count: int = Field(ge=0, le=MAX_EVENTS)
    filters: dict
    events: list[AuditEvent]


def sanitize_event(row: dict) -> AuditEvent:
    # Allowlist both keys and value domains. Never copy arbitrary source payloads.
    if row["origin"] not in ORIGINS:
        raise ApiError(500, "audit_invalid_event", "Evento fora do contrato")
    metadata = {}
    raw = row.get("metadata") or {}
    if not isinstance(raw, dict):
        raise ApiError(500, "audit_invalid_event", "Evento fora do contrato")
    for key in (
        "version",
        "state_version",
        "record_count",
        "artifact_count",
        "duration_ms",
        "attempt_number",
        "event_count",
    ):
        value = raw.get(key)
        if type(value) is int and 0 <= value <= 2**63 - 1:
            metadata[key] = value
    for key in ("consent", "is_active"):
        if type(raw.get(key)) is bool:
            metadata[key] = raw[key]
    for key in ("from_state", "to_state"):
        value = raw.get(key)
        if isinstance(value, str) and value in STATES:
            metadata[key] = value
    if raw.get("format") in ("json", "csv"):
        metadata["format"] = raw["format"]
    result = AuditEvent.model_validate(
        {key: row[key] for key in AuditEvent.model_fields if key != "metadata"}
        | {"metadata": metadata}
    )
    for key in ("id", "resource_id"):
        setattr(result, key, safe_identifier(getattr(result, key)))
    if SENSITIVE.search(result.resource_type):
        result.resource_id = "[redacted]"
    if result.occurred_at.utcoffset() is None:
        raise ApiError(500, "audit_invalid_event", "Evento sem fuso horario")
    result.occurred_at = result.occurred_at.astimezone(UTC)
    return result


class AuditRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def read(
        self,
        query: AuditQuery,
        *,
        limit: int,
        offset: int = 0,
        exclude_export: UUID | None = None,
    ) -> tuple[list[dict], int]:
        clauses = ["occurred_at >= %s", "occurred_at < %s"]
        values: list = [query.occurred_from, query.occurred_to]
        if query.organization_id is None:
            clauses.append("organization_id IS NULL")
        else:
            clauses.append("organization_id = %s")
            values.append(query.organization_id)
        for name in ("actor_id", "action", "resource_type", "resource_id", "outcome"):
            if (value := getattr(query, name)) is not None:
                clauses.append(f"{name} = %s")
                values.append(value)
        if exclude_export is not None:
            clauses.append("(origin <> 'audit_export_events' OR resource_id <> %s)")
            values.append(str(exclude_export))
        where = " AND ".join(clauses)
        direction = "ASC" if query.sort == "oldest" else "DESC"
        with self._connect() as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            connection.execute("SET LOCAL statement_timeout = '5s'")
            total = connection.execute(
                f"SELECT count(*) AS total FROM (SELECT 1 "
                f"FROM synergia.audit_event_catalog WHERE {where} "
                "LIMIT %s) bounded",
                [*values, MAX_EVENTS + 1],
            ).fetchone()["total"]
            if total > MAX_EVENTS:
                raise ApiError(
                    413,
                    "audit_volume_limit",
                    "Divida o periodo ou refine os filtros; limite de 10000 eventos",
                )
            rows = connection.execute(
                f"SELECT * FROM synergia.audit_event_catalog WHERE {where} "
                f'ORDER BY occurred_at {direction}, id COLLATE "C" {direction} '
                "LIMIT %s OFFSET %s",
                [*values, limit, offset],
            ).fetchall()
        return list(rows), total

    def record_export(
        self,
        export_id: UUID,
        action: str,
        actor: ActorContext,
        query: AuditQuery,
        count: int | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO synergia.audit_export_events (
                    export_id, action, actor_user_id, actor_session_id,
                    organization_id, correlation_id, export_format, filters,
                    event_count
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    export_id,
                    action,
                    actor.user_id,
                    actor.session_id,
                    query.organization_id,
                    actor.correlation_id,
                    query.format,
                    Jsonb(query.filters()),
                    count,
                ),
            )


def get_audit_repository() -> Generator[AuditRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ApiError(503, "database_not_configured", "Auditoria indisponivel")
    yield AuditRepository(database_url)


def authorize_scope(
    actor: ActorContext,
    query: AuditQuery,
    permissions: tuple[str, ...],
    authorization: AuthorizationRepo,
    request: Request,
) -> None:
    if any(
        not actor.allows(permission, query.organization_id)
        for permission in permissions
    ):
        # The requested organization is untrusted: logging it as a foreign key
        # would distinguish nonexistent organizations by failing with a 500.
        authorization.audit_denial(actor, permissions[-1], request)
        raise ApiError(403, "access_denied", "Acao nao autorizada")


def csv_cell(value: object) -> str:
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = "" if value is None else str(value)
    if text.startswith(("\t", "\r", "\n")) or text.lstrip().startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + text
    return text


def render_export(
    events: list[AuditEvent],
    query: AuditQuery,
    generated_at: datetime,
) -> bytes:
    manifest = {
        "format_version": FORMAT_VERSION,
        "timezone": "UTC",
        "generated_at": generated_at.isoformat(),
        "event_count": len(events),
        "filters": query.filters(),
    }
    document = AuditExportDocument(**manifest, events=events)
    manifest = document.model_dump(mode="json", exclude={"events"})
    if query.format == "json":
        content = document.model_dump_json().encode("utf-8")
    else:
        output = io.StringIO(newline="")
        fields = ["record_type", *manifest, *AuditEvent.model_fields]
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\r\n")
        writer.writeheader()
        writer.writerow(
            {
                key: csv_cell(value)
                for key, value in (manifest | {"record_type": "manifest"}).items()
            }
        )
        for event in events:
            writer.writerow(
                {
                    key: csv_cell(value)
                    for key, value in (
                        event.model_dump(mode="json") | {"record_type": "event"}
                    ).items()
                }
            )
        content = output.getvalue().encode("utf-8")
    if len(content) > MAX_BYTES:
        raise ApiError(413, "audit_size_limit", "Divida o periodo da exportacao")
    return content


@router.get(
    "",
    response_model=AuditPage,
    responses=RESPONSES,
    summary="Consultar eventos de auditoria sanitizados",
)
def list_events(
    request: Request,
    actor: Annotated[ActorContext, Depends(require_permission("audit.read"))],
    authorization: AuthorizationRepo,
    query: Annotated[AuditQuery, Query()],
    repository: Annotated[AuditRepository, Depends(get_audit_repository)],
) -> AuditPage:
    authorize_scope(actor, query, ("audit.read",), authorization, request)
    rows, total = repository.read(
        query, limit=query.page_size, offset=(query.page - 1) * query.page_size
    )
    return AuditPage(
        generated_at=datetime.now(UTC),
        filters=query.filters(),
        items=[sanitize_event(row) for row in rows],
        total=total,
        page=query.page,
        page_size=query.page_size,
        pages=math.ceil(total / query.page_size),
        sort=query.sort,
    )


@router.get(
    "/export",
    responses=RESPONSES
    | {200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
    summary="Exportar auditoria em JSON ou CSV",
    response_model=AuditExportDocument,
    response_class=JSONResponse,
)
def export_events(
    request: Request,
    actor: Annotated[ActorContext, Depends(require_permission("audit.export"))],
    authorization: AuthorizationRepo,
    query: Annotated[AuditQuery, Query()],
    repository: Annotated[AuditRepository, Depends(get_audit_repository)],
) -> Response:
    authorize_scope(
        actor, query, ("audit.read", "audit.export"), authorization, request
    )
    export_id = uuid4()
    generated_at = datetime.now(UTC)
    repository.record_export(export_id, "requested", actor, query)
    try:
        rows, _ = repository.read(query, limit=MAX_EVENTS, exclude_export=export_id)
        events = [sanitize_event(row) for row in rows]
        content = render_export(events, query, generated_at)
        repository.record_export(export_id, "succeeded", actor, query, len(events))
    except Exception:
        # Persist a terminal outcome, then propagate the original failure.
        # Never publish partial content, exception messages or exported records.
        repository.record_export(export_id, "failed", actor, query)
        raise
    media_type = (
        "application/json; charset=utf-8"
        if query.format == "json"
        else "text/csv; charset=utf-8"
    )
    filename = f"audit-{export_id}.{query.format}"
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Audit-Export-Id": str(export_id),
        },
    )
