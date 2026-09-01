from __future__ import annotations

# SQL contracts remain easier to audit as aligned, complete clauses.
# ruff: noqa: E501
import math
import os
from collections.abc import Generator
from datetime import datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query, status
from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator, model_validator

from app.authorization import ActorContext as Actor
from app.authorization import (
    CurrentActor,
    active_global_admin_count,
    is_global_admin,
    require_permission,
)
from app.errors import ApiError, ErrorResponse
from app.users import LAST_ACTIVE_ADMIN_LOCK_ID

router = APIRouter(
    prefix="/admin/access",
    tags=["access control"],
    dependencies=[Depends(require_permission("access.admin"))],
)

ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Acao nao autorizada"},
    404: {"model": ErrorResponse, "description": "Recurso nao encontrado"},
    409: {"model": ErrorResponse, "description": "Conflito de integridade"},
    422: {"model": ErrorResponse, "description": "Parametros invalidos"},
    503: {"model": ErrorResponse, "description": "Identidade indisponivel"},
}

AssociationKind = Literal[
    "user_group", "user_role", "role_permission", "group_role", "user_permission"
]


def _strip(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("o campo deve conter texto")
    return normalized


def _audit_snapshot(row: dict, *fields: str) -> dict:
    return {
        field: value.isoformat() if isinstance(value, datetime) else value
        for field in fields
        if (value := row.get(field)) is not None
    }


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    organization_id: UUID | None = None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = _strip(value)
        if len(normalized) < 3:
            raise ValueError("o motivo deve possuir ao menos tres caracteres")
        return normalized


class VersionedReason(ReasonRequest):
    version: int = Field(ge=1)


class GroupCreate(BaseModel):
    group_name: str = Field(min_length=1, max_length=160)
    external_reference: str | None = Field(default=None, max_length=240)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("group_name", "reason")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _strip(value)


class GroupUpdate(BaseModel):
    version: int = Field(ge=1)
    group_name: str | None = Field(default=None, min_length=1, max_length=160)
    external_reference: str | None = Field(default=None, max_length=240)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("group_name", "reason")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _strip(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> GroupUpdate:
        if self.group_name is None and self.external_reference is None:
            raise ValueError("informe ao menos um campo")
        return self


class RoleCreate(BaseModel):
    role_key: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("role_key", "reason")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _strip(value)


class RoleUpdate(BaseModel):
    version: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("description", "reason")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _strip(value)


class GroupResponse(BaseModel):
    id: UUID
    group_name: str
    external_reference: str | None = None
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None = None


class RoleResponse(BaseModel):
    id: UUID
    role_key: str
    description: str | None = None
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None = None


class PermissionResponse(BaseModel):
    id: UUID
    permission_key: str
    resource_type: str
    description: str | None = None
    catalog_version: str
    is_reserved: bool
    is_active: bool


class Page(BaseModel):
    items: list[dict]
    page: int
    page_size: int
    total: int
    pages: int
    sort: str


class EffectivePermission(BaseModel):
    permission_key: str
    resource_type: str
    source: Literal["direct", "role", "group"]
    source_id: UUID
    organization_id: UUID | None = None
    organization_code: str | None = None


class EffectivePermissionsResponse(BaseModel):
    user_id: UUID
    permissions: list[EffectivePermission]


class AssociationResponse(BaseModel):
    id: UUID | None
    idempotent: bool
    kind: AssociationKind


class AccessRepository(Protocol):
    def authorize(self, actor_id: UUID) -> None: ...

    def create_group(self, payload: GroupCreate, actor_id: UUID) -> dict: ...

    def get_group(self, group_id: UUID) -> dict | None: ...

    def list_groups(self, page: int, page_size: int) -> tuple[list[dict], int]: ...

    def update_group(
        self, group_id: UUID, payload: GroupUpdate, actor_id: UUID
    ) -> dict: ...

    def set_group_active(
        self, group_id: UUID, active: bool, payload: VersionedReason, actor_id: UUID
    ) -> dict: ...

    def create_role(self, payload: RoleCreate, actor_id: UUID) -> dict: ...

    def get_role(self, role_id: UUID) -> dict | None: ...

    def list_roles(self, page: int, page_size: int) -> tuple[list[dict], int]: ...

    def update_role(
        self, role_id: UUID, payload: RoleUpdate, actor_id: UUID
    ) -> dict: ...

    def set_role_active(
        self, role_id: UUID, active: bool, payload: VersionedReason, actor_id: UUID
    ) -> dict: ...

    def list_permissions(self, catalog_version: str | None) -> list[dict]: ...

    def grant(
        self,
        kind: AssociationKind,
        left_id: UUID,
        right_id: UUID,
        payload: ReasonRequest,
        actor_id: UUID,
    ) -> dict: ...

    def revoke(
        self,
        kind: AssociationKind,
        left_id: UUID,
        right_id: UUID,
        payload: ReasonRequest,
        actor_id: UUID,
    ) -> dict: ...

    def list_associations(
        self, kind: AssociationKind | None, page: int, page_size: int
    ) -> tuple[list[dict], int]: ...

    def effective_permissions(
        self, user_id: UUID, organization_id: UUID | None
    ) -> list[dict]: ...


class PostgresAccessRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def authorize(self, actor_id: UUID) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            if not is_global_admin(cursor, actor_id):
                raise ApiError(
                    403, "access_denied", "Acao administrativa nao autorizada"
                )

    @staticmethod
    def _event(
        cursor,
        event_key: str,
        actor_id: UUID,
        entity_type: str,
        entity_id: UUID,
        reason: str,
        subject_id: UUID | None = None,
        details: dict | None = None,
        organization_id: UUID | None = None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO synergia.identity_access_events (
                event_key, actor_user_id, subject_user_id,
                organization_id, entity_type, entity_id, payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event_key,
                actor_id,
                subject_id,
                organization_id,
                entity_type,
                str(entity_id),
                Jsonb({"reason": reason, **(details or {})}),
            ),
        )

    @staticmethod
    def _conflict(exc: Exception) -> None:
        raise ApiError(
            409,
            "access_data_conflict",
            "Os dados informados conflitam com o controle de acesso",
        ) from exc

    def create_group(self, payload: GroupCreate, actor_id: UUID) -> dict:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO synergia.identity_groups (
                        group_name, external_reference
                    ) VALUES (%s, %s) RETURNING *
                    """,
                    (payload.group_name, payload.external_reference),
                )
                result = cursor.fetchone()
                self._event(
                    cursor,
                    "access.group_created",
                    actor_id,
                    "identity_group",
                    result["id"],
                    payload.reason,
                )
                connection.commit()
                return result
        except errors.UniqueViolation as exc:
            self._conflict(exc)

    def get_group(self, group_id: UUID) -> dict | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM synergia.identity_groups WHERE id = %s", (group_id,)
            )
            return cursor.fetchone()

    def list_groups(self, page: int, page_size: int) -> tuple[list[dict], int]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS total FROM synergia.identity_groups")
            total = cursor.fetchone()["total"]
            cursor.execute(
                """
                SELECT * FROM synergia.identity_groups
                ORDER BY normalized_name, id LIMIT %s OFFSET %s
                """,
                (page_size, (page - 1) * page_size),
            )
            return cursor.fetchall(), total

    def update_group(
        self, group_id: UUID, payload: GroupUpdate, actor_id: UUID
    ) -> dict:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM synergia.identity_groups WHERE id = %s FOR UPDATE",
                    (group_id,),
                )
                before = cursor.fetchone()
                if before is None:
                    raise ApiError(
                        404, "access_resource_not_found", "Recurso nao encontrado"
                    )
                cursor.execute(
                    """
                    UPDATE synergia.identity_groups
                    SET group_name = COALESCE(%s, group_name),
                        external_reference = COALESCE(%s, external_reference)
                    WHERE id = %s AND version = %s RETURNING *
                    """,
                    (
                        payload.group_name,
                        payload.external_reference,
                        group_id,
                        payload.version,
                    ),
                )
                result = cursor.fetchone()
                if result is None:
                    self._version_or_not_found(cursor, "identity_groups", group_id)
                self._event(
                    cursor,
                    "access.group_updated",
                    actor_id,
                    "identity_group",
                    group_id,
                    payload.reason,
                    details={
                        "before": _audit_snapshot(
                            before, "group_name", "external_reference", "version"
                        ),
                        "after": _audit_snapshot(
                            result, "group_name", "external_reference", "version"
                        ),
                    },
                )
                connection.commit()
                return result
        except errors.UniqueViolation as exc:
            self._conflict(exc)

    @staticmethod
    def _version_or_not_found(cursor, table: str, entity_id: UUID) -> None:
        cursor.execute(f"SELECT 1 FROM synergia.{table} WHERE id = %s", (entity_id,))  # noqa: S608
        if cursor.fetchone() is None:
            raise ApiError(404, "access_resource_not_found", "Recurso nao encontrado")
        raise ApiError(
            409, "access_version_conflict", "O recurso foi alterado por outra operacao"
        )

    def _active_admin_count(self, cursor) -> int:
        return active_global_admin_count(cursor)

    def set_group_active(
        self, group_id: UUID, active: bool, payload: VersionedReason, actor_id: UUID
    ) -> dict:
        with self._connect() as connection, connection.cursor() as cursor:
            if not active:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s)", (LAST_ACTIVE_ADMIN_LOCK_ID,)
                )
            cursor.execute(
                "SELECT * FROM synergia.identity_groups WHERE id = %s FOR UPDATE",
                (group_id,),
            )
            before = cursor.fetchone()
            if before is None:
                raise ApiError(
                    404, "access_resource_not_found", "Recurso nao encontrado"
                )
            cursor.execute(
                """
                UPDATE synergia.identity_groups
                SET is_active = %s,
                    deactivated_at = CASE WHEN %s THEN NULL ELSE now() END
                WHERE id = %s AND version = %s AND is_active <> %s
                RETURNING *
                """,
                (active, active, group_id, payload.version, active),
            )
            result = cursor.fetchone()
            if result is None:
                self._version_or_not_found(cursor, "identity_groups", group_id)
            if not active and self._active_admin_count(cursor) == 0:
                raise ApiError(
                    409,
                    "last_active_admin",
                    "O ultimo administrador ativo deve ser preservado",
                )
            action = "activated" if active else "deactivated"
            self._event(
                cursor,
                f"access.group_{action}",
                actor_id,
                "identity_group",
                group_id,
                payload.reason,
                details={
                    "before": _audit_snapshot(
                        before, "is_active", "deactivated_at", "version"
                    ),
                    "after": _audit_snapshot(
                        result, "is_active", "deactivated_at", "version"
                    ),
                },
            )
            connection.commit()
            return result

    def create_role(self, payload: RoleCreate, actor_id: UUID) -> dict:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO synergia.roles (role_key, description)
                    VALUES (lower(btrim(%s)), %s) RETURNING *
                    """,
                    (payload.role_key, payload.description),
                )
                result = cursor.fetchone()
                self._event(
                    cursor,
                    "access.role_created",
                    actor_id,
                    "role",
                    result["id"],
                    payload.reason,
                )
                connection.commit()
                return result
        except errors.UniqueViolation as exc:
            self._conflict(exc)

    def list_roles(self, page: int, page_size: int) -> tuple[list[dict], int]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS total FROM synergia.roles")
            total = cursor.fetchone()["total"]
            cursor.execute(
                "SELECT * FROM synergia.roles ORDER BY normalized_key, id LIMIT %s OFFSET %s",
                (page_size, (page - 1) * page_size),
            )
            return cursor.fetchall(), total

    def get_role(self, role_id: UUID) -> dict | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM synergia.roles WHERE id = %s", (role_id,))
            return cursor.fetchone()

    def update_role(self, role_id: UUID, payload: RoleUpdate, actor_id: UUID) -> dict:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM synergia.roles WHERE id = %s FOR UPDATE", (role_id,)
            )
            before = cursor.fetchone()
            if before is None:
                raise ApiError(
                    404, "access_resource_not_found", "Recurso nao encontrado"
                )
            cursor.execute(
                """
                UPDATE synergia.roles SET description = %s
                WHERE id = %s AND version = %s RETURNING *
                """,
                (payload.description, role_id, payload.version),
            )
            result = cursor.fetchone()
            if result is None:
                self._version_or_not_found(cursor, "roles", role_id)
            self._event(
                cursor,
                "access.role_updated",
                actor_id,
                "role",
                role_id,
                payload.reason,
                details={
                    "before": _audit_snapshot(before, "description", "version"),
                    "after": _audit_snapshot(result, "description", "version"),
                },
            )
            connection.commit()
            return result

    def set_role_active(
        self, role_id: UUID, active: bool, payload: VersionedReason, actor_id: UUID
    ) -> dict:
        with self._connect() as connection, connection.cursor() as cursor:
            if not active:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s)", (LAST_ACTIVE_ADMIN_LOCK_ID,)
                )
            cursor.execute(
                "SELECT * FROM synergia.roles WHERE id = %s FOR UPDATE", (role_id,)
            )
            before = cursor.fetchone()
            if before is None:
                raise ApiError(
                    404, "access_resource_not_found", "Recurso nao encontrado"
                )
            cursor.execute(
                """
                UPDATE synergia.roles
                SET is_active = %s,
                    deactivated_at = CASE WHEN %s THEN NULL ELSE now() END
                WHERE id = %s AND version = %s AND is_active <> %s
                RETURNING *
                """,
                (active, active, role_id, payload.version, active),
            )
            result = cursor.fetchone()
            if result is None:
                self._version_or_not_found(cursor, "roles", role_id)
            if not active and self._active_admin_count(cursor) == 0:
                raise ApiError(
                    409,
                    "last_active_admin",
                    "O ultimo administrador ativo deve ser preservado",
                )
            action = "activated" if active else "deactivated"
            self._event(
                cursor,
                f"access.role_{action}",
                actor_id,
                "role",
                role_id,
                payload.reason,
                details={
                    "before": _audit_snapshot(
                        before, "is_active", "deactivated_at", "version"
                    ),
                    "after": _audit_snapshot(
                        result, "is_active", "deactivated_at", "version"
                    ),
                },
            )
            connection.commit()
            return result

    def list_permissions(self, catalog_version: str | None) -> list[dict]:
        with self._connect() as connection, connection.cursor() as cursor:
            where_clause = ""
            parameters: tuple[str, ...] = ()
            if catalog_version is not None:
                where_clause = "WHERE catalog_version = %s"
                parameters = (catalog_version,)
            cursor.execute(
                f"""
                SELECT id, permission_key, resource_type, description,
                       catalog_version, is_reserved, is_active
                FROM synergia.permissions
                {where_clause}
                ORDER BY normalized_key, id
                """,
                parameters,
            )
            return cursor.fetchall()

    @staticmethod
    def _association_config(kind: AssociationKind) -> tuple[str, str, str, bool]:
        return {
            "user_group": ("user_group_memberships", "user_id", "group_id", False),
            "user_role": ("user_role_assignments", "user_id", "role_id", True),
            "role_permission": ("role_permissions", "role_id", "permission_id", False),
            "group_role": ("group_role_assignments", "group_id", "role_id", True),
            "user_permission": (
                "user_permission_assignments",
                "user_id",
                "permission_id",
                True,
            ),
        }[kind]

    @staticmethod
    def _validate_grant_entities(
        cursor,
        kind: AssociationKind,
        left_id: UUID,
        right_id: UUID,
        organization_id: UUID | None,
    ) -> None:
        checks = {
            "user_group": (
                ("identity_users", left_id, "status = 'active'"),
                ("identity_groups", right_id, "is_active"),
            ),
            "user_role": (
                ("identity_users", left_id, "status = 'active'"),
                ("roles", right_id, "is_active"),
            ),
            "role_permission": (
                ("roles", left_id, "is_active"),
                ("permissions", right_id, "is_active"),
            ),
            "group_role": (
                ("identity_groups", left_id, "is_active"),
                ("roles", right_id, "is_active"),
            ),
            "user_permission": (
                ("identity_users", left_id, "status = 'active'"),
                ("permissions", right_id, "is_active"),
            ),
        }[kind]
        for table, entity_id, condition in checks:
            cursor.execute(
                f"SELECT EXISTS (SELECT 1 FROM synergia.{table} "
                f"WHERE id = %s AND {condition}) AS valid",  # noqa: S608
                (entity_id,),
            )
            if not cursor.fetchone()["valid"]:
                raise ApiError(
                    409,
                    "inactive_or_invalid_access_resource",
                    "A associacao exige recursos ativos e validos",
                )
        if organization_id is not None:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM synergia.iam_organizations
                    WHERE id = %s AND is_active
                ) AS valid
                """,
                (organization_id,),
            )
            if not cursor.fetchone()["valid"]:
                raise ApiError(
                    409,
                    "invalid_organization_scope",
                    "A organizacao informada nao e um escopo ativo",
                )

    def grant(
        self,
        kind: AssociationKind,
        left_id: UUID,
        right_id: UUID,
        payload: ReasonRequest,
        actor_id: UUID,
    ) -> dict:
        table, left_column, right_column, scoped = self._association_config(kind)
        organization_id = payload.organization_id if scoped else None
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                self._validate_grant_entities(
                    cursor, kind, left_id, right_id, organization_id
                )
                cursor.execute(
                    f"""
                    SELECT id, granted_at, revoked_at FROM synergia.{table}
                    WHERE {left_column} = %s AND {right_column} = %s
                      AND revoked_at IS NULL
                      {"AND organization_id IS NOT DISTINCT FROM %s" if scoped else ""}
                    """,  # noqa: S608
                    (left_id, right_id, organization_id)
                    if scoped
                    else (left_id, right_id),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    return {"id": existing["id"], "idempotent": True, "kind": kind}
                columns = f"{left_column}, {right_column}, granted_by_user_id"
                values = "%s, %s, %s"
                parameters: list[object] = [left_id, right_id, actor_id]
                if scoped:
                    columns += ", organization_id"
                    values += ", %s"
                    parameters.append(organization_id)
                cursor.execute(
                    f"INSERT INTO synergia.{table} ({columns}) VALUES ({values}) RETURNING id",  # noqa: S608
                    parameters,
                )
                association_id = cursor.fetchone()["id"]
                subject = (
                    left_id
                    if kind in {"user_group", "user_role", "user_permission"}
                    else None
                )
                self._event(
                    cursor,
                    "access.association_granted",
                    actor_id,
                    kind,
                    association_id,
                    payload.reason,
                    subject,
                    {
                        "left_id": str(left_id),
                        "right_id": str(right_id),
                        "change": "granted",
                    },
                    organization_id,
                )
                connection.commit()
                return {"id": association_id, "idempotent": False, "kind": kind}
        except (errors.UniqueViolation, errors.ForeignKeyViolation) as exc:
            self._conflict(exc)

    def revoke(
        self,
        kind: AssociationKind,
        left_id: UUID,
        right_id: UUID,
        payload: ReasonRequest,
        actor_id: UUID,
    ) -> dict:
        table, left_column, right_column, scoped = self._association_config(kind)
        organization_id = payload.organization_id if scoped else None
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)", (LAST_ACTIVE_ADMIN_LOCK_ID,)
            )
            cursor.execute(
                f"""
                UPDATE synergia.{table}
                SET revoked_at = now(), revocation_reason = %s
                WHERE {left_column} = %s AND {right_column} = %s
                  AND revoked_at IS NULL
                  {"AND organization_id IS NOT DISTINCT FROM %s" if scoped else ""}
                RETURNING id
                """,  # noqa: S608
                (payload.reason, left_id, right_id, organization_id)
                if scoped
                else (payload.reason, left_id, right_id),
            )
            result = cursor.fetchone()
            if result is None:
                return {"id": None, "idempotent": True, "kind": kind}
            if self._active_admin_count(cursor) == 0:
                raise ApiError(
                    409,
                    "last_active_admin",
                    "O ultimo administrador ativo deve ser preservado",
                )
            subject = (
                left_id
                if kind in {"user_group", "user_role", "user_permission"}
                else None
            )
            self._event(
                cursor,
                "access.association_revoked",
                actor_id,
                kind,
                result["id"],
                payload.reason,
                subject,
                {
                    "left_id": str(left_id),
                    "right_id": str(right_id),
                    "change": "revoked",
                },
                organization_id,
            )
            connection.commit()
            return {"id": result["id"], "idempotent": False, "kind": kind}

    def list_associations(
        self, kind: AssociationKind | None, page: int, page_size: int
    ) -> tuple[list[dict], int]:
        selects = []
        parameters: list[object] = []
        for current_kind in (
            "user_group",
            "user_role",
            "role_permission",
            "group_role",
            "user_permission",
        ):
            if kind and kind != current_kind:
                continue
            table, left_column, right_column, scoped = self._association_config(
                current_kind
            )
            organization = "organization_id" if scoped else "NULL::uuid"
            selects.append(
                f"SELECT '{current_kind}' AS kind, id, {left_column} AS left_id, "
                f"{right_column} AS right_id, {organization} AS organization_id, "
                f"granted_at, revoked_at FROM synergia.{table}"
            )
        union = " UNION ALL ".join(selects)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT count(*) AS total FROM ({union}) associations")  # noqa: S608
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"SELECT * FROM ({union}) associations "  # noqa: S608
                "ORDER BY granted_at, kind, id LIMIT %s OFFSET %s",
                [*parameters, page_size, (page - 1) * page_size],
            )
            return cursor.fetchall(), total

    def effective_permissions(
        self, user_id: UUID, organization_id: UUID | None
    ) -> list[dict]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.permission_key, p.resource_type, 'direct' AS source,
                       upa.id AS source_id, upa.organization_id,
                       o.organization_code
                FROM synergia.user_permission_assignments upa
                JOIN synergia.permissions p ON p.id = upa.permission_id AND p.is_active
                LEFT JOIN synergia.iam_organizations o ON o.id = upa.organization_id
                WHERE upa.user_id = %s AND upa.revoked_at IS NULL
                  AND (%s IS NULL OR upa.organization_id IS NULL OR upa.organization_id = %s)
                UNION ALL
                SELECT p.permission_key, p.resource_type, 'role', ura.id,
                       ura.organization_id, o.organization_code
                FROM synergia.user_role_assignments ura
                JOIN synergia.roles r ON r.id = ura.role_id AND r.is_active
                JOIN synergia.role_permissions rp ON rp.role_id = r.id AND rp.revoked_at IS NULL
                JOIN synergia.permissions p ON p.id = rp.permission_id AND p.is_active
                LEFT JOIN synergia.iam_organizations o ON o.id = ura.organization_id
                WHERE ura.user_id = %s AND ura.revoked_at IS NULL
                  AND (ura.expires_at IS NULL OR ura.expires_at > now())
                  AND (%s IS NULL OR ura.organization_id IS NULL OR ura.organization_id = %s)
                UNION ALL
                SELECT p.permission_key, p.resource_type, 'group', gra.id,
                       gra.organization_id, o.organization_code
                FROM synergia.user_group_memberships ugm
                JOIN synergia.identity_groups g ON g.id = ugm.group_id AND g.is_active
                JOIN synergia.group_role_assignments gra ON gra.group_id = g.id AND gra.revoked_at IS NULL
                JOIN synergia.roles r ON r.id = gra.role_id AND r.is_active
                JOIN synergia.role_permissions rp ON rp.role_id = r.id AND rp.revoked_at IS NULL
                JOIN synergia.permissions p ON p.id = rp.permission_id AND p.is_active
                LEFT JOIN synergia.iam_organizations o ON o.id = gra.organization_id
                WHERE ugm.user_id = %s AND ugm.revoked_at IS NULL
                  AND (%s IS NULL OR gra.organization_id IS NULL OR gra.organization_id = %s)
                ORDER BY permission_key, source, organization_code NULLS FIRST, source_id
                """,
                (
                    user_id,
                    organization_id,
                    organization_id,
                    user_id,
                    organization_id,
                    organization_id,
                    user_id,
                    organization_id,
                    organization_id,
                ),
            )
            return cursor.fetchall()


