from __future__ import annotations

import os
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.auth.config import AuthConfig
from app.auth.security import AccessClaims, TokenCodec
from app.errors import ApiError

INVALID_SESSION = "Sessao invalida ou expirada"
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ActorContext:
    user_id: UUID
    session_id: UUID
    token_id: UUID
    permissions: dict[str, frozenset[UUID | None]]
    correlation_id: UUID

    def scopes_for(self, permission: str) -> frozenset[UUID | None]:
        return self.permissions.get(permission, frozenset())

    def allows(self, permission: str, organization_id: UUID | None = None) -> bool:
        scopes = self.scopes_for(permission)
        return None in scopes or organization_id in scopes

    def organization_ids(self, permission: str) -> frozenset[UUID]:
        return frozenset(
            scope for scope in self.scopes_for(permission) if scope is not None
        )

    def scope_filter(self, permission: str) -> frozenset[UUID] | None:
        scopes = self.scopes_for(permission)
        return None if None in scopes else self.organization_ids(permission)


class AuthorizationRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def resolve(self, claims: AccessClaims, now: datetime) -> dict | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.user_id
                FROM synergia.identity_sessions s
                JOIN synergia.identity_users u ON u.id = s.user_id
                WHERE s.id = %s AND s.user_id = %s
                  AND s.status = 'active' AND u.status = 'active'
                  AND s.idle_expires_at > %s AND s.absolute_expires_at > %s
                """,
                (claims.session_id, claims.user_id, now, now),
            )
            if cursor.fetchone() is None:
                return None
            cursor.execute(
                """
                SELECT p.normalized_key AS permission_key, ura.organization_id
                FROM synergia.user_role_assignments ura
                JOIN synergia.roles r ON r.id = ura.role_id AND r.is_active
                JOIN synergia.role_permissions rp
                  ON rp.role_id = r.id AND rp.revoked_at IS NULL
                JOIN synergia.permissions p
                  ON p.id = rp.permission_id AND p.is_active
                WHERE ura.user_id = %s AND ura.revoked_at IS NULL
                  AND (ura.expires_at IS NULL OR ura.expires_at > %s)
                UNION
                SELECT p.normalized_key, gra.organization_id
                FROM synergia.user_group_memberships ugm
                JOIN synergia.identity_groups g
                  ON g.id = ugm.group_id AND g.is_active
                JOIN synergia.group_role_assignments gra
                  ON gra.group_id = g.id AND gra.revoked_at IS NULL
                JOIN synergia.roles r ON r.id = gra.role_id AND r.is_active
                JOIN synergia.role_permissions rp
                  ON rp.role_id = r.id AND rp.revoked_at IS NULL
                JOIN synergia.permissions p
                  ON p.id = rp.permission_id AND p.is_active
                WHERE ugm.user_id = %s AND ugm.revoked_at IS NULL
                UNION
                SELECT p.normalized_key, upa.organization_id
                FROM synergia.user_permission_assignments upa
                JOIN synergia.permissions p
                  ON p.id = upa.permission_id AND p.is_active
                WHERE upa.user_id = %s AND upa.revoked_at IS NULL
                """,
                (claims.user_id, now, claims.user_id, claims.user_id),
            )
            permissions: dict[str, set[UUID | None]] = {}
            for row in cursor.fetchall():
                permissions.setdefault(row["permission_key"], set()).add(
                    row["organization_id"]
                )
            return {key: frozenset(scopes) for key, scopes in permissions.items()}

    def audit_denial(
        self,
        actor: ActorContext,
        permission: str,
        request: Request,
        organization_id: UUID | None = None,
    ) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO synergia.identity_access_events (
                    event_key, actor_user_id, subject_user_id, session_id,
                    organization_id, entity_type, entity_id, payload,
                    correlation_id
                ) VALUES (
                    'authorization.denied', %s, %s, %s, %s,
                    'api_route', %s, %s, %s
                )
                """,
                (
                    actor.user_id,
                    actor.user_id,
                    actor.session_id,
                    organization_id,
                    request.scope.get("route").path
                    if request.scope.get("route") is not None
                    else "unknown",
                    Jsonb({"method": request.method, "permission": permission}),
                    actor.correlation_id,
                ),
            )

    def execution_organization(self, execution_id: str) -> UUID | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT organization_id FROM synergia.executions WHERE id = %s",
                (execution_id,),
            )
            row = cursor.fetchone()
            return row["organization_id"] if row else None

    def resource_organization(self, resource: str, identifier: str) -> UUID | None:
        statements = {
            "workorder": """
                SELECT e.organization_id FROM synergia.workorders w
                JOIN synergia.executions e ON e.id = w.execution_id
                WHERE w.workorder_number = %s
                ORDER BY w.updated_at DESC LIMIT 1
            """,
            "lot": """
                SELECT e.organization_id FROM synergia.lots l
                JOIN synergia.executions e ON e.id = l.execution_id
                WHERE l.lot_number = %s
                ORDER BY l.updated_at DESC LIMIT 1
            """,
            "serial": """
                SELECT e.organization_id FROM synergia.serials s
                JOIN synergia.executions e ON e.id = s.execution_id
                WHERE s.serial_number = %s
                ORDER BY s.updated_at DESC LIMIT 1
            """,
            "pending": """
                SELECT e.organization_id FROM synergia.pending_items p
                JOIN synergia.executions e ON e.id = p.execution_id
                WHERE p.id = %s LIMIT 1
            """,
        }
        statement = statements.get(resource)
        if statement is None:
            raise ValueError("unsupported authorization resource")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement, (identifier,))
            row = cursor.fetchone()
            return row["organization_id"] if row else None

    def lot_organization(
        self, lot_number: str, workorder_number: str | None = None
    ) -> UUID | None:
        filters = ["l.lot_number = %s"]
        parameters: list[str] = [lot_number]
        if workorder_number:
            filters.append("w.workorder_number = %s")
            parameters.append(workorder_number)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT e.organization_id
                FROM synergia.lots l
                JOIN synergia.workorders w ON w.id = l.workorder_id
                JOIN synergia.executions e ON e.id = l.execution_id
                WHERE {" AND ".join(filters)}
                ORDER BY l.updated_at DESC, l.id DESC
                LIMIT 1
                """,
                parameters,
            )
            row = cursor.fetchone()
            return row["organization_id"] if row else None


def get_authorization_repository() -> Generator[AuthorizationRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ApiError(503, "database_not_configured", "Autorizacao indisponivel")
    yield AuthorizationRepository(database_url)


AuthorizationRepo = Annotated[
    AuthorizationRepository, Depends(get_authorization_repository)
]


def get_authorization_config() -> AuthConfig:
    return AuthConfig.from_env()


def get_access_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AccessClaims:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(
            401,
            "invalid_access_token",
            INVALID_SESSION,
            headers={"WWW-Authenticate": "Bearer"},
        )
    config = get_authorization_config()
    try:
        return TokenCodec(config).decode_access(credentials.credentials)
    except Exception as exc:
        raise ApiError(
            401,
            "invalid_access_token",
            INVALID_SESSION,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_actor_context(
    request: Request,
    claims: Annotated[AccessClaims, Depends(get_access_claims)],
    repository: AuthorizationRepo,
) -> ActorContext:
    permissions = repository.resolve(claims, datetime.now(UTC))
    if permissions is None:
        raise ApiError(
            401,
            "invalid_access_token",
            INVALID_SESSION,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return ActorContext(
        user_id=claims.user_id,
        session_id=claims.session_id,
        token_id=claims.token_id,
        permissions=permissions,
        correlation_id=request.state.correlation_id,
    )


CurrentActor = Annotated[ActorContext, Depends(get_actor_context)]


def require_permission(permission: str) -> Callable:
    def dependency(
        request: Request,
        actor: CurrentActor,
        repository: AuthorizationRepo,
    ) -> ActorContext:
        if not actor.scopes_for(permission):
            repository.audit_denial(actor, permission, request)
            raise ApiError(403, "access_denied", "Acao nao autorizada")
        return actor

    return dependency


def permission_dependency(permission: str):
    return Depends(require_permission(permission))


def require_execution_permission(permission: str) -> Callable:
    def dependency(
        execution_id: str,
        request: Request,
        actor: CurrentActor,
        repository: AuthorizationRepo,
    ) -> ActorContext:
        if not actor.scopes_for(permission):
            repository.audit_denial(actor, permission, request)
            raise ApiError(403, "access_denied", "Acao nao autorizada")
        organization_id = repository.execution_organization(execution_id)
        if organization_id is None or not actor.allows(permission, organization_id):
            repository.audit_denial(
                actor, permission, request, organization_id=organization_id
            )
            raise ApiError(404, "resource_not_found", "Recurso nao encontrado")
        return actor

    return dependency


def require_resource_permission(
    permission: str, resource: str, path_parameter: str
) -> Callable:
    def dependency(
        request: Request,
        actor: CurrentActor,
        repository: AuthorizationRepo,
    ) -> ActorContext:
        if not actor.scopes_for(permission):
            repository.audit_denial(actor, permission, request)
            raise ApiError(403, "access_denied", "Acao nao autorizada")
        identifier = str(request.path_params[path_parameter])
        execution_id = request.query_params.get("execution_id")
        organization_id = (
            repository.execution_organization(execution_id)
            if execution_id
            else repository.resource_organization(resource, identifier)
        )
        if organization_id is None or not actor.allows(permission, organization_id):
            repository.audit_denial(
                actor, permission, request, organization_id=organization_id
            )
            raise ApiError(404, "resource_not_found", "Recurso nao encontrado")
        return actor

    return dependency


def require_lot_permission(permission: str) -> Callable:
    def dependency(
        lot_number: str,
        request: Request,
        actor: CurrentActor,
        repository: AuthorizationRepo,
        workorder_number: str | None = None,
    ) -> ActorContext:
        if not actor.scopes_for(permission):
            repository.audit_denial(actor, permission, request)
            raise ApiError(403, "access_denied", "Acao nao autorizada")
        organization_id = repository.lot_organization(lot_number, workorder_number)
        if organization_id is not None and not actor.allows(
            permission, organization_id
        ):
            repository.audit_denial(
                actor, permission, request, organization_id=organization_id
            )
            raise ApiError(
                404,
                "lot_not_found",
                "Lot não encontrado",
                {"identifier": lot_number},
            )
        return actor

    return dependency


def global_admins_cte() -> str:
    return """
    WITH effective_admins AS (
        SELECT ura.user_id
        FROM synergia.user_role_assignments ura
        JOIN synergia.roles r ON r.id = ura.role_id AND r.is_active
        WHERE ura.revoked_at IS NULL
          AND ura.organization_id IS NULL
          AND (ura.expires_at IS NULL OR ura.expires_at > now())
          AND r.normalized_key = 'admin'
        UNION
        SELECT ugm.user_id
        FROM synergia.user_group_memberships ugm
        JOIN synergia.identity_groups g ON g.id = ugm.group_id AND g.is_active
        JOIN synergia.group_role_assignments gra
          ON gra.group_id = g.id AND gra.revoked_at IS NULL
        JOIN synergia.roles r ON r.id = gra.role_id AND r.is_active
        WHERE ugm.revoked_at IS NULL
          AND gra.organization_id IS NULL
          AND r.normalized_key = 'admin'
        UNION
        SELECT upa.user_id
        FROM synergia.user_permission_assignments upa
        JOIN synergia.permissions p
          ON p.id = upa.permission_id AND p.is_active
        WHERE upa.revoked_at IS NULL
          AND upa.organization_id IS NULL
          AND p.normalized_key = 'access.admin'
        UNION
        SELECT ura.user_id
        FROM synergia.user_role_assignments ura
        JOIN synergia.roles r ON r.id = ura.role_id AND r.is_active
        JOIN synergia.role_permissions rp
          ON rp.role_id = r.id AND rp.revoked_at IS NULL
        JOIN synergia.permissions p
          ON p.id = rp.permission_id AND p.is_active
        WHERE ura.revoked_at IS NULL
          AND ura.organization_id IS NULL
          AND (ura.expires_at IS NULL OR ura.expires_at > now())
          AND p.normalized_key = 'access.admin'
        UNION
        SELECT ugm.user_id
        FROM synergia.user_group_memberships ugm
        JOIN synergia.identity_groups g ON g.id = ugm.group_id AND g.is_active
        JOIN synergia.group_role_assignments gra
          ON gra.group_id = g.id AND gra.revoked_at IS NULL
        JOIN synergia.roles r ON r.id = gra.role_id AND r.is_active
        JOIN synergia.role_permissions rp
          ON rp.role_id = r.id AND rp.revoked_at IS NULL
        JOIN synergia.permissions p
          ON p.id = rp.permission_id AND p.is_active
        WHERE ugm.revoked_at IS NULL
          AND gra.organization_id IS NULL
          AND p.normalized_key = 'access.admin'
    )
    """


def is_global_admin(cursor, user_id: UUID) -> bool:
    cursor.execute(
        global_admins_cte()
        + """
        SELECT EXISTS (
            SELECT 1
            FROM effective_admins ea
            JOIN synergia.identity_users u ON u.id = ea.user_id
            WHERE ea.user_id = %s AND u.status = 'active'
        ) AS authorized
        """,
        (user_id,),
    )
    return cursor.fetchone()["authorized"]


def active_global_admin_count(cursor) -> int:
    cursor.execute(
        global_admins_cte()
        + """
        SELECT count(DISTINCT ea.user_id) AS total
        FROM effective_admins ea
        JOIN synergia.identity_users u ON u.id = ea.user_id
        WHERE u.status = 'active'
        """
    )
    return cursor.fetchone()["total"]
