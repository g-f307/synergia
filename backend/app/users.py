from __future__ import annotations

import math
import os
import re
from collections.abc import Generator
from datetime import datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Header, Query, status
from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator, model_validator

from app.errors import ApiError, ErrorResponse

router = APIRouter(prefix="/admin/users", tags=["user administration"])

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Operacao inconsistente"},
    403: {"model": ErrorResponse, "description": "Acao nao autorizada"},
    404: {"model": ErrorResponse, "description": "Recurso nao encontrado"},
    409: {"model": ErrorResponse, "description": "Conflito de estado ou versao"},
    422: {"model": ErrorResponse, "description": "Parametros invalidos"},
    503: {
        "model": ErrorResponse,
        "description": "Adaptador de identidade indisponivel",
    },
}

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
UserStatus = Literal["pending", "active", "blocked", "inactive"]
UserCreateStatus = Literal["pending", "active"]
UserStateAction = Literal["deactivate", "reactivate", "block", "unblock"]
TRUSTED_HEADER_ENVIRONMENTS = frozenset({"development", "test", "homologation"})
LAST_ACTIVE_ADMIN_LOCK_ID = 7_421_903_901


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) > 320 or not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("e-mail invalido")
    return normalized


class UserEmailInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    is_primary: bool = False
    is_verified: bool = False

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class UserCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    status: UserCreateStatus = "pending"
    emails: list[UserEmailInput] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("o campo deve conter texto")
        return normalized

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("o motivo deve possuir ao menos tres caracteres")
        return normalized

    @model_validator(mode="after")
    def validate_emails(self) -> UserCreate:
        normalized = [item.email for item in self.emails]
        if len(normalized) != len(set(normalized)):
            raise ValueError("e-mails duplicados na requisicao")
        if sum(item.is_primary for item in self.emails) > 1:
            raise ValueError("somente um e-mail pode ser principal")
        return self


class UserUpdate(BaseModel):
    version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    emails: list[UserEmailInput] | None = Field(
        default=None, min_length=1, max_length=20
    )
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("o campo deve conter texto")
        return normalized

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("o motivo deve possuir ao menos tres caracteres")
        return normalized

    @model_validator(mode="after")
    def validate_change(self) -> UserUpdate:
        if self.display_name is None and self.emails is None:
            raise ValueError("informe ao menos um campo para atualizar")
        if self.emails is not None:
            normalized = [item.email for item in self.emails]
            if len(normalized) != len(set(normalized)):
                raise ValueError("e-mails duplicados na requisicao")
            if sum(item.is_primary for item in self.emails) > 1:
                raise ValueError("somente um e-mail pode ser principal")
        return self


