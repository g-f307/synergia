from __future__ import annotations

# Approval transitions intentionally keep their SQL together for transactional review.
# ruff: noqa: E501
import os
from collections.abc import Generator
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.authorization import ActorContext, require_permission
from app.errors import ApiError, ErrorResponse

router = APIRouter(tags=["approvals"])

ApprovalState = Literal[
    "draft", "submitted", "in_review", "approved", "rejected", "returned"
]
ERROR_RESPONSES = {
    403: {"model": ErrorResponse, "description": "Ação não autorizada"},
    404: {"model": ErrorResponse, "description": "Solicitação não encontrada"},
    409: {"model": ErrorResponse, "description": "Estado ou versão incompatível"},
    422: {"model": ErrorResponse, "description": "Regra de decisão não atendida"},
}


class ApprovalEventResponse(BaseModel):
    id: int
    event_type: str
    from_state: str | None
    to_state: str
    actor_user_id: UUID
    assignee_user_id: UUID | None
    justification: str | None
    consent: bool
    request_version: int
    occurred_at: datetime


class ApprovalResponse(BaseModel):
    id: UUID
    pending_item_id: int
    organization_id: UUID
    requester_user_id: UUID
    assignee_user_id: UUID | None
    review_group: str
    policy_key: str
    policy_version: int
    state: ApprovalState
    version: int
    created_at: datetime
    submitted_at: datetime | None
    decided_at: datetime | None
    updated_at: datetime
    history: list[ApprovalEventResponse] = Field(default_factory=list)


class VersionedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(gt=0)


class CreateApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    justification: str = Field(min_length=1, max_length=2000)


class AssignmentRequest(VersionedRequest):
    assignee_user_id: UUID
    justification: str = Field(min_length=1, max_length=2000)


class DecisionRequest(VersionedRequest):
    justification: str = Field(min_length=1, max_length=4000)
    consent: StrictBool = False


class ApprovalRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _permissions(actor: ActorContext) -> list[str]:
        return sorted(key for key, scopes in actor.permissions.items() if scopes)

    @staticmethod
    def _visible(actor: ActorContext, permission: str, organization_id: UUID) -> bool:
        return actor.allows(permission, organization_id)

    def _history(self, connection, request_id: UUID) -> list[dict]:
        return list(
            connection.execute(
                """
                SELECT id, event_type, from_state, to_state, actor_user_id,
                       assignee_user_id, justification, consent,
                       request_version, occurred_at
                FROM synergia.approval_events
                WHERE request_id = %s
                ORDER BY occurred_at, id
                """,
                (request_id,),
            ).fetchall()
        )

    def _serialize(self, connection, row: dict) -> dict:
        result = dict(row)
        result["history"] = self._history(connection, row["id"])
        return result

    def get_for_pending(
        self, pending_id: int, actor: ActorContext, permission: str = "approval.read"
    ) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT ar.*
                FROM synergia.approval_requests ar
                WHERE ar.pending_item_id = %s
                ORDER BY ar.created_at DESC, ar.id DESC
                LIMIT 1
                """,
                (pending_id,),
            ).fetchone()
            if row is None or not self._visible(
                actor, permission, row["organization_id"]
            ):
                return None
            return self._serialize(connection, row)

    def create(
        self, pending_id: int, justification: str, actor: ActorContext
    ) -> dict | None:
        with self._connect() as connection:
            pending = connection.execute(
                """
                SELECT p.id, p.status, e.organization_id
                FROM synergia.pending_items p
                JOIN synergia.executions e ON e.id = p.execution_id
                WHERE p.id = %s
                FOR UPDATE
                """,
                (pending_id,),
            ).fetchone()
            if pending is None or not self._visible(
                actor, "approval.submit", pending["organization_id"]
            ):
                return None
            if pending["status"] != "open":
                raise ApiError(409, "pending_not_open", "A pendência não está aberta")
            existing = connection.execute(
                """
                SELECT id FROM synergia.approval_requests
                WHERE pending_item_id = %s
                  AND state IN ('draft', 'submitted', 'in_review', 'returned')
                """,
                (pending_id,),
            ).fetchone()
            if existing:
                raise ApiError(
                    409,
                    "approval_already_active",
                    "A pendência já possui solicitação ativa",
                )
            policy = connection.execute(
                """
                SELECT * FROM synergia.approval_policies
                WHERE policy_key = 'pending.standard' AND is_active
                """
            ).fetchone()
            if policy is None:
                raise ApiError(
                    503,
                    "approval_policy_unavailable",
                    "Política de aprovação indisponível",
                )
            row = connection.execute(
                """
                INSERT INTO synergia.approval_requests (
                    pending_item_id, organization_id, requester_user_id,
                    requester_session_id, review_group, policy_key,
                    policy_version, state, submitted_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'submitted', now())
                RETURNING *
                """,
                (
                    pending_id,
                    pending["organization_id"],
                    actor.user_id,
                    actor.session_id,
                    policy["review_group"],
                    policy["policy_key"],
                    policy["version"],
                ),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO synergia.approval_stages (
                    request_id, sequence, review_group, state
                ) VALUES (%s, 1, %s, 'waiting')
                """,
                (row["id"], policy["review_group"]),
            )
            event_id = self._event(
                connection,
                row,
                actor,
                "submitted",
                None,
                "submitted",
                justification,
                False,
                None,
            )
            self._notify(
                connection, row, actor, "approval.submitted", event_id=event_id
            )
            return self._serialize(connection, row)

    def _load_locked(self, connection, request_id: UUID) -> dict | None:
        return connection.execute(
            """
            SELECT ar.*, ap.require_distinct_approver,
                   ap.require_approval_justification,
                   ap.require_rejection_justification,
                   ap.require_return_justification
            FROM synergia.approval_requests ar
            JOIN synergia.approval_policies ap
              ON ap.policy_key = ar.policy_key AND ap.version = ar.policy_version
            WHERE ar.id = %s
            FOR UPDATE OF ar
            """,
            (request_id,),
        ).fetchone()

    def _check(
        self, row: dict | None, actor: ActorContext, permission: str, version: int
    ) -> dict:
        if row is None or not self._visible(actor, permission, row["organization_id"]):
            raise ApiError(404, "approval_not_found", "Solicitação não encontrada")
        if row["version"] != version:
            raise ApiError(
                409, "approval_version_conflict", "A solicitação foi atualizada"
            )
        return row

    def assign(
        self,
        request_id: UUID,
        assignee_id: UUID,
        version: int,
        justification: str,
        actor: ActorContext,
    ) -> dict:
        with self._connect() as connection:
            row = self._check(
                self._load_locked(connection, request_id),
                actor,
                "approval.assign",
                version,
            )
            if row["state"] not in {"submitted", "in_review"}:
                raise ApiError(
                    409,
                    "approval_state_conflict",
                    "A solicitação não pode ser atribuída neste estado",
                )
            eligible = connection.execute(
                """
                SELECT u.status = 'active'
                   AND synergia.user_has_effective_permission(
                       u.id, 'approval.decide', %s
                   )
                   AND (
                       EXISTS (
                           SELECT 1
                           FROM synergia.user_role_assignments ura
                           JOIN synergia.roles r
                             ON r.id = ura.role_id AND r.is_active
                           WHERE ura.user_id = u.id
                             AND ura.organization_id = %s
                             AND ura.revoked_at IS NULL
                             AND (ura.expires_at IS NULL OR ura.expires_at > now())
                             AND r.normalized_key = %s
                       )
                       OR EXISTS (
                           SELECT 1
                           FROM synergia.user_group_memberships ugm
                           JOIN synergia.identity_groups g
                             ON g.id = ugm.group_id AND g.is_active
                           JOIN synergia.group_role_assignments gra
                             ON gra.group_id = g.id AND gra.revoked_at IS NULL
                           JOIN synergia.roles r
                             ON r.id = gra.role_id AND r.is_active
                           WHERE ugm.user_id = u.id
                             AND ugm.revoked_at IS NULL
                             AND gra.organization_id = %s
                             AND r.normalized_key = %s
                       )
                   ) AS eligible
                FROM synergia.identity_users u WHERE u.id = %s
                """,
                (
                    row["organization_id"],
                    row["organization_id"],
                    row["review_group"],
                    row["organization_id"],
                    row["review_group"],
                    assignee_id,
                ),
            ).fetchone()
            if eligible is None or not eligible["eligible"]:
                raise ApiError(
                    422,
                    "assignee_not_eligible",
                    "Responsável não elegível para decidir",
                )
            event_type = "reassigned" if row["assignee_user_id"] else "assigned"
            updated = connection.execute(
                """
                UPDATE synergia.approval_requests
                SET assignee_user_id = %s, state = 'in_review',
                    version = version + 1, updated_at = now()
                WHERE id = %s RETURNING *
                """,
                (assignee_id, request_id),
            ).fetchone()
            connection.execute(
                """
                UPDATE synergia.approval_stages
                SET assignee_user_id = %s, state = 'in_review'
                WHERE request_id = %s
                  AND sequence = (
                      SELECT max(current_stage.sequence)
                      FROM synergia.approval_stages current_stage
                      WHERE current_stage.request_id = %s
                        AND current_stage.state IN ('waiting', 'in_review')
                  )
                """,
                (assignee_id, request_id, request_id),
            )
            event_id = self._event(
                connection,
                updated,
                actor,
                event_type,
                row["state"],
                "in_review",
                justification,
                False,
                assignee_id,
            )
            self._notify(
                connection,
                updated,
                actor,
                "approval.assigned",
                recipient=assignee_id,
                event_id=event_id,
            )
            return self._serialize(connection, updated)

    def decide(
        self,
        request_id: UUID,
        action: Literal["approved", "rejected", "returned"],
        version: int,
        justification: str,
        consent: bool,
        actor: ActorContext,
    ) -> dict:
        with self._connect() as connection:
            row = self._check(
                self._load_locked(connection, request_id),
                actor,
                "approval.decide",
                version,
            )
            if row["state"] != "in_review" or row["assignee_user_id"] != actor.user_id:
                raise ApiError(
                    409,
                    "approval_not_assigned",
                    "A decisão exige atribuição ao ator atual",
                )
            if (
                row["require_distinct_approver"]
                and row["requester_user_id"] == actor.user_id
            ):
                raise ApiError(
                    422,
                    "self_approval_forbidden",
                    "A política exige outro usuário para decidir",
                )
            required_key = f"require_{'approval' if action == 'approved' else 'rejection' if action == 'rejected' else 'return'}_justification"
            if row[required_key] and not justification.strip():
                raise ApiError(
                    422, "justification_required", "Justificativa obrigatória"
                )
            if action == "approved" and not consent:
                raise ApiError(
                    422, "consent_required", "Consentimento explícito obrigatório"
                )
            updated = connection.execute(
                """
                UPDATE synergia.approval_requests
                SET state = %s, version = version + 1, updated_at = now(),
                    decided_at = CASE WHEN %s IN ('approved', 'rejected') THEN now() ELSE NULL END
                WHERE id = %s RETURNING *
                """,
                (action, action, request_id),
            ).fetchone()
            connection.execute(
                """
                UPDATE synergia.approval_stages
                SET state = %s, closed_at = now()
                WHERE request_id = %s
                  AND sequence = (
                      SELECT max(current_stage.sequence)
                      FROM synergia.approval_stages current_stage
                      WHERE current_stage.request_id = %s
                        AND current_stage.state = 'in_review'
                  )
                """,
                (
                    "returned" if action == "returned" else "completed",
                    request_id,
                    request_id,
                ),
            )
            event_id = self._event(
                connection,
                updated,
                actor,
                action,
                "in_review",
                action,
                justification,
                consent,
                actor.user_id,
            )
            self._notify(
                connection,
                updated,
                actor,
                f"approval.{action}",
                recipient=row["requester_user_id"],
                event_id=event_id,
            )
            return self._serialize(connection, updated)

    def resubmit(
        self, request_id: UUID, version: int, justification: str, actor: ActorContext
    ) -> dict:
        with self._connect() as connection:
            row = self._check(
                self._load_locked(connection, request_id),
                actor,
                "approval.submit",
                version,
            )
            if row["state"] != "returned" or row["requester_user_id"] != actor.user_id:
                raise ApiError(
                    409,
                    "approval_state_conflict",
                    "Somente o solicitante pode reenviar uma devolução",
                )
            updated = connection.execute(
                """
                UPDATE synergia.approval_requests
                SET state = 'submitted', assignee_user_id = NULL,
                    version = version + 1, submitted_at = now(), updated_at = now()
                WHERE id = %s RETURNING *
                """,
                (request_id,),
            ).fetchone()
            sequence = connection.execute(
                "SELECT COALESCE(max(sequence), 0) + 1 AS value FROM synergia.approval_stages WHERE request_id = %s",
                (request_id,),
            ).fetchone()["value"]
            connection.execute(
                "INSERT INTO synergia.approval_stages (request_id, sequence, review_group, state) VALUES (%s, %s, %s, 'waiting')",
                (request_id, sequence, row["review_group"]),
            )
            event_id = self._event(
                connection,
                updated,
                actor,
                "resubmitted",
                "returned",
                "submitted",
                justification,
                False,
                None,
            )
            self._notify(
                connection, updated, actor, "approval.resubmitted", event_id=event_id
            )
            return self._serialize(connection, updated)

    def _event(
        self,
        connection,
        row: dict,
        actor: ActorContext,
        event_type: str,
        from_state: str | None,
        to_state: str,
        justification: str | None,
        consent: bool,
        assignee: UUID | None,
    ) -> int:
        event_id = connection.execute(
            """
            INSERT INTO synergia.approval_events (
                request_id, event_type, from_state, to_state, actor_user_id,
                actor_session_id, organization_id, actor_permissions,
                assignee_user_id, justification, consent, request_version,
                correlation_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                row["id"],
                event_type,
                from_state,
                to_state,
                actor.user_id,
                actor.session_id,
                row["organization_id"],
                Jsonb(self._permissions(actor)),
                assignee,
                justification.strip() if justification else None,
                consent,
                row["version"],
                actor.correlation_id,
            ),
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO synergia.identity_access_events (
                event_key, actor_user_id, subject_user_id, session_id,
                organization_id, entity_type, entity_id, payload, correlation_id
            ) VALUES (%s, %s, %s, %s, %s, 'approval_request', %s, %s, %s)
            """,
            (
                f"approval.{event_type}",
                actor.user_id,
                assignee,
                actor.session_id,
                row["organization_id"],
                str(row["id"]),
                Jsonb({"from": from_state, "to": to_state, "version": row["version"]}),
                actor.correlation_id,
            ),
        )
        return event_id

    @staticmethod
    def _notify(
        connection,
        row: dict,
        actor: ActorContext,
        notification_type: str,
        recipient: UUID | None = None,
        event_id: int = 0,
    ) -> None:
        recipients: list[UUID] = []
        if recipient:
            recipients = [recipient]
        else:
            recipients = [
                item["id"]
                for item in connection.execute(
                    """
                    SELECT id FROM synergia.identity_users
                    WHERE status = 'active'
                      AND synergia.user_has_effective_permission(id, 'approval.read', %s)
                    """,
                    (row["organization_id"],),
                ).fetchall()
            ]
        for user_id in recipients:
            connection.execute(
                "SELECT synergia.enqueue_internal_notification(%s, %s, %s, %s, %s, %s, 'audit_event', %s, now(), %s)",
                (
                    user_id,
                    row["organization_id"],
                    notification_type,
                    str(row["id"]),
                    Jsonb(
                        {
                            "request_id": str(row["id"]),
                            "pending_id": row["pending_item_id"],
                        }
                    ),
                    f"approval:{row['id']}:{notification_type}",
                    event_id,
                    actor.correlation_id,
                ),
            )


