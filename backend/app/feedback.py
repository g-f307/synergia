from __future__ import annotations

import json
import math
import os
import unicodedata
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.authorization import ActorContext, CurrentActor, require_permission
from app.errors import ApiError, ErrorResponse

FeedbackState = Literal["received", "under_review", "planned", "resolved", "discarded"]
FeedbackKind = Literal["bug", "suggestion"]
TRANSITIONS = {
    "received": ("under_review", "discarded"),
    "under_review": ("planned", "resolved", "discarded"),
    "planned": ("under_review", "resolved", "discarded"),
    "resolved": (),
    "discarded": (),
}
SOURCE_CATALOG = json.loads(
    (Path(__file__).parent / "model/feedback_sources.json").read_text(encoding="utf-8")
)["sources"]
router = APIRouter(prefix="/feedback", tags=["feedback"])
ERRORS = {
    code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 429, 503)
}


def normalize_text(value, limit: int, *, multiline: bool = True) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Texto fora dos limites permitidos")
    text = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    if any(
        unicodedata.category(character) in {"Cc", "Cf"}
        and character not in {"\n", "\t"}
        for character in text
    ):
        raise ValueError("Texto contem caracteres de controle")
    return text.strip() if multiline else " ".join(text.split())


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: FeedbackKind
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=4000)
    expected_result: str | None = Field(default=None, max_length=2000)
    observed_result: str | None = Field(default=None, max_length=2000)
    source_id: str = Field(min_length=1, max_length=100)

    @field_validator("title", mode="before")
    @classmethod
    def title_text(cls, value):
        return normalize_text(value, 160, multiline=False)

    @field_validator("description", mode="before")
    @classmethod
    def description_text(cls, value):
        return normalize_text(value, 4000)

    @field_validator("expected_result", "observed_result", mode="before")
    @classmethod
    def optional_text(cls, value):
        return normalize_text(value, 2000) or None

    @model_validator(mode="after")
    def bug_fields(self):
        if self.kind == "suggestion" and (self.expected_result or self.observed_result):
            raise ValueError(
                "Resultados esperado e observado se aplicam somente a bugs"
            )
        return self


class FeedbackTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, strict=True)
    state: FeedbackState
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("reason", mode="before")
    @classmethod
    def reason_text(cls, value):
        return normalize_text(value, 2000) or None

    @model_validator(mode="after")
    def terminal_reason(self):
        if self.state in {"resolved", "discarded"} and len(self.reason or "") < 5:
            raise ValueError("Informe justificativa de pelo menos 5 caracteres")
        return self


class FeedbackQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: str | None = Field(default=None, pattern=r"^FB-[A-Fa-f0-9]{32}$")
    kind: FeedbackKind | None = None
    state: FeedbackState | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=20, ge=1, le=100)
    sort: Literal["oldest", "newest"] = "newest"

    @field_validator("created_from", "created_to")
    @classmethod
    def utc_period(cls, value):
        if value is not None:
            if value.utcoffset() is None:
                raise ValueError("Informe o fuso horario")
            return value.astimezone(UTC)
        return value

    @model_validator(mode="after")
    def bounded_period(self):
        if self.created_from and self.created_to:
            period = self.created_to - self.created_from
            if period <= timedelta(0) or period > timedelta(days=366):
                raise ValueError("Periodo deve ser positivo e de ate 366 dias")
        return self


class FeedbackEvent(BaseModel):
    id: int
    actor_user_id: UUID
    from_state: FeedbackState | None
    to_state: FeedbackState
    version: int
    reason: str | None
    occurred_at: datetime


class FeedbackItem(BaseModel):
    id: UUID
    protocol: str
    organization_id: UUID
    author_user_id: UUID
    kind: FeedbackKind
    title: str
    description: str
    expected_result: str | None
    observed_result: str | None
    source_route: str
    state: FeedbackState
    version: int
    created_at: datetime
    updated_at: datetime
    history: list[FeedbackEvent] = Field(default_factory=list)
    allowed_transitions: list[FeedbackState] = Field(default_factory=list)


class FeedbackPage(BaseModel):
    items: list[FeedbackItem]
    pagination: dict[str, int]
    sort: str
    generated_at: datetime


class FeedbackPolicy(BaseModel):
    can_create: bool
    organization: dict | None
    organization_issue: Literal["missing", "ambiguous"] | None
    sources: list[dict[str, str]]
    limits: dict[str, int] = {"title": 160, "description": 4000, "result": 2000}


def allowed_source(actor: ActorContext, source: dict) -> bool:
    permission = source["permission"]
    return not permission or (
        actor.allows(permission)
        if source["global"]
        else bool(actor.scopes_for(permission))
    )


def require_organization(organizations: list[dict]) -> dict:
    if len(organizations) != 1:
        code = (
            "feedback_organization_missing"
            if not organizations
            else "feedback_organization_ambiguous"
        )
        raise ApiError(409, code, "O feedback exige um vinculo organizacional unico")
    return organizations[0]