class UserStateChange(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("o motivo deve possuir ao menos tres caracteres")
        return normalized


class UserEmailResponse(BaseModel):
    email: str
    is_primary: bool
    is_verified: bool


class UserResponse(BaseModel):
    id: UUID
    status: UserStatus
    display_name: str
    emails: list[UserEmailResponse]
    version: int
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None = None
    last_login_at: datetime | None = None


class UserPage(BaseModel):
    items: list[UserResponse]
    page: int
    page_size: int
    total: int
    pages: int
    sort: Literal["created_at,id"] = "created_at,id"


class Actor(BaseModel):
    user_id: UUID


def get_actor(
    x_actor_id: Annotated[str | None, Header(alias="X-Actor-Id")] = None,
) -> Actor:
    environment = os.getenv("SYNERGIA_ENV", "").strip().lower()
    header_enabled = os.getenv(
        "SYNERGIA_TRUSTED_ACTOR_HEADER_ENABLED", ""
    ).strip().lower() in {"1", "true", "yes"}
    if not header_enabled or environment not in TRUSTED_HEADER_ENVIRONMENTS:
        raise ApiError(
            503,
            "identity_adapter_unavailable",
            "Administracao de usuarios indisponivel sem adaptador de identidade",
        )
    if not x_actor_id:
        raise ApiError(403, "access_denied", "Acao administrativa nao autorizada")
    try:
        return Actor(user_id=UUID(x_actor_id))
    except ValueError as exc:
        raise ApiError(
            403, "access_denied", "Acao administrativa nao autorizada"
        ) from exc


class UserRepository(Protocol):
    def authorize(self, actor_id: UUID) -> None: ...

    def create(self, payload: UserCreate, actor_id: UUID) -> dict: ...

    def get(self, user_id: UUID) -> dict | None: ...

    def list(
        self,
        *,
        status_filter: UserStatus | None,
        group: str | None,
        role: str | None,
        organization: str | None,
        name: str | None,
        email: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]: ...

    def update(self, user_id: UUID, payload: UserUpdate, actor_id: UUID) -> dict: ...

    def change_status(
        self,
        user_id: UUID,
        target_status: UserStatus,
        action: UserStateAction,
        payload: UserStateChange,
        actor_id: UUID,
    ) -> dict: ...


class PostgresUserRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _public_user(cursor, user_id: UUID) -> dict | None:
        cursor.execute(
            """
            SELECT id, status, display_name, version, created_at, updated_at,
                   deactivated_at, last_login_at
            FROM synergia.identity_users
            WHERE id = %s
            """,
            (user_id,),
        )
        user = cursor.fetchone()
        if user is None:
            return None
        cursor.execute(
            """
            SELECT normalized_email AS email, is_primary, is_verified
            FROM synergia.user_emails
            WHERE user_id = %s AND disabled_at IS NULL
            ORDER BY is_primary DESC, normalized_email, id
            """,
            (user_id,),
        )
        user["emails"] = cursor.fetchall()
        return user

    def authorize(self, actor_id: UUID) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM synergia.identity_users u
                    JOIN synergia.user_role_assignments ura ON ura.user_id = u.id
                    JOIN synergia.roles r ON r.id = ura.role_id
                    LEFT JOIN synergia.role_permissions rp ON rp.role_id = r.id
                    LEFT JOIN synergia.permissions p ON p.id = rp.permission_id
                    WHERE u.id = %s AND u.status = 'active'
                      AND ura.revoked_at IS NULL
                      AND (ura.expires_at IS NULL OR ura.expires_at > now())
                      AND r.is_active
                      AND (r.normalized_key = 'admin'
                           OR (p.normalized_key = 'access.admin' AND p.is_active))
                ) AS authorized
                """,
                (actor_id,),
            )
            if not cursor.fetchone()["authorized"]:
                raise ApiError(
                    403, "access_denied", "Acao administrativa nao autorizada"
                )

    @staticmethod
    def _record_event(
        cursor,
        *,
        event_key: str,
        actor_id: UUID,
        subject_id: UUID,
        payload: dict,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO synergia.identity_access_events (
                event_key, actor_user_id, subject_user_id,
                entity_type, entity_id, payload
            ) VALUES (%s, %s, %s, 'identity_user', %s, %s)
            """,
            (event_key, actor_id, subject_id, str(subject_id), Jsonb(payload)),
        )

    @staticmethod
    def _raise_integrity_error(exc: errors.UniqueViolation) -> None:
        raise ApiError(
            409,
            "user_data_conflict",
            "Os dados informados conflitam com um usuario existente",
        ) from exc

    def create(self, payload: UserCreate, actor_id: UUID) -> dict:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO synergia.identity_users (status, display_name)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (payload.status, payload.display_name),
                )
                user_id = cursor.fetchone()["id"]
                for item in payload.emails:
                    cursor.execute(
                        """
                        INSERT INTO synergia.user_emails (
                            user_id, email, is_primary, is_verified, verified_at
                        ) VALUES (%s, %s, %s, %s,
                                  CASE WHEN %s THEN now() ELSE NULL END)
                        """,
                        (
                            user_id,
                            item.email,
                            item.is_primary,
                            item.is_verified,
                            item.is_verified,
                        ),
                    )
                self._record_event(
                    cursor,
                    event_key="user.admin_created",
                    actor_id=actor_id,
                    subject_id=user_id,
                    payload={
                        "reason": payload.reason,
                        "changed_fields": ["display_name", "status", "emails"],
                    },
                )
                result = self._public_user(cursor, user_id)
                connection.commit()
                assert result is not None
                return result
        except errors.UniqueViolation as exc:
            self._raise_integrity_error(exc)

    def get(self, user_id: UUID) -> dict | None:
        with self._connect() as connection, connection.cursor() as cursor:
            return self._public_user(cursor, user_id)

    def list(
        self,
        *,
        status_filter: UserStatus | None,
        group: str | None,
        role: str | None,
        organization: str | None,
        name: str | None,
        email: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        filters = ["TRUE"]
        parameters: list[object] = []
        if status_filter:
            filters.append("u.status = %s")
            parameters.append(status_filter)
        if name:
            filters.append("u.display_name ILIKE %s")
            parameters.append(f"%{name.strip()}%")
        if email:
            filters.append(
                "EXISTS (SELECT 1 FROM synergia.user_emails ue "
                "WHERE ue.user_id = u.id AND ue.disabled_at IS NULL "
                "AND ue.normalized_email = %s)"
            )
            parameters.append(normalize_email(email))
        if group:
            filters.append(
                "EXISTS (SELECT 1 FROM synergia.user_group_memberships ugm "
                "JOIN synergia.identity_groups g ON g.id = ugm.group_id "
                "WHERE ugm.user_id = u.id AND ugm.revoked_at IS NULL "
                "AND g.normalized_name = lower(btrim(%s)))"
            )
            parameters.append(group)
        if role or organization:
            role_filters = ["ura.user_id = u.id", "ura.revoked_at IS NULL"]
            if role:
                role_filters.append("r.normalized_key = lower(btrim(%s))")
                parameters.append(role)
            if organization:
                role_filters.append("o.organization_code = lower(btrim(%s))")
                parameters.append(organization)
            filters.append(
                "EXISTS (SELECT 1 FROM synergia.user_role_assignments ura "
                "JOIN synergia.roles r ON r.id = ura.role_id "
                "LEFT JOIN synergia.iam_organizations o "
                "ON o.id = ura.organization_id WHERE "
                + " AND ".join(role_filters)
                + ")"
            )
        where = " AND ".join(filters)
        with self._connect() as connection, connection.cursor() as cursor:
            count_sql = (
                f"SELECT count(*) AS total FROM synergia.identity_users u WHERE {where}"
            )
            cursor.execute(
                count_sql,
                parameters,
            )  # noqa: S608
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"SELECT u.id FROM synergia.identity_users u WHERE {where} "  # noqa: S608
                "ORDER BY u.created_at, u.id LIMIT %s OFFSET %s",
                [*parameters, page_size, (page - 1) * page_size],
            )
            items = [self._public_user(cursor, row["id"]) for row in cursor.fetchall()]
            return [item for item in items if item is not None], total

    def update(self, user_id: UUID, payload: UserUpdate, actor_id: UUID) -> dict:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT display_name FROM synergia.identity_users "
                    "WHERE id = %s FOR UPDATE",
                    (user_id,),
                )
                current = cursor.fetchone()
                if current is None:
                    return self._not_found()
                changed_fields: list[str] = []
                if (
                    payload.display_name is not None
                    and payload.display_name != current["display_name"]
                ):
                    cursor.execute(
                        """
                        UPDATE synergia.identity_users SET display_name = %s
                        WHERE id = %s AND version = %s
                        RETURNING version
                        """,
                        (payload.display_name, user_id, payload.version),
                    )
                    if cursor.fetchone() is None:
                        self._version_conflict()
                    changed_fields.append("display_name")
                else:
                    cursor.execute(
                        "SELECT version FROM synergia.identity_users WHERE id = %s",
                        (user_id,),
                    )
                    if cursor.fetchone()["version"] != payload.version:
                        self._version_conflict()
                if payload.emails is not None:
                    cursor.execute(
                        "SELECT id, normalized_email FROM synergia.user_emails "
                        "WHERE user_id = %s FOR UPDATE",
                        (user_id,),
                    )
                    existing = {
                        row["normalized_email"]: row["id"] for row in cursor.fetchall()
                    }
                    desired = {item.email for item in payload.emails}
                    cursor.execute(
                        """
                        UPDATE synergia.user_emails
                        SET disabled_at = CASE
                                WHEN normalized_email = ANY(%s) THEN NULL
                                ELSE COALESCE(disabled_at, now())
                            END,
                            is_primary = false
                        WHERE user_id = %s
                        """,
                        (list(desired), user_id),
                    )
                    for item in payload.emails:
                        if item.email in existing:
                            cursor.execute(
                                """
                                UPDATE synergia.user_emails
                                SET email = %s, is_primary = %s, is_verified = %s,
                                    verified_at = CASE
                                        WHEN %s THEN COALESCE(verified_at, now())
                                        ELSE NULL
                                    END,
                                    disabled_at = NULL
                                WHERE id = %s
                                """,
                                (
                                    item.email,
                                    item.is_primary,
                                    item.is_verified,
                                    item.is_verified,
                                    existing[item.email],
                                ),
                            )
                        else:
                            cursor.execute(
                                """
                                INSERT INTO synergia.user_emails (
                                    user_id, email, is_primary,
                                    is_verified, verified_at
                                ) VALUES (%s, %s, %s, %s,
                                          CASE WHEN %s THEN now() ELSE NULL END)
                                """,
                                (
                                    user_id,
                                    item.email,
                                    item.is_primary,
                                    item.is_verified,
                                    item.is_verified,
                                ),
                            )
                    if not changed_fields:
                        cursor.execute(
                            "UPDATE synergia.identity_users SET updated_at = now() "
                            "WHERE id = %s",
                            (user_id,),
                        )
                    changed_fields.append("emails")
                self._record_event(
                    cursor,
                    event_key="user.admin_updated",
                    actor_id=actor_id,
                    subject_id=user_id,
                    payload={
                        "reason": payload.reason,
                        "changed_fields": changed_fields,
                    },
                )
                result = self._public_user(cursor, user_id)
                connection.commit()
                assert result is not None
                return result
        except errors.UniqueViolation as exc:
            self._raise_integrity_error(exc)

    @staticmethod
    def _not_found():
        raise ApiError(404, "user_not_found", "Usuario nao encontrado")

    @staticmethod
    def _version_conflict():
        raise ApiError(
            409,
            "user_version_conflict",
            "O usuario foi alterado por outra operacao",
        )

    def change_status(
        self,
        user_id: UUID,
        target_status: UserStatus,
        action: UserStateAction,
        payload: UserStateChange,
        actor_id: UUID,
    ) -> dict:
        with self._connect() as connection, connection.cursor() as cursor:
            if target_status in {"inactive", "blocked"}:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    (LAST_ACTIVE_ADMIN_LOCK_ID,),
                )
            cursor.execute(
                "SELECT status, version FROM synergia.identity_users "
                "WHERE id = %s FOR UPDATE",
                (user_id,),
            )
            current = cursor.fetchone()
            if current is None:
                self._not_found()
            if current["version"] != payload.version:
                self._version_conflict()
            allowed_statuses = {
                "deactivate": {"pending", "active", "blocked"},
                "reactivate": {"inactive"},
                "block": {"pending", "active"},
                "unblock": {"blocked"},
            }
            if current["status"] not in allowed_statuses[action]:
                raise ApiError(
                    409,
                    "invalid_user_state_transition",
                    "A transicao solicitada nao e permitida para o estado atual",
                )
            if current["status"] == target_status:
                raise ApiError(
                    409, "user_state_unchanged", "Usuario ja esta no estado solicitado"
                )
            if target_status in {"inactive", "blocked"}:
                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM synergia.user_role_assignments ura
                        JOIN synergia.roles r ON r.id = ura.role_id
                        LEFT JOIN synergia.role_permissions rp
                          ON rp.role_id = r.id
                        LEFT JOIN synergia.permissions p
                          ON p.id = rp.permission_id
                        WHERE ura.user_id = %s AND ura.revoked_at IS NULL
                          AND (ura.expires_at IS NULL OR ura.expires_at > now())
                          AND r.is_active
                          AND (r.normalized_key = 'admin'
                               OR (p.normalized_key = 'access.admin'
                                   AND p.is_active))
                    ) AS is_admin
                    """,
                    (user_id,),
                )
                if cursor.fetchone()["is_admin"]:
                    cursor.execute(
                        """
                        SELECT count(DISTINCT u.id) AS total
                        FROM synergia.identity_users u
                        JOIN synergia.user_role_assignments ura ON ura.user_id = u.id
                        JOIN synergia.roles r ON r.id = ura.role_id
                        LEFT JOIN synergia.role_permissions rp
                          ON rp.role_id = r.id
                        LEFT JOIN synergia.permissions p
                          ON p.id = rp.permission_id
                        WHERE u.status = 'active' AND ura.revoked_at IS NULL
                          AND (ura.expires_at IS NULL OR ura.expires_at > now())
                          AND r.is_active
                          AND (r.normalized_key = 'admin'
                               OR (p.normalized_key = 'access.admin'
                                   AND p.is_active))
                        """
                    )
                    if cursor.fetchone()["total"] <= 1:
                        raise ApiError(
                            409,
                            "last_active_admin",
                            "O ultimo administrador ativo nao pode ser "
                            "desativado ou bloqueado",
                        )
            deactivated = target_status == "inactive"
            cursor.execute(
                """
                UPDATE synergia.identity_users
                SET status = %s,
                    deactivated_at = CASE WHEN %s THEN now() ELSE NULL END
                WHERE id = %s AND version = %s
                RETURNING version
                """,
                (target_status, deactivated, user_id, payload.version),
            )
            if cursor.fetchone() is None:
                self._version_conflict()
            self._record_event(
                cursor,
                event_key=f"user.admin_{action}",
                actor_id=actor_id,
                subject_id=user_id,
                payload={
                    "reason": payload.reason,
                    "previous_status": current["status"],
                    "new_status": target_status,
                    "changed_fields": ["status"],
                },
            )
            result = self._public_user(cursor, user_id)
            connection.commit()
            assert result is not None
            return result


def get_user_repository() -> Generator[UserRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ApiError(500, "database_not_configured", "Banco de dados indisponivel")
    yield PostgresUserRepository(database_url)


Repository = Annotated[UserRepository, Depends(get_user_repository)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


def _authorized(repository: UserRepository, actor: Actor) -> None:
    repository.authorize(actor.user_id)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def create_user(
    payload: UserCreate, repository: Repository, actor: CurrentActor
) -> dict:
    _authorized(repository, actor)
    return repository.create(payload, actor.user_id)


@router.get("", response_model=UserPage, responses=ERROR_RESPONSES)
def list_users(
    repository: Repository,
    actor: CurrentActor,
    status_filter: Annotated[UserStatus | None, Query(alias="status")] = None,
    group: str | None = None,
    role: str | None = None,
    organization: str | None = None,
    name: str | None = None,
    email: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> UserPage:
    _authorized(repository, actor)
    items, total = repository.list(
        status_filter=status_filter,
        group=group,
        role=role,
        organization=organization,
        name=name,
        email=email,
        page=page,
        page_size=page_size,
    )
    return UserPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/{user_id}", response_model=UserResponse, responses=ERROR_RESPONSES)
def get_user(user_id: UUID, repository: Repository, actor: CurrentActor) -> dict:
    _authorized(repository, actor)
    result = repository.get(user_id)
    if result is None:
        raise ApiError(404, "user_not_found", "Usuario nao encontrado")
    return result


@router.patch("/{user_id}", response_model=UserResponse, responses=ERROR_RESPONSES)
def update_user(
    user_id: UUID, payload: UserUpdate, repository: Repository, actor: CurrentActor
) -> dict:
    _authorized(repository, actor)
    return repository.update(user_id, payload, actor.user_id)


def _change_status(
    user_id: UUID,
    target: UserStatus,
    action: UserStateAction,
    payload: UserStateChange,
    repository: UserRepository,
    actor: Actor,
) -> dict:
    _authorized(repository, actor)
    return repository.change_status(user_id, target, action, payload, actor.user_id)


@router.post(
    "/{user_id}/deactivate", response_model=UserResponse, responses=ERROR_RESPONSES
)
def deactivate_user(
    user_id: UUID, payload: UserStateChange, repository: Repository, actor: CurrentActor
) -> dict:
    return _change_status(user_id, "inactive", "deactivate", payload, repository, actor)


@router.post(
    "/{user_id}/reactivate", response_model=UserResponse, responses=ERROR_RESPONSES
)
def reactivate_user(
    user_id: UUID, payload: UserStateChange, repository: Repository, actor: CurrentActor
) -> dict:
    return _change_status(user_id, "active", "reactivate", payload, repository, actor)


@router.post("/{user_id}/block", response_model=UserResponse, responses=ERROR_RESPONSES)
def block_user(
    user_id: UUID, payload: UserStateChange, repository: Repository, actor: CurrentActor
) -> dict:
    return _change_status(user_id, "blocked", "block", payload, repository, actor)


@router.post(
    "/{user_id}/unblock", response_model=UserResponse, responses=ERROR_RESPONSES
)
def unblock_user(
    user_id: UUID, payload: UserStateChange, repository: Repository, actor: CurrentActor
) -> dict:
    return _change_status(user_id, "active", "unblock", payload, repository, actor)


@router.delete(
    "/{user_id}", status_code=status.HTTP_409_CONFLICT, responses=ERROR_RESPONSES
)
def reject_physical_delete(
    user_id: UUID, repository: Repository, actor: CurrentActor
) -> None:
    _authorized(repository, actor)
    if repository.get(user_id) is None:
        raise ApiError(404, "user_not_found", "Usuario nao encontrado")
    raise ApiError(
        409,
        "physical_deletion_forbidden",
        "Usuarios devem ser desativados, nunca excluidos fisicamente",
    )
