from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.authorization import get_actor_context, get_authorization_repository
from app.errors import ApiError
from app.main import app
from app.users import UserCreate, UserStateChange, UserUpdate, get_user_repository

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)
ACTOR_ID = UUID("00000000-0000-0000-0000-000000000001")
HEADERS = {"X-Actor-Id": str(ACTOR_ID)}


class MemoryUserRepository:
    def __init__(self) -> None:
        self.authorized = True
        self.audit: list[dict] = []
        self.users: dict[UUID, dict] = {}

    def authorize(self, actor_id: UUID) -> None:
        if not self.authorized or actor_id != ACTOR_ID:
            raise ApiError(403, "access_denied", "Acao administrativa nao autorizada")

    def create(self, payload: UserCreate, actor_id: UUID) -> dict:
        existing = {
            email["email"] for user in self.users.values() for email in user["emails"]
        }
        if any(item.email in existing for item in payload.emails):
            raise ApiError(
                409,
                "user_data_conflict",
                "Os dados informados conflitam com um usuario existente",
            )
        user_id = uuid4()
        user = {
            "id": user_id,
            "status": payload.status,
            "display_name": payload.display_name,
            "emails": [item.model_dump() for item in payload.emails],
            "version": 1,
            "created_at": NOW,
            "updated_at": NOW,
            "deactivated_at": None,
            "last_login_at": None,
        }
        self.users[user_id] = user
        self.audit.append(
            {"event": "user.admin_created", "actor": actor_id, "subject": user_id}
        )
        return deepcopy(user)

    def get(self, user_id: UUID) -> dict | None:
        return deepcopy(self.users.get(user_id))

    def list(
        self,
        *,
        status_filter,
        group,
        role,
        organization,
        name,
        email,
        page,
        page_size,
    ) -> tuple[list[dict], int]:
        del group, role, organization
        items = sorted(
            self.users.values(), key=lambda item: (item["created_at"], item["id"])
        )
        items = [
            item
            for item in items
            if (status_filter is None or item["status"] == status_filter)
            and (name is None or name.lower() in item["display_name"].lower())
            and (
                email is None
                or email.strip().lower() in {entry["email"] for entry in item["emails"]}
            )
        ]
        total = len(items)
        start = (page - 1) * page_size
        return deepcopy(items[start : start + page_size]), total

    def update(self, user_id: UUID, payload: UserUpdate, actor_id: UUID) -> dict:
        user = self.users.get(user_id)
        if user is None:
            raise ApiError(404, "user_not_found", "Usuario nao encontrado")
        if user["version"] != payload.version:
            raise ApiError(
                409,
                "user_version_conflict",
                "O usuario foi alterado por outra operacao",
            )
        if payload.display_name is not None:
            user["display_name"] = payload.display_name
        if payload.emails is not None:
            user["emails"] = [item.model_dump() for item in payload.emails]
        user["version"] += 1
        self.audit.append(
            {"event": "user.admin_updated", "actor": actor_id, "subject": user_id}
        )
        return deepcopy(user)

    def change_status(
        self,
        user_id: UUID,
        target_status,
        action,
        payload: UserStateChange,
        actor_id: UUID,
    ) -> dict:
        user = self.users.get(user_id)
        if user is None:
            raise ApiError(404, "user_not_found", "Usuario nao encontrado")
        if user["version"] != payload.version:
            raise ApiError(
                409,
                "user_version_conflict",
                "O usuario foi alterado por outra operacao",
            )
        if user.get("last_admin") and target_status in {"inactive", "blocked"}:
            raise ApiError(
                409,
                "last_active_admin",
                "O ultimo administrador ativo nao pode ser alterado",
            )
        user["status"] = target_status
        user["deactivated_at"] = NOW if target_status == "inactive" else None
        user["version"] += 1
        self.audit.append(
            {
                "event": f"user.admin_{action}",
                "actor": actor_id,
                "subject": user_id,
            }
        )
        return deepcopy(user)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv("SYNERGIA_TRUSTED_ACTOR_HEADER_ENABLED", "true")
    repository = MemoryUserRepository()
    app.dependency_overrides[get_user_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, repository
    app.dependency_overrides.clear()


def _create(client: TestClient, email: str = "Admin@Example.Invalid"):
    return client.post(
        "/admin/users",
        headers=HEADERS,
        json={
            "display_name": "Synthetic Admin",
            "status": "active",
            "emails": [{"email": email, "is_primary": True}],
            "reason": "provisionamento sintetico",
        },
    )


def test_creates_normalizes_and_gets_user_without_sensitive_data(api) -> None:
    client, _repository = api
    created = _create(client)
    assert created.status_code == 201
    body = created.json()
    assert body["emails"][0]["email"] == "admin@example.invalid"
    assert not {"local_password_hash", "token", "token_hash"} & body.keys()

    found = client.get(f"/admin/users/{body['id']}", headers=HEADERS)
    assert found.status_code == 200
    assert found.json() == body


@pytest.mark.parametrize(
    "payload_path,payload_value",
    [("email", "invalid"), ("display_name", "   ")],
)
def test_rejects_invalid_creation(api, payload_path, payload_value) -> None:
    client, _repository = api
    payload = {
        "display_name": "Synthetic User",
        "emails": [{"email": "valid@example.invalid"}],
        "reason": "synthetic reason",
    }
    if payload_path == "email":
        payload["emails"][0]["email"] = payload_value
    else:
        payload[payload_path] = payload_value
    response = client.post("/admin/users", headers=HEADERS, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_rejects_inactive_state_during_creation(api) -> None:
    client, repository = api
    response = client.post(
        "/admin/users",
        headers=HEADERS,
        json={
            "display_name": "Inactive created user",
            "status": "inactive",
            "emails": [{"email": "inactive-review@example.invalid"}],
            "reason": "review scenario",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
    assert repository.users == {}


def test_rejects_mass_assignment_in_admin_http_contract(api) -> None:
    client, repository = api
    response = client.post(
        "/admin/users",
        headers=HEADERS,
        json={
            "display_name": "Synthetic Escalation",
            "emails": [{"email": "mass-assignment@example.invalid"}],
            "reason": "security regression",
            "roles": ["admin"],
            "local_password_hash": "must-never-be-accepted",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
    assert repository.users == {}


def test_rejects_duplicate_email_without_enumerating_owner(api) -> None:
    client, _repository = api
    assert _create(client).status_code == 201
    duplicate = _create(client, " ADMIN@example.invalid ")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "user_data_conflict"
    assert "id" not in duplicate.json()["error"]["details"]


def test_returns_same_safe_not_found_for_unknown_user(api) -> None:
    client, _repository = api
    response = client.get(f"/admin/users/{uuid4()}", headers=HEADERS)
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "user_not_found",
        "message": "Usuario nao encontrado",
        "details": {},
    }


def test_lists_with_pagination_filters_and_stable_sort(api) -> None:
    client, _repository = api
    first = _create(client, "first@example.invalid").json()
    second = _create(client, "second@example.invalid").json()
    page = client.get(
        "/admin/users?page=1&page_size=1&status=active&name=Synthetic",
        headers=HEADERS,
    )
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["pages"] == 2
    assert page.json()["sort"] == "created_at,id"
    assert page.json()["items"][0]["id"] == min(first["id"], second["id"])


def test_updates_with_optimistic_version_and_audit(api) -> None:
    client, repository = api
    user = _create(client).json()
    updated = client.patch(
        f"/admin/users/{user['id']}",
        headers=HEADERS,
        json={
            "version": 1,
            "display_name": "Updated Name",
            "emails": [{"email": "updated@example.invalid", "is_primary": True}],
            "reason": "correcao administrativa",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    conflict = client.patch(
        f"/admin/users/{user['id']}",
        headers=HEADERS,
        json={"version": 1, "display_name": "Stale", "reason": "stale update"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "user_version_conflict"
    assert repository.audit[-1]["event"] == "user.admin_updated"


def test_deactivates_reactivates_blocks_and_revokes_logically(api) -> None:
    client, repository = api
    user = _create(client).json()
    version = user["version"]
    for action, expected in [
        ("deactivate", "inactive"),
        ("reactivate", "active"),
        ("block", "blocked"),
        ("unblock", "active"),
    ]:
        response = client.post(
            f"/admin/users/{user['id']}/{action}",
            headers=HEADERS,
            json={"version": version, "reason": f"synthetic {action}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == expected
        version = response.json()["version"]
    assert len(repository.audit) == 5


def test_protects_last_active_administrator(api) -> None:
    client, repository = api
    user = _create(client).json()
    repository.users[UUID(user["id"])]["last_admin"] = True
    response = client.post(
        f"/admin/users/{user['id']}/deactivate",
        headers=HEADERS,
        json={"version": 1, "reason": "invalid admin removal"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_active_admin"


def test_rejects_physical_delete_and_unauthorized_access(api) -> None:
    client, repository = api
    user = _create(client).json()
    deletion = client.delete(f"/admin/users/{user['id']}", headers=HEADERS)
    assert deletion.status_code == 409
    assert deletion.json()["error"]["code"] == "physical_deletion_forbidden"

    repository.authorized = False
    denied = client.get(f"/admin/users/{user['id']}", headers=HEADERS)
    assert denied.status_code == 403
    missing_actor = client.get(f"/admin/users/{user['id']}")
    assert missing_actor.status_code == 403


def test_trusted_actor_header_does_not_replace_bearer_authentication(api) -> None:
    client, _repository = api
    app.dependency_overrides.pop(get_actor_context, None)
    app.dependency_overrides[get_authorization_repository] = lambda: object()
    response = client.get(f"/admin/users/{uuid4()}", headers=HEADERS)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_access_token"


def test_openapi_documents_filters_errors_and_models(api) -> None:
    client, _repository = api
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/admin/users"]["get"]
    parameters = {item["name"] for item in operation["parameters"]}
    assert {"status", "group", "role", "organization", "name", "email"} <= parameters
    assert {"403", "409", "422"} <= operation["responses"].keys()