def get_access_repository() -> Generator[AccessRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ApiError(500, "database_not_configured", "Banco de dados indisponivel")
    yield PostgresAccessRepository(database_url)


Repository = Annotated[AccessRepository, Depends(get_access_repository)]


def _authorize(repository: AccessRepository, actor: Actor) -> None:
    repository.authorize(actor.user_id)


def _page(items: list[dict], total: int, page: int, page_size: int, sort: str) -> Page:
    return Page(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=math.ceil(total / page_size) if total else 0,
        sort=sort,
    )


@router.post(
    "/groups",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def create_group(
    payload: GroupCreate, repository: Repository, actor: CurrentActor
) -> dict:
    _authorize(repository, actor)
    return repository.create_group(payload, actor.user_id)


@router.get("/groups", response_model=Page, responses=ERROR_RESPONSES)
def list_groups(
    repository: Repository,
    actor: CurrentActor,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page:
    _authorize(repository, actor)
    items, total = repository.list_groups(page, page_size)
    return _page(items, total, page, page_size, "normalized_name,id")


@router.get(
    "/groups/{group_id}", response_model=GroupResponse, responses=ERROR_RESPONSES
)
def get_group(group_id: UUID, repository: Repository, actor: CurrentActor) -> dict:
    _authorize(repository, actor)
    result = repository.get_group(group_id)
    if result is None:
        raise ApiError(404, "access_resource_not_found", "Recurso nao encontrado")
    return result


@router.patch(
    "/groups/{group_id}", response_model=GroupResponse, responses=ERROR_RESPONSES
)
def update_group(
    group_id: UUID, payload: GroupUpdate, repository: Repository, actor: CurrentActor
) -> dict:
    _authorize(repository, actor)
    return repository.update_group(group_id, payload, actor.user_id)


@router.post(
    "/groups/{group_id}/deactivate",
    response_model=GroupResponse,
    responses=ERROR_RESPONSES,
)
def deactivate_group(
    group_id: UUID,
    payload: VersionedReason,
    repository: Repository,
    actor: CurrentActor,
) -> dict:
    _authorize(repository, actor)
    return repository.set_group_active(group_id, False, payload, actor.user_id)


@router.post(
    "/groups/{group_id}/activate",
    response_model=GroupResponse,
    responses=ERROR_RESPONSES,
)
def activate_group(
    group_id: UUID,
    payload: VersionedReason,
    repository: Repository,
    actor: CurrentActor,
) -> dict:
    _authorize(repository, actor)
    return repository.set_group_active(group_id, True, payload, actor.user_id)


@router.post(
    "/roles",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def create_role(
    payload: RoleCreate, repository: Repository, actor: CurrentActor
) -> dict:
    _authorize(repository, actor)
    return repository.create_role(payload, actor.user_id)


@router.get("/roles", response_model=Page, responses=ERROR_RESPONSES)
def list_roles(
    repository: Repository,
    actor: CurrentActor,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page:
    _authorize(repository, actor)
    items, total = repository.list_roles(page, page_size)
    return _page(items, total, page, page_size, "normalized_key,id")


@router.get("/roles/{role_id}", response_model=RoleResponse, responses=ERROR_RESPONSES)
def get_role(role_id: UUID, repository: Repository, actor: CurrentActor) -> dict:
    _authorize(repository, actor)
    result = repository.get_role(role_id)
    if result is None:
        raise ApiError(404, "access_resource_not_found", "Recurso nao encontrado")
    return result


@router.patch(
    "/roles/{role_id}", response_model=RoleResponse, responses=ERROR_RESPONSES
)
def update_role(
    role_id: UUID, payload: RoleUpdate, repository: Repository, actor: CurrentActor
) -> dict:
    _authorize(repository, actor)
    return repository.update_role(role_id, payload, actor.user_id)


@router.post(
    "/roles/{role_id}/deactivate",
    response_model=RoleResponse,
    responses=ERROR_RESPONSES,
)
def deactivate_role(
    role_id: UUID,
    payload: VersionedReason,
    repository: Repository,
    actor: CurrentActor,
) -> dict:
    _authorize(repository, actor)
    return repository.set_role_active(role_id, False, payload, actor.user_id)


@router.post(
    "/roles/{role_id}/activate",
    response_model=RoleResponse,
    responses=ERROR_RESPONSES,
)
def activate_role(
    role_id: UUID,
    payload: VersionedReason,
    repository: Repository,
    actor: CurrentActor,
) -> dict:
    _authorize(repository, actor)
    return repository.set_role_active(role_id, True, payload, actor.user_id)


@router.get(
    "/permissions", response_model=list[PermissionResponse], responses=ERROR_RESPONSES
)
def list_permissions(
    repository: Repository, actor: CurrentActor, catalog_version: str | None = None
) -> list[dict]:
    _authorize(repository, actor)
    return repository.list_permissions(catalog_version)


def _association_path(kind: AssociationKind):
    def grant_endpoint(
        left_id: UUID,
        right_id: UUID,
        payload: ReasonRequest,
        repository: Repository,
        actor: CurrentActor,
    ) -> dict:
        _authorize(repository, actor)
        return repository.grant(kind, left_id, right_id, payload, actor.user_id)

    def revoke_endpoint(
        left_id: UUID,
        right_id: UUID,
        payload: ReasonRequest,
        repository: Repository,
        actor: CurrentActor,
    ) -> dict:
        _authorize(repository, actor)
        return repository.revoke(kind, left_id, right_id, payload, actor.user_id)

    return grant_endpoint, revoke_endpoint


for _kind, _path in {
    "user_group": "/users/{left_id}/groups/{right_id}",
    "user_role": "/users/{left_id}/roles/{right_id}",
    "role_permission": "/roles/{left_id}/permissions/{right_id}",
    "group_role": "/groups/{left_id}/roles/{right_id}",
    "user_permission": "/users/{left_id}/permissions/{right_id}",
}.items():
    _grant, _revoke = _association_path(_kind)
    router.add_api_route(
        _path,
        _grant,
        methods=["PUT"],
        response_model=AssociationResponse,
        responses=ERROR_RESPONSES,
    )
    router.add_api_route(
        _path,
        _revoke,
        methods=["DELETE"],
        response_model=AssociationResponse,
        responses=ERROR_RESPONSES,
    )


@router.get("/associations", response_model=Page, responses=ERROR_RESPONSES)
def list_associations(
    repository: Repository,
    actor: CurrentActor,
    kind: AssociationKind | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page:
    _authorize(repository, actor)
    items, total = repository.list_associations(kind, page, page_size)
    return _page(items, total, page, page_size, "granted_at,kind,id")


@router.get(
    "/users/{user_id}/effective-permissions",
    response_model=EffectivePermissionsResponse,
    responses=ERROR_RESPONSES,
)
def effective_permissions(
    user_id: UUID,
    repository: Repository,
    actor: CurrentActor,
    organization_id: UUID | None = None,
) -> EffectivePermissionsResponse:
    _authorize(repository, actor)
    return EffectivePermissionsResponse(
        user_id=user_id,
        permissions=repository.effective_permissions(user_id, organization_id),
    )
