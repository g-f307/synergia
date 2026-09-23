from __future__ import annotations

# Administrative SQL is intentionally kept in complete, aligned clauses.
# ruff: noqa: E501
import math
import os
import re
from collections.abc import Generator
from datetime import datetime
from string import Formatter
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query
from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.authorization import ActorContext, require_global_permission
from app.email_delivery import EmailConfig
from app.errors import ApiError, ErrorResponse

TemplateChannel = Literal["in_app", "email"]
TemplateLocale = Literal["pt-BR", "en-US"]
TemplateState = Literal["draft", "active", "inactive"]

router = APIRouter(
    prefix="/admin/notification-templates",
    tags=["notification template administration"],
    dependencies=[Depends(require_global_permission("access.admin"))],
)

ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Ação não autorizada"},
    404: {"model": ErrorResponse, "description": "Template não encontrado"},
    409: {"model": ErrorResponse, "description": "Conflito de versão ou estado"},
    422: {"model": ErrorResponse, "description": "Conteúdo inválido"},
    503: {"model": ErrorResponse, "description": "Administração indisponível"},
}

ACTIVE_HTML = re.compile(r"<\s*/?\s*[a-z][^>]*>|\bon[a-z]+\s*=", re.IGNORECASE)
UNSAFE_URI = re.compile(r"\b(?:javascript|data|vbscript|file)\s*:", re.IGNORECASE)
SECRET_MATERIAL = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"\b(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u202a-\u202e\u2066-\u2069]")

SYNTHETIC_VALUES = {
    "execution_id": "EXEC-SYNTHETIC-001",
    "count": "3",
    "version": "2",
    "pending_id": "PENDING-SYNTHETIC-001",
    "request_id": "REQUEST-SYNTHETIC-001",
}


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("o campo deve conter texto")
    return normalized


def _reason(value: str) -> str:
    normalized = _text(value)
    if (
        ACTIVE_HTML.search(normalized)
        or SECRET_MATERIAL.search(normalized)
        or CONTROL_CHARACTERS.search(normalized)
    ):
        raise ValueError("a justificativa contém conteúdo não permitido")
    return normalized


class DraftCreate(StrictRequest):
    notification_type: str = Field(min_length=3, max_length=120)
    channel: TemplateChannel
    locale: TemplateLocale
    title_template: str = Field(min_length=1, max_length=200)
    body_template: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("notification_type", "title_template", "body_template")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _text(value)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _reason(value)


class DraftUpdate(StrictRequest):
    row_version: int = Field(ge=1)
    title_template: str = Field(min_length=1, max_length=200)
    body_template: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("title_template", "body_template")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _text(value)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _reason(value)


class TransitionRequest(StrictRequest):
    row_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _reason(value)


class EventPolicy(BaseModel):
    notification_type: str
    required_permission: str
    resource_type: str
    allowed_placeholders: list[str]


class TemplatePolicyResponse(BaseModel):
    events: list[EventPolicy]
    channels: list[TemplateChannel]
    locales: list[TemplateLocale]
    external_delivery: Literal["disabled", "local_capture", "unavailable"]
    external_delivery_corporate: bool = False


class TemplateRevisionResponse(BaseModel):
    id: UUID
    notification_type: str
    channel: TemplateChannel
    locale: TemplateLocale
    version_number: int
    version_label: str
    state: TemplateState
    title_template: str
    body_template: str
    allowed_placeholders: list[str]
    row_version: int
    created_by_user_id: UUID | None
    created_reason: str
    created_at: datetime
    updated_by_user_id: UUID | None
    updated_reason: str | None
    updated_at: datetime
    published_by_user_id: UUID | None
    published_reason: str | None
    published_at: datetime | None
    deactivated_by_user_id: UUID | None = None
    deactivated_reason: str | None = None
    deactivated_at: datetime | None = None


class TemplatePage(BaseModel):
    items: list[TemplateRevisionResponse]
    page: int
    page_size: int
    total: int
    pages: int
    sort: Literal["newest", "oldest"]


class PreviewResponse(BaseModel):
    title: str
    body: str
    sample_data: dict[str, str]
    synthetic: bool = True