def get_approval_repository() -> Generator[ApprovalRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ApiError(503, "database_not_configured", "Aprovações indisponíveis")
    yield ApprovalRepository(database_url)


ApprovalRepo = Annotated[ApprovalRepository, Depends(get_approval_repository)]


@router.get(
    "/pending-items/{pending_id}/approval",
    response_model=ApprovalResponse,
    responses=ERROR_RESPONSES,
)
def get_approval(
    pending_id: int,
    actor: Annotated[ActorContext, Depends(require_permission("approval.read"))],
    repository: ApprovalRepo,
) -> ApprovalResponse:
    item = repository.get_for_pending(pending_id, actor)
    if item is None:
        raise ApiError(404, "approval_not_found", "Solicitação não encontrada")
    return ApprovalResponse.model_validate(item)


@router.post(
    "/pending-items/{pending_id}/approval",
    response_model=ApprovalResponse,
    status_code=201,
    responses=ERROR_RESPONSES,
)
def create_approval(
    pending_id: int,
    body: CreateApprovalRequest,
    actor: Annotated[ActorContext, Depends(require_permission("approval.submit"))],
    repository: ApprovalRepo,
) -> ApprovalResponse:
    item = repository.create(pending_id, body.justification, actor)
    if item is None:
        raise ApiError(404, "pending_item_not_found", "Pendência não encontrada")
    return ApprovalResponse.model_validate(item)


@router.post(
    "/approvals/{request_id}/assign",
    response_model=ApprovalResponse,
    responses=ERROR_RESPONSES,
)
def assign_approval(
    request_id: UUID,
    body: AssignmentRequest,
    actor: Annotated[ActorContext, Depends(require_permission("approval.assign"))],
    repository: ApprovalRepo,
) -> ApprovalResponse:
    return ApprovalResponse.model_validate(
        repository.assign(
            request_id, body.assignee_user_id, body.version, body.justification, actor
        )
    )


@router.post(
    "/approvals/{request_id}/resubmit",
    response_model=ApprovalResponse,
    responses=ERROR_RESPONSES,
)
def resubmit_approval(
    request_id: UUID,
    body: DecisionRequest,
    actor: Annotated[ActorContext, Depends(require_permission("approval.submit"))],
    repository: ApprovalRepo,
) -> ApprovalResponse:
    return ApprovalResponse.model_validate(
        repository.resubmit(request_id, body.version, body.justification, actor)
    )


def _decision_route(action: Literal["approved", "rejected", "returned"]):
    def endpoint(
        request_id: UUID,
        body: DecisionRequest,
        actor: Annotated[ActorContext, Depends(require_permission("approval.decide"))],
        repository: ApprovalRepo,
    ) -> ApprovalResponse:
        return ApprovalResponse.model_validate(
            repository.decide(
                request_id,
                action,
                body.version,
                body.justification,
                body.consent,
                actor,
            )
        )

    endpoint.__name__ = f"{action}_approval"
    return endpoint


router.post(
    "/approvals/{request_id}/approve",
    response_model=ApprovalResponse,
    responses=ERROR_RESPONSES,
)(_decision_route("approved"))
router.post(
    "/approvals/{request_id}/reject",
    response_model=ApprovalResponse,
    responses=ERROR_RESPONSES,
)(_decision_route("rejected"))
router.post(
    "/approvals/{request_id}/return",
    response_model=ApprovalResponse,
    responses=ERROR_RESPONSES,
)(_decision_route("returned"))
