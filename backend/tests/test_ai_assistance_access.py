from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.ai_assistance_access import require_assistance_permission
from app.authorization import (
    ActorContext,
    get_actor_context,
    get_authorization_repository,
)
from app.errors import install_error_handlers
from app.main import create_app

ORG = uuid4()
OTHER_ORG = uuid4()
pytestmark = pytest.mark.security


def actor(permissions):
    return ActorContext(uuid4(), uuid4(), uuid4(), permissions, uuid4())


class Repository:
    def __init__(self, organization):
        self.organization = organization
        self.denials = []

    def execution_organization(self, _execution):
        return self.organization

    def audit_denial(self, *args, **kwargs):
        self.denials.append((args, kwargs))


@pytest.mark.parametrize("action", ["read", "generate"])
@pytest.mark.parametrize(
    "execution_scope,ai_scope,organization,expected",
    [
        ([], [], ORG, 403),
        ([ORG], [], ORG, 403),
        ([], [ORG], ORG, 403),
        ([ORG], [ORG], ORG, 200),
        ([ORG], [OTHER_ORG], ORG, 404),
        ([OTHER_ORG], [ORG], ORG, 404),
        ([ORG], [ORG], OTHER_ORG, 404),
        ([ORG], [ORG], None, 404),
        ([None], [ORG], ORG, 200),
        ([ORG], [None], ORG, 200),
        ([None], [None], ORG, 200),
    ],
)
def test_server_guard_intersects_both_organization_scopes(
    action,
    execution_scope,
    ai_scope,
    organization,
    expected,
):
    application = FastAPI()
    install_error_handlers(application)

    @application.get("/executions/{execution_id}/test")
    def guarded(_actor=Depends(require_assistance_permission(action))):
        return {"ok": True}

    repository = Repository(organization)
    application.dependency_overrides[get_authorization_repository] = lambda: repository
    application.dependency_overrides[get_actor_context] = lambda: actor(
        {
            "execution.read": frozenset(execution_scope),
            f"ai.assistance.{action}": frozenset(ai_scope),
        }
    )
    with TestClient(application) as client:
        response = client.get(f"/executions/{uuid4()}/test")
    assert response.status_code == expected
    if expected != 200:
        assert repository.denials
        assert str(organization) not in response.text


@pytest.mark.parametrize(
    "role,can_assist",
    [
        ("admin", False),
        ("gestor", True),
        ("analista", True),
        ("operador", False),
        ("consulta", False),
    ],
)
def test_role_capability_and_disabled_mode(monkeypatch, role, can_assist):
    permissions = {} if role == "admin" else {"execution.read": frozenset({ORG})}
    if can_assist:
        permissions.update(
            {f"ai.assistance.{key}": frozenset({ORG}) for key in ("read", "generate")}
        )
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENABLED", "false")
    application = create_app()
    application.dependency_overrides[get_actor_context] = lambda: actor(permissions)
    with TestClient(application) as client:
        response = client.get("/me/ai-assistance-capability")
        assert response.status_code == (200 if can_assist else 403)
        if can_assist:
            assert response.json() == {
                "enabled": False,
                "read": False,
                "generate": False,
            }
        assert client.get("/health/live").status_code == 200


@pytest.mark.parametrize("action", ["read", "generate"])
def test_capability_permissions_are_independent(monkeypatch, action):
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENABLED", "true")
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENDPOINT", "http://127.0.0.1:11434")
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_MODEL", "synthetic:1")
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_DIGEST", "sha256:" + "a" * 64)
    application = create_app()
    permissions = {
        "execution.read": frozenset({ORG}),
        f"ai.assistance.{action}": frozenset({ORG}),
    }
    application.dependency_overrides[get_actor_context] = lambda: actor(permissions)
    with TestClient(application) as client:
        response = client.get("/me/ai-assistance-capability")
        assert response.json() == {
            "enabled": True,
            "read": action == "read",
            "generate": action == "generate",
        }


def test_capability_disjoint_scopes_are_denied():
    application = create_app()
    application.dependency_overrides[get_actor_context] = lambda: actor(
        {
            "execution.read": frozenset({ORG}),
            "ai.assistance.read": frozenset({OTHER_ORG}),
        }
    )
    with TestClient(application) as client:
        assert client.get("/me/ai-assistance-capability").status_code == 403


def test_capability_requires_authentication():
    with TestClient(create_app()) as client:
        assert client.get("/me/ai-assistance-capability").status_code == 401