def validate_template_content(
    title: str, body: str, allowed_placeholders: set[str]
) -> None:
    for field, value in (("title_template", title), ("body_template", body)):
        if ACTIVE_HTML.search(value):
            raise ApiError(
                422,
                "template_active_content",
                "HTML e conteúdo ativo não são permitidos",
                {"field": field},
            )
        if UNSAFE_URI.search(value):
            raise ApiError(
                422,
                "template_unsafe_url",
                "A URL informada utiliza um esquema inseguro",
                {"field": field},
            )
        if SECRET_MATERIAL.search(value):
            raise ApiError(
                422,
                "template_secret_material",
                "O conteúdo aparenta conter credencial ou segredo",
                {"field": field},
            )
        if CONTROL_CHARACTERS.search(value):
            raise ApiError(
                422,
                "template_control_characters",
                "Caracteres de controle não são permitidos",
                {"field": field},
            )
        try:
            parsed = list(Formatter().parse(value))
        except ValueError as exc:
            raise ApiError(
                422,
                "template_invalid_placeholder",
                "A sintaxe dos placeholders é inválida",
                {"field": field},
            ) from exc
        for _, placeholder, format_spec, conversion in parsed:
            if placeholder is None:
                continue
            if (
                placeholder not in allowed_placeholders
                or format_spec
                or conversion
                or "." in placeholder
                or "[" in placeholder
                or "]" in placeholder
            ):
                raise ApiError(
                    422,
                    "template_placeholder_not_allowed",
                    "O template utiliza um placeholder não permitido",
                    {"field": field, "placeholder": placeholder},
                )


def render_synthetic(template: str, placeholders: list[str]) -> str:
    values = {key: SYNTHETIC_VALUES[key] for key in placeholders}
    return template.format_map(values)


class NotificationTemplateRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _select() -> str:
        return """
            SELECT r.*,
                   p.allowed_placeholders,
                   CASE
                     WHEN r.published_at IS NULL THEN 'draft'
                     WHEN active.id IS NOT NULL THEN 'active'
                     ELSE 'inactive'
                   END AS state,
                   latest.deactivated_by_user_id,
                   latest.deactivated_reason,
                   latest.deactivated_at
            FROM synergia.notification_template_revisions r
            JOIN synergia.notification_event_policies p
              ON p.notification_type = r.notification_type
            LEFT JOIN synergia.notification_template_activations active
              ON active.revision_id = r.id AND active.deactivated_at IS NULL
            LEFT JOIN LATERAL (
              SELECT deactivated_by_user_id, deactivated_reason, deactivated_at
              FROM synergia.notification_template_activations history
              WHERE history.revision_id = r.id
              ORDER BY history.id DESC LIMIT 1
            ) latest ON true
        """

    def policies(self) -> list[dict]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT notification_type, required_permission, resource_type,
                          allowed_placeholders
                   FROM synergia.notification_event_policies
                   ORDER BY notification_type"""
            )
            return cursor.fetchall()

    def list(
        self,
        *,
        notification_type: str | None,
        channel: TemplateChannel | None,
        locale: TemplateLocale | None,
        state: TemplateState | None,
        sort: Literal["newest", "oldest"],
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        filters: list[str] = []
        parameters: list[object] = []
        for expression, value in (
            ("r.notification_type = %s", notification_type),
            ("r.channel = %s", channel),
            ("r.locale = %s", locale),
        ):
            if value is not None:
                filters.append(expression)
                parameters.append(value)
        if state == "draft":
            filters.append("r.published_at IS NULL")
        elif state == "active":
            filters.append("active.id IS NOT NULL")
        elif state == "inactive":
            filters.append("r.published_at IS NOT NULL AND active.id IS NULL")
        where = " WHERE " + " AND ".join(filters) if filters else ""
        direction = "DESC" if sort == "newest" else "ASC"
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) AS total FROM (" + self._select() + where + ") templates",
                parameters,
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                self._select()
                + where
                + f" ORDER BY r.created_at {direction}, r.id {direction} LIMIT %s OFFSET %s",
                [*parameters, page_size, (page - 1) * page_size],
            )
            return cursor.fetchall(), total

    def get(self, revision_id: UUID, *, lock: bool = False, cursor=None) -> dict | None:
        suffix = " FOR UPDATE OF r" if lock else ""
        if cursor is not None:
            cursor.execute(self._select() + " WHERE r.id = %s" + suffix, (revision_id,))
            return cursor.fetchone()
        with self._connect() as connection, connection.cursor() as own_cursor:
            own_cursor.execute(self._select() + " WHERE r.id = %s", (revision_id,))
            return own_cursor.fetchone()

    @staticmethod
    def _event(cursor, revision_id: UUID, event_type: str, actor: ActorContext, reason: str, payload: dict) -> None:
        cursor.execute(
            """INSERT INTO synergia.notification_template_events (
                 revision_id, event_type, actor_user_id, actor_session_id,
                 correlation_id, reason, payload
               ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                revision_id,
                event_type,
                actor.user_id,
                actor.session_id,
                actor.correlation_id,
                reason,
                Jsonb(payload),
            ),
        )

    @staticmethod
    def _policy(cursor, notification_type: str, *, lock: bool = False) -> dict:
        cursor.execute(
            """SELECT * FROM synergia.notification_event_policies
               WHERE notification_type = %s"""
            + (" FOR UPDATE" if lock else ""),
            (notification_type,),
        )
        policy = cursor.fetchone()
        if policy is None:
            raise ApiError(422, "notification_type_unknown", "Tipo de evento desconhecido")
        return policy

    def create(self, payload: DraftCreate, actor: ActorContext) -> dict:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                policy = self._policy(cursor, payload.notification_type, lock=True)
                validate_template_content(
                    payload.title_template,
                    payload.body_template,
                    set(policy["allowed_placeholders"]),
                )
                # Version labels are unique across locales in a channel. The
                # initial bilingual v1 remains a paired translation, while a
                # later independently edited locale cannot be mistaken for a
                # translation of another revision with the same label.
                lock_key = f"{payload.notification_type}:{payload.channel}"
                cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
                cursor.execute(
                    """SELECT COALESCE(max(version_number), 0) + 1 AS next_version
                       FROM synergia.notification_template_revisions
                       WHERE notification_type = %s AND channel = %s""",
                    (payload.notification_type, payload.channel),
                )
                version_number = cursor.fetchone()["next_version"]
                version_label = f"{version_number}.0.0"
                cursor.execute(
                    """INSERT INTO synergia.notification_template_versions (
                         notification_type, template_version,
                         required_permission, resource_type
                       ) VALUES (%s, %s, %s, %s)
                       ON CONFLICT (notification_type, template_version) DO NOTHING""",
                    (
                        payload.notification_type,
                        version_label,
                        policy["required_permission"],
                        policy["resource_type"],
                    ),
                )
                cursor.execute(
                    """INSERT INTO synergia.notification_template_revisions (
                         notification_type, channel, locale, version_number,
                         version_label, title_template, body_template,
                         created_by_user_id, created_reason
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (
                        payload.notification_type,
                        payload.channel,
                        payload.locale,
                        version_number,
                        version_label,
                        payload.title_template,
                        payload.body_template,
                        actor.user_id,
                        payload.reason,
                    ),
                )
                revision_id = cursor.fetchone()["id"]
                self._event(
                    cursor,
                    revision_id,
                    "template.draft_created",
                    actor,
                    payload.reason,
                    {"version": version_number, "channel": payload.channel, "locale": payload.locale},
                )
                result = self.get(revision_id, cursor=cursor)
                connection.commit()
                assert result is not None
                return result
        except errors.UniqueViolation as exc:
            raise ApiError(409, "template_version_conflict", "A versão já existe") from exc

    def update(self, revision_id: UUID, payload: DraftUpdate, actor: ActorContext) -> dict:
        with self._connect() as connection, connection.cursor() as cursor:
            current = self.get(revision_id, lock=True, cursor=cursor)
            if current is None:
                raise ApiError(404, "template_not_found", "Template não encontrado")
            if current["published_at"] is not None:
                raise ApiError(409, "published_template_immutable", "Versão publicada é imutável")
            if current["row_version"] != payload.row_version:
                raise ApiError(409, "template_version_conflict", "O rascunho foi atualizado")
            validate_template_content(
                payload.title_template,
                payload.body_template,
                set(current["allowed_placeholders"]),
            )
            cursor.execute(
                """UPDATE synergia.notification_template_revisions
                   SET title_template = %s, body_template = %s,
                       updated_by_user_id = %s, updated_reason = %s,
                       updated_at = now(), row_version = row_version + 1
                   WHERE id = %s""",
                (
                    payload.title_template,
                    payload.body_template,
                    actor.user_id,
                    payload.reason,
                    revision_id,
                ),
            )
            self._event(
                cursor,
                revision_id,
                "template.draft_updated",
                actor,
                payload.reason,
                {"version": current["version_number"]},
            )
            result = self.get(revision_id, cursor=cursor)
            connection.commit()
            assert result is not None
            return result

    def publish(self, revision_id: UUID, payload: TransitionRequest, actor: ActorContext) -> dict:
        with self._connect() as connection, connection.cursor() as cursor:
            current = self.get(revision_id, lock=True, cursor=cursor)
            if current is None:
                raise ApiError(404, "template_not_found", "Template não encontrado")
            if current["published_at"] is not None:
                raise ApiError(409, "template_already_published", "A versão já foi publicada")
            if current["row_version"] != payload.row_version:
                raise ApiError(409, "template_version_conflict", "O rascunho foi atualizado")
            validate_template_content(
                current["title_template"],
                current["body_template"],
                set(current["allowed_placeholders"]),
            )
            lock_key = f"{current['notification_type']}:{current['channel']}:{current['locale']}"
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
            cursor.execute(
                """UPDATE synergia.notification_template_activations
                   SET deactivated_by_user_id = %s,
                       deactivated_reason = %s, deactivated_at = now()
                   WHERE notification_type = %s AND channel = %s AND locale = %s
                     AND deactivated_at IS NULL
                   RETURNING revision_id""",
                (
                    actor.user_id,
                    f"Substituída: {payload.reason}",
                    current["notification_type"],
                    current["channel"],
                    current["locale"],
                ),
            )
            for replaced in cursor.fetchall():
                self._event(
                    cursor,
                    replaced["revision_id"],
                    "template.deactivated",
                    actor,
                    f"Substituída: {payload.reason}",
                    {"replacement_revision_id": str(revision_id)},
                )
            cursor.execute(
                """UPDATE synergia.notification_template_revisions
                   SET published_by_user_id = %s, published_reason = %s,
                       published_at = now(), row_version = row_version + 1,
                       updated_at = now()
                   WHERE id = %s""",
                (actor.user_id, payload.reason, revision_id),
            )
            cursor.execute(
                """INSERT INTO synergia.notification_template_activations (
                     revision_id, notification_type, channel, locale,
                     activated_by_user_id, activated_reason
                   ) VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    revision_id,
                    current["notification_type"],
                    current["channel"],
                    current["locale"],
                    actor.user_id,
                    payload.reason,
                ),
            )
            self._event(
                cursor,
                revision_id,
                "template.published",
                actor,
                payload.reason,
                {"version": current["version_number"]},
            )
            result = self.get(revision_id, cursor=cursor)
            connection.commit()
            assert result is not None
            return result

    def deactivate(self, revision_id: UUID, payload: TransitionRequest, actor: ActorContext) -> dict:
        with self._connect() as connection, connection.cursor() as cursor:
            current = self.get(revision_id, lock=True, cursor=cursor)
            if current is None:
                raise ApiError(404, "template_not_found", "Template não encontrado")
            if current["row_version"] != payload.row_version:
                raise ApiError(409, "template_version_conflict", "A versão foi atualizada")
            if current["state"] != "active":
                raise ApiError(409, "template_not_active", "A versão não está ativa")
            cursor.execute(
                """UPDATE synergia.notification_template_activations
                   SET deactivated_by_user_id = %s,
                       deactivated_reason = %s, deactivated_at = now()
                   WHERE revision_id = %s AND deactivated_at IS NULL""",
                (actor.user_id, payload.reason, revision_id),
            )
            self._event(
                cursor,
                revision_id,
                "template.deactivated",
                actor,
                payload.reason,
                {"version": current["version_number"]},
            )
            result = self.get(revision_id, cursor=cursor)
            connection.commit()
            assert result is not None
            return result


