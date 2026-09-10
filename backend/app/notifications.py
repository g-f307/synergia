from __future__ import annotations

# Notification SQL is intentionally kept in aligned blocks for auditability.
# ruff: noqa: E501
import math
import os
from collections.abc import Generator
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query, Request
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from app.authorization import ActorContext, AuthorizationRepo, require_permission
from app.errors import ApiError, ErrorResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])

NotificationState = Literal["unread", "read"]
NotificationFilter = Literal["all", "unread", "read"]
NotificationSort = Literal["newest", "oldest"]

ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Ação não autorizada"},
    404: {"model": ErrorResponse, "description": "Notificação não encontrada"},
    409: {"model": ErrorResponse, "description": "Versão desatualizada"},
}


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class NotificationResponse(BaseModel):
    id: UUID
    type: str
    state: NotificationState
    title: str
    body: str
    occurrence_count: int
    organization_id: UUID
    resource_type: str
    resource_url: str | None
    resource_available: bool
    template_version: str
    version: int
    first_occurred_at: datetime
    last_occurred_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationResponse]
    pagination: Pagination
    sort: NotificationSort
    filter: NotificationFilter


class UnreadCountResponse(BaseModel):
    count: int


class ReadNotificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(gt=0)


class ReadAllResponse(BaseModel):
    count: int


class NotificationRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _visibility(actor: ActorContext, alias: str = "n") -> tuple[str, list[Any]]:
        notification_scopes = actor.scopes_for("notification.read")
        clauses: list[str] = []
        parameters: list[Any] = []
        for permission in (
            "execution.read",
            "pending.read",
            "report.read",
            "approval.read",
        ):
            source_scopes = actor.scopes_for(permission)
            if not source_scopes:
                continue
            clauses.append(f"({alias}.required_permission = %s")
            parameters.append(permission)
            allowed: set[UUID] | None
            if None in notification_scopes and None in source_scopes:
                allowed = None
            elif None in notification_scopes:
                allowed = {scope for scope in source_scopes if scope is not None}
            elif None in source_scopes:
                allowed = {scope for scope in notification_scopes if scope is not None}
            else:
                allowed = {
                    scope
                    for scope in notification_scopes.intersection(source_scopes)
                    if scope is not None
                }
            if allowed is not None:
                if not allowed:
                    clauses.pop()
                    parameters.pop()
                    continue
                clauses[-1] += f" AND {alias}.organization_id = ANY(%s)"
                parameters.append(list(allowed))
            clauses[-1] += ")"
        if not clauses:
            return "FALSE", []
        return "(" + " OR ".join(clauses) + ")", parameters

    @staticmethod
    def _resource_url(row: dict) -> str | None:
        if not row["resource_available"]:
            return None
        resource_id = quote(str(row["resource_id"]), safe="")
        if row["resource_type"] == "execution":
            return f"/executions/{resource_id}"
        if row["resource_type"] == "pending":
            return f"/pending-items?execution={resource_id}"
        if row["resource_type"] == "report":
            return f"/reports/{resource_id}"
        if row["resource_type"] == "approval":
            pending_id = row["parameters"].get("pending_id")
            return f"/pending-items/{quote(str(pending_id), safe='')}" if pending_id else None
        return None

    @staticmethod
    def _render(template: str, parameters: dict[str, Any]) -> str:
        allowed = {
            key: str(value)
            for key, value in parameters.items()
            if key in {"execution_id", "count", "version", "pending_id", "request_id"}
            and isinstance(value, str | int)
        }
        try:
            return template.format_map(allowed)
        except (KeyError, ValueError):
            return template

    def _serialize(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "type": row["notification_type"],
            "state": row["state"],
            "title": self._render(row["title_template"], row["parameters"]),
            "body": self._render(row["body_template"], row["parameters"]),
            "occurrence_count": row["occurrence_count"],
            "organization_id": row["organization_id"],
            "resource_type": row["resource_type"],
            "resource_url": self._resource_url(row),
            "resource_available": row["resource_available"],
            "template_version": row["template_version"],
            "version": row["version"],
            "first_occurred_at": row["first_occurred_at"],
            "last_occurred_at": row["last_occurred_at"],
            "read_at": row["read_at"],
        }

    @staticmethod
    def _select(
        locale_expression: str = "COALESCE(NULLIF(u.locale, 'es-ES'), 'pt-BR')",
    ) -> str:
        return f"""
            SELECT n.*, t.title_template, t.body_template,
              CASE n.resource_type
                WHEN 'execution' THEN EXISTS (
                  SELECT 1 FROM synergia.executions e
                  WHERE e.id = n.resource_id AND e.organization_id = n.organization_id
                )
                WHEN 'pending' THEN EXISTS (
                  SELECT 1 FROM synergia.pending_items pi
                  JOIN synergia.executions e ON e.id = pi.execution_id
                  WHERE pi.execution_id = n.resource_id
                    AND e.organization_id = n.organization_id
                )
                WHEN 'report' THEN EXISTS (
                  SELECT 1 FROM synergia.reports r
                  WHERE r.id::text = n.resource_id AND r.organization_id = n.organization_id
                )
                WHEN 'approval' THEN EXISTS (
                  SELECT 1 FROM synergia.approval_requests ar
                  WHERE ar.id::text = n.resource_id
                    AND ar.organization_id = n.organization_id
                )
                ELSE false
              END AS resource_available
            FROM synergia.notifications n
            JOIN synergia.identity_users u ON u.id = n.recipient_user_id
            JOIN synergia.notification_templates t
              ON t.notification_type = n.notification_type
             AND t.template_version = n.template_version
             AND t.locale = {locale_expression}
        """

    def list(
        self,
        actor: ActorContext,
        state_filter: NotificationFilter,
        sort: NotificationSort,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        visibility, scope_parameters = self._visibility(actor)
        state = "" if state_filter == "all" else " AND n.state = %s"
        parameters: list[Any] = [actor.user_id, *scope_parameters]
        if state:
            parameters.append(state_filter)
        base_where = f"n.recipient_user_id = %s AND n.state IN ('unread', 'read') AND {visibility}{state}"
        order = "DESC" if sort == "newest" else "ASC"
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*) AS total FROM synergia.notifications n WHERE {base_where}",
                parameters,
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                self._select()
                + f" WHERE {base_where} ORDER BY n.last_occurred_at {order}, n.id {order} LIMIT %s OFFSET %s",
                [*parameters, page_size, (page - 1) * page_size],
            )
            return [self._serialize(row) for row in cursor.fetchall()], total

    def unread_count(self, actor: ActorContext) -> int:
        visibility, parameters = self._visibility(actor)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*) AS total FROM synergia.notifications n WHERE n.recipient_user_id = %s AND n.state = 'unread' AND {visibility}",
                [actor.user_id, *parameters],
            )
            return cursor.fetchone()["total"]

    def mark_read(
        self, notification_id: UUID, expected_version: int, actor: ActorContext
    ) -> dict | None:
        visibility, parameters = self._visibility(actor)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT n.version, n.state FROM synergia.notifications n WHERE n.id = %s AND n.recipient_user_id = %s AND n.state IN ('unread', 'read') AND {visibility} FOR UPDATE",
                [notification_id, actor.user_id, *parameters],
            )
            current = cursor.fetchone()
            if current is None:
                return None
            if current["state"] == "read":
                if current["version"] != expected_version:
                    raise ApiError(
                        409,
                        "notification_version_conflict",
                        "A notificação foi atualizada",
                    )
            elif current["version"] != expected_version:
                raise ApiError(
                    409, "notification_version_conflict", "A notificação foi atualizada"
                )
            else:
                cursor.execute(
                    """UPDATE synergia.notifications
                       SET state = 'read', read_at = now(), updated_at = now(), version = version + 1
                       WHERE id = %s RETURNING *""",
                    (notification_id,),
                )
                cursor.execute(
                    """INSERT INTO synergia.notification_events (
                         notification_id, recipient_user_id, event_type,
                         actor_user_id, actor_session_id, correlation_id, payload
                       ) VALUES (%s, %s, 'notification.read', %s, %s, %s, %s)""",
                    (
                        notification_id,
                        actor.user_id,
                        actor.user_id,
                        actor.session_id,
                        actor.correlation_id,
                        Jsonb({"mode": "individual"}),
                    ),
                )
            cursor.execute(
                self._select() + " WHERE n.id = %s AND n.recipient_user_id = %s",
                (notification_id, actor.user_id),
            )
            return self._serialize(cursor.fetchone())

    def notification_organization(self, notification_id: UUID) -> UUID | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT organization_id FROM synergia.notifications WHERE id = %s",
                (notification_id,),
            )
            row = cursor.fetchone()
            return row["organization_id"] if row else None

    def mark_all_read(self, actor: ActorContext) -> int:
        visibility, parameters = self._visibility(actor)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE synergia.notifications n
                    SET state = 'read', read_at = now(), updated_at = now(), version = version + 1
                    WHERE n.recipient_user_id = %s AND n.state = 'unread' AND {visibility}
                    RETURNING n.id""",
                [actor.user_id, *parameters],
            )
            ids = [row["id"] for row in cursor.fetchall()]
            for notification_id in ids:
                cursor.execute(
                    """INSERT INTO synergia.notification_events (
                         notification_id, recipient_user_id, event_type,
                         actor_user_id, actor_session_id, correlation_id, payload
                       ) VALUES (%s, %s, 'notification.read', %s, %s, %s, %s)""",
                    (
                        notification_id,
                        actor.user_id,
                        actor.user_id,
                        actor.session_id,
                        actor.correlation_id,
                        Jsonb({"mode": "all"}),
                    ),
                )
            return len(ids)


def get_notification_repository() -> Generator[NotificationRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ApiError(503, "database_not_configured", "Notificações indisponíveis")
    yield NotificationRepository(database_url)


NotificationRepo = Annotated[
    NotificationRepository, Depends(get_notification_repository)
]
NotificationActor = Annotated[
    ActorContext, Depends(require_permission("notification.read"))
]


@router.get("", response_model=NotificationPage, responses=ERROR_RESPONSES)
def list_notifications(
    actor: NotificationActor,
    repository: NotificationRepo,
    state_filter: NotificationFilter = Query(default="all", alias="filter"),
    sort: NotificationSort = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> NotificationPage:
    items, total = repository.list(actor, state_filter, sort, page, page_size)
    return NotificationPage(
        items=items,
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total=total,
            pages=math.ceil(total / page_size) if total else 0,
        ),
        sort=sort,
        filter=state_filter,
    )


@router.get(
    "/unread-count", response_model=UnreadCountResponse, responses=ERROR_RESPONSES
)
def unread_count(
    actor: NotificationActor, repository: NotificationRepo
) -> UnreadCountResponse:
    return UnreadCountResponse(count=repository.unread_count(actor))


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    responses=ERROR_RESPONSES,
)
def mark_notification_read(
    notification_id: UUID,
    payload: ReadNotificationRequest,
    request: Request,
    actor: NotificationActor,
    repository: NotificationRepo,
    authorization: AuthorizationRepo,
) -> NotificationResponse:
    notification = repository.mark_read(notification_id, payload.version, actor)
    if notification is None:
        organization_id = repository.notification_organization(notification_id)
        if organization_id is not None:
            authorization.audit_denial(
                actor, "notification.read", request, organization_id
            )
        raise ApiError(404, "notification_not_found", "Notificação não encontrada")
    return NotificationResponse.model_validate(notification)


@router.post("/read-all", response_model=ReadAllResponse, responses=ERROR_RESPONSES)
def mark_all_notifications_read(
    actor: NotificationActor, repository: NotificationRepo
) -> ReadAllResponse:
    return ReadAllResponse(count=repository.mark_all_read(actor))