def public_item(row: dict, *, triage: bool = False) -> FeedbackItem:
    item = FeedbackItem.model_validate(row)
    item.allowed_transitions = list(TRANSITIONS[item.state]) if triage else []
    return item


class FeedbackRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def organizations(self, actor: ActorContext) -> list[dict]:
        # Global grants never manufacture organizational membership.
        with self._connect() as connection:
            return list(
                connection.execute(
                    """WITH memberships AS (
                    SELECT a.organization_id FROM synergia.user_role_assignments a
                    JOIN synergia.roles r ON r.id = a.role_id AND r.is_active
                    WHERE a.user_id = %s AND a.revoked_at IS NULL
                      AND (a.expires_at IS NULL OR a.expires_at > now())
                    UNION
                    SELECT a.organization_id FROM synergia.user_group_memberships m
                    JOIN synergia.identity_groups g ON g.id = m.group_id AND g.is_active
                    JOIN synergia.group_role_assignments a
                      ON a.group_id = g.id AND a.revoked_at IS NULL
                    JOIN synergia.roles r ON r.id = a.role_id AND r.is_active
                    WHERE m.user_id = %s AND m.revoked_at IS NULL
                    UNION
                    SELECT a.organization_id FROM synergia.user_permission_assignments a
                    JOIN synergia.permissions p
                      ON p.id = a.permission_id AND p.is_active
                    WHERE a.user_id = %s AND a.revoked_at IS NULL
                )
                SELECT o.id, o.organization_code, o.display_name
                FROM synergia.iam_organizations o
                JOIN memberships m ON m.organization_id = o.id
                WHERE o.is_active ORDER BY o.id""",
                    (actor.user_id, actor.user_id, actor.user_id),
                ).fetchall()
            )

    def create(
        self,
        actor: ActorContext,
        organization_id: UUID,
        payload: FeedbackCreate,
        source: dict,
    ) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """INSERT INTO synergia.feedback (
                    organization_id, author_user_id, author_session_id,
                    kind, title, description, expected_result, observed_result,
                    source_id, source_route, last_actor_user_id,
                    last_actor_session_id, correlation_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *""",
                (
                    organization_id,
                    actor.user_id,
                    actor.session_id,
                    payload.kind,
                    payload.title,
                    payload.description,
                    payload.expected_result,
                    payload.observed_result,
                    payload.source_id,
                    source["route"],
                    actor.user_id,
                    actor.session_id,
                    actor.correlation_id,
                ),
            ).fetchone()
            return self._detail(connection, row)

    @staticmethod
    def _detail(connection, row: dict) -> dict:
        history = connection.execute(
            """SELECT id, actor_user_id, from_state, to_state, version,
                      reason, occurred_at
            FROM synergia.feedback_events WHERE feedback_id = %s
            ORDER BY version, id""",
            (row["id"],),
        ).fetchall()
        return {**row, "history": history}

    def get(
        self, identifier: UUID, organization_id: UUID, author_id: UUID | None
    ) -> dict:
        scope = "AND author_user_id = %s" if author_id else ""
        values = [identifier, organization_id] + ([author_id] if author_id else [])
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM synergia.feedback WHERE id = %s "
                f"AND organization_id = %s {scope}",
                values,
            ).fetchone()
            if row is None:
                raise ApiError(404, "feedback_not_found", "Registro nao encontrado")
            return self._detail(connection, row)

    def list(
        self, organization_id: UUID, author_id: UUID | None, query: FeedbackQuery
    ) -> tuple[list[dict], int]:
        clauses, values = ["organization_id = %s"], [organization_id]
        if author_id:
            clauses.append("author_user_id = %s")
            values.append(author_id)
        for name in ("protocol", "kind", "state"):
            if (value := getattr(query, name)) is not None:
                clauses.append(f"{name} = %s")
                values.append(value.upper() if name == "protocol" else value)
        for name, comparator in (("created_from", ">="), ("created_to", "<")):
            if (value := getattr(query, name)) is not None:
                clauses.append(f"created_at {comparator} %s")
                values.append(value)
        where = " AND ".join(clauses)
        direction = "ASC" if query.sort == "oldest" else "DESC"
        with self._connect() as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            connection.execute("SET LOCAL statement_timeout = '5s'")
            total = connection.execute(
                f"SELECT count(*) AS total FROM synergia.feedback WHERE {where}",
                values,
            ).fetchone()["total"]
            rows = connection.execute(
                f"SELECT * FROM synergia.feedback WHERE {where} "
                f"ORDER BY created_at {direction}, id {direction} LIMIT %s OFFSET %s",
                [*values, query.page_size, (query.page - 1) * query.page_size],
            ).fetchall()
            return list(rows), total

    def transition(
        self,
        identifier: UUID,
        organization_id: UUID,
        actor: ActorContext,
        payload: FeedbackTransition,
    ) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM synergia.feedback
                WHERE id = %s AND organization_id = %s FOR UPDATE""",
                (identifier, organization_id),
            ).fetchone()
            if row is None:
                raise ApiError(404, "feedback_not_found", "Registro nao encontrado")
            if row["version"] != payload.version:
                raise ApiError(
                    409, "feedback_conflict", "Recarregue o registro atualizado"
                )
            if payload.state not in TRANSITIONS[row["state"]]:
                raise ApiError(
                    409, "feedback_transition_invalid", "Transicao nao permitida"
                )
            updated = connection.execute(
                """UPDATE synergia.feedback SET state = %s, version = version + 1,
                    change_reason = %s, last_actor_user_id = %s,
                    last_actor_session_id = %s, correlation_id = %s
                WHERE id = %s RETURNING *""",
                (
                    payload.state,
                    payload.reason,
                    actor.user_id,
                    actor.session_id,
                    actor.correlation_id,
                    identifier,
                ),
            ).fetchone()
            return self._detail(connection, updated)


def get_feedback_repository() -> Generator[FeedbackRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ApiError(503, "database_not_configured", "Feedback indisponivel")
    try:
        yield FeedbackRepository(database_url)
    except psycopg.OperationalError as exc:
        raise ApiError(503, "feedback_unavailable", "Feedback indisponivel") from exc


Repository = Annotated[FeedbackRepository, Depends(get_feedback_repository)]
Triager = Annotated[ActorContext, Depends(require_permission("feedback.triage"))]


def triage_organization(actor: ActorContext, repository: FeedbackRepository) -> UUID:
    organization = require_organization(repository.organizations(actor))["id"]
    if not actor.allows("feedback.triage", organization):
        raise ApiError(403, "access_denied", "Acao nao autorizada")
    return organization


@router.get("/policy", response_model=FeedbackPolicy, responses=ERRORS)
def feedback_policy(actor: CurrentActor, repository: Repository):
    organizations = repository.organizations(actor)
    return FeedbackPolicy(
        can_create=len(organizations) == 1,
        organization=organizations[0] if len(organizations) == 1 else None,
        organization_issue=(
            None
            if len(organizations) == 1
            else "missing"
            if not organizations
            else "ambiguous"
        ),
        sources=[
            {"id": key, "route": source["route"]}
            for key, source in SOURCE_CATALOG.items()
            if allowed_source(actor, source)
        ],
    )


@router.post("", status_code=201, response_model=FeedbackItem, responses=ERRORS)
def create_feedback(
    actor: CurrentActor, payload: FeedbackCreate, repository: Repository
):
    organization = require_organization(repository.organizations(actor))["id"]
    source = SOURCE_CATALOG.get(payload.source_id)
    if source is None or not allowed_source(actor, source):
        raise ApiError(422, "feedback_source_invalid", "Origem funcional nao permitida")
    return public_item(repository.create(actor, organization, payload, source))


def feedback_page(actor, repository, query, triage):
    organization = (
        triage_organization(actor, repository)
        if triage
        else require_organization(repository.organizations(actor))["id"]
    )
    rows, total = repository.list(
        organization, None if triage else actor.user_id, query
    )
    return FeedbackPage(
        items=[public_item(row, triage=triage) for row in rows],
        pagination={
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "pages": math.ceil(total / query.page_size),
        },
        sort=query.sort,
        generated_at=datetime.now(UTC),
    )


@router.get("/triage", response_model=FeedbackPage, responses=ERRORS)
def triage_list(
    actor: Triager, repository: Repository, query: Annotated[FeedbackQuery, Query()]
):
    return feedback_page(actor, repository, query, True)


@router.get("/triage/{feedback_id}", response_model=FeedbackItem, responses=ERRORS)
def triage_detail(feedback_id: UUID, actor: Triager, repository: Repository):
    organization = triage_organization(actor, repository)
    return public_item(repository.get(feedback_id, organization, None), triage=True)


@router.patch("/triage/{feedback_id}", response_model=FeedbackItem, responses=ERRORS)
def triage_transition(
    feedback_id: UUID,
    actor: Triager,
    payload: FeedbackTransition,
    repository: Repository,
):
    organization = triage_organization(actor, repository)
    return public_item(
        repository.transition(feedback_id, organization, actor, payload), triage=True
    )


@router.get("", response_model=FeedbackPage, responses=ERRORS)
def own_list(
    actor: CurrentActor,
    repository: Repository,
    query: Annotated[FeedbackQuery, Query()],
):
    return feedback_page(actor, repository, query, False)


@router.get("/{feedback_id}", response_model=FeedbackItem, responses=ERRORS)
def own_detail(feedback_id: UUID, actor: CurrentActor, repository: Repository):
    organization = require_organization(repository.organizations(actor))["id"]
    return public_item(repository.get(feedback_id, organization, actor.user_id))