def get_notification_template_repository() -> Generator[NotificationTemplateRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ApiError(503, "database_not_configured", "Templates indisponíveis")
    yield NotificationTemplateRepository(database_url)


TemplateRepo = Annotated[
    NotificationTemplateRepository, Depends(get_notification_template_repository)
]
AdminActor = Annotated[
    ActorContext, Depends(require_global_permission("access.admin"))
]


def _external_delivery() -> Literal["disabled", "local_capture", "unavailable"]:
    try:
        config = EmailConfig.from_env()
    except (ValueError, OSError):
        return "unavailable"
    if not config.enabled:
        return "disabled"
    return "local_capture"


@router.get("/policy", response_model=TemplatePolicyResponse, responses=ERROR_RESPONSES)
def template_policy(repository: TemplateRepo) -> TemplatePolicyResponse:
    return TemplatePolicyResponse(
        events=repository.policies(),
        channels=["in_app", "email"],
        locales=["pt-BR", "en-US"],
        external_delivery=_external_delivery(),
    )


@router.get("", response_model=TemplatePage, responses=ERROR_RESPONSES)
def list_templates(
    repository: TemplateRepo,
    notification_type: str | None = None,
    channel: TemplateChannel | None = None,
    locale: TemplateLocale | None = None,
    state: TemplateState | None = None,
    sort: Literal["newest", "oldest"] = "newest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> TemplatePage:
    items, total = repository.list(
        notification_type=notification_type,
        channel=channel,
        locale=locale,
        state=state,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return TemplatePage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=math.ceil(total / page_size) if total else 0,
        sort=sort,
    )


@router.post("/drafts", response_model=TemplateRevisionResponse, status_code=201, responses=ERROR_RESPONSES)
def create_draft(payload: DraftCreate, actor: AdminActor, repository: TemplateRepo) -> TemplateRevisionResponse:
    return TemplateRevisionResponse.model_validate(repository.create(payload, actor))


@router.get("/{revision_id}", response_model=TemplateRevisionResponse, responses=ERROR_RESPONSES)
def get_template(revision_id: UUID, repository: TemplateRepo) -> TemplateRevisionResponse:
    result = repository.get(revision_id)
    if result is None:
        raise ApiError(404, "template_not_found", "Template não encontrado")
    return TemplateRevisionResponse.model_validate(result)


@router.patch("/{revision_id}", response_model=TemplateRevisionResponse, responses=ERROR_RESPONSES)
def update_draft(revision_id: UUID, payload: DraftUpdate, actor: AdminActor, repository: TemplateRepo) -> TemplateRevisionResponse:
    return TemplateRevisionResponse.model_validate(repository.update(revision_id, payload, actor))


@router.post("/{revision_id}/preview", response_model=PreviewResponse, responses=ERROR_RESPONSES)
def preview_template(revision_id: UUID, repository: TemplateRepo) -> PreviewResponse:
    result = repository.get(revision_id)
    if result is None:
        raise ApiError(404, "template_not_found", "Template não encontrado")
    placeholders = list(result["allowed_placeholders"])
    validate_template_content(
        result["title_template"], result["body_template"], set(placeholders)
    )
    return PreviewResponse(
        title=render_synthetic(result["title_template"], placeholders),
        body=render_synthetic(result["body_template"], placeholders),
        sample_data={key: SYNTHETIC_VALUES[key] for key in placeholders},
    )


@router.post("/{revision_id}/publish", response_model=TemplateRevisionResponse, responses=ERROR_RESPONSES)
def publish_template(revision_id: UUID, payload: TransitionRequest, actor: AdminActor, repository: TemplateRepo) -> TemplateRevisionResponse:
    return TemplateRevisionResponse.model_validate(repository.publish(revision_id, payload, actor))


@router.post("/{revision_id}/deactivate", response_model=TemplateRevisionResponse, responses=ERROR_RESPONSES)
def deactivate_template(revision_id: UUID, payload: TransitionRequest, actor: AdminActor, repository: TemplateRepo) -> TemplateRevisionResponse:
    return TemplateRevisionResponse.model_validate(repository.deactivate(revision_id, payload, actor))
