from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import Request

from app.auth.config import AuthConfig
from app.auth.security import TokenCodec
from app.authorization import (
    ActorContext,
    get_actor_context,
    get_authorization_repository,
)
from app.main import app

TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
TEST_TOKEN_ID = UUID("33333333-3333-4333-8333-333333333333")
TEST_ORGANIZATION_ID = UUID("44444444-4444-4444-8444-444444444444")
TEST_CORRELATION_ID = UUID("55555555-5555-4555-8555-555555555555")

ALL_PERMISSIONS = {
    key: frozenset({TEST_ORGANIZATION_ID})
    for key in (
        "dashboard.read",
        "execution.read",
        "business.read",
        "pending.read",
        "import.create",
        "import.read",
        "artifact.read",
        "execution.reprocess",
        "audit.read",
        "artifact.export",
        "report.export",
        "access.admin",
        "session.revoke.any",
        "session.revoke.own",
    )
}
ALL_PERMISSIONS["access.admin"] = frozenset({None})
ALL_PERMISSIONS["session.revoke.own"] = frozenset({None})


class PermissiveAuthorizationRepository:
    def audit_denial(self, *args, **kwargs) -> None:
        return None

    def list_active_organizations(self, scopes) -> list[dict]:
        if not scopes:
            return []
        return [
            {
                "id": TEST_ORGANIZATION_ID,
                "organization_code": "org-001",
                "display_name": "Organization 001",
            }
        ]

    def execution_organization(self, execution_id: str) -> UUID:
        return TEST_ORGANIZATION_ID

    def resource_organization(self, resource: str, identifier: str) -> UUID:
        return TEST_ORGANIZATION_ID

    def lot_organization(
        self, lot_number: str, workorder_number: str | None = None
    ) -> None:
        return None


@pytest.fixture(autouse=True)
def synthetic_authorization(request):
    if request.node.get_closest_marker("real_authorization") is not None:
        yield
        return
    previous_actor = app.dependency_overrides.get(get_actor_context)
    previous_repository = app.dependency_overrides.get(get_authorization_repository)
    def actor_context(http_request: Request) -> ActorContext:
        supplied = http_request.headers.get("X-Actor-Id")
        user_id = UUID(supplied) if supplied else TEST_USER_ID
        session_id = TEST_SESSION_ID
        token_id = TEST_TOKEN_ID
        authorization = http_request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            try:
                claims = TokenCodec(AuthConfig.from_env()).decode_access(
                    authorization.split(" ", 1)[1]
                )
                user_id = claims.user_id
                session_id = claims.session_id
                token_id = claims.token_id
            except Exception:
                pass
        return ActorContext(
            user_id=user_id,
            session_id=session_id,
            token_id=token_id,
            permissions=ALL_PERMISSIONS,
            correlation_id=TEST_CORRELATION_ID,
        )

    app.dependency_overrides[get_actor_context] = actor_context
    app.dependency_overrides[get_authorization_repository] = (
        PermissiveAuthorizationRepository
    )
    try:
        yield
    finally:
        if previous_actor is None:
            app.dependency_overrides.pop(get_actor_context, None)
        else:
            app.dependency_overrides[get_actor_context] = previous_actor
        if previous_repository is None:
            app.dependency_overrides.pop(get_authorization_repository, None)
        else:
            app.dependency_overrides[get_authorization_repository] = previous_repository
