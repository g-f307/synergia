from __future__ import annotations

import logging
import sys
from pathlib import Path
from statistics import median
from time import perf_counter

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.access_control import GroupCreate, GroupUpdate, ReasonRequest, RoleCreate
from app.auth.security import PasswordVerifier
from app.main import app
from app.users import UserCreate, UserUpdate

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from security_matrix import (  # noqa: E402
    PUBLIC,
    ROLE_PERMISSIONS,
    ROLES,
    load_cases,
    openapi_operations,
    render_report,
    validate,
)

pytestmark = pytest.mark.security
CASES = load_cases()


def test_every_private_openapi_operation_is_in_the_executable_matrix() -> None:
    operations, secured = openapi_operations()
    documented = {(case.method, case.path) for case in CASES}

    assert validate(CASES) == []
    assert operations - PUBLIC == documented
    assert documented <= secured


@pytest.mark.parametrize(
    ("case", "role"),
    [(case, role) for case in CASES for role in ROLES],
    ids=[f"{case.method}-{case.path}-{role}" for case in CASES for role in ROLES],
)
def test_role_route_method_matrix(case, role) -> None:
    expected = case.permission in ROLE_PERMISSIONS[role]

    assert (role in case.allowed_roles) is expected


def test_committed_security_report_matches_the_executable_matrix() -> None:
    report = ROOT / "docs" / "security-test-report.md"

    assert report.read_text(encoding="utf-8") == render_report(CASES)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            UserCreate,
            {
                "display_name": "Synthetic User",
                "emails": [{"email": "security@example.invalid"}],
                "reason": "security regression",
                "is_admin": True,
            },
        ),
        (
            UserUpdate,
            {
                "version": 1,
                "display_name": "Synthetic User",
                "reason": "security regression",
                "status": "active",
            },
        ),
        (
            GroupCreate,
            {
                "group_name": "synthetic-group",
                "reason": "security regression",
                "permissions": ["access.admin"],
            },
        ),
        (
            GroupUpdate,
            {
                "version": 1,
                "group_name": "synthetic-group",
                "reason": "security regression",
                "is_active": True,
            },
        ),
        (
            RoleCreate,
            {
                "role_key": "synthetic-role",
                "reason": "security regression",
                "organization_scope": "all",
            },
        ),
        (
            ReasonRequest,
            {
                "reason": "security regression",
                "approved_by": "self",
            },
        ),
    ],
)
def test_administrative_contracts_reject_mass_assignment(model, payload) -> None:
    with pytest.raises(ValidationError) as captured:
        model.model_validate(payload)

    assert any(error["type"] == "extra_forbidden" for error in captured.value.errors())


@pytest.mark.real_authorization
def test_invalid_bearer_is_not_echoed_in_response_or_logs(monkeypatch, caplog) -> None:
    secret = "synthetic.invalid.bearer.must-not-leak"
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv(
        "AUTH_JWT_SIGNING_KEY", "security-regression-key-with-at-least-32-bytes"
    )
    monkeypatch.setenv("AUTH_JWT_ISSUER", "synergia-security-test")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "synergia-security-api-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused.invalid/security")

    with caplog.at_level(logging.DEBUG), TestClient(app) as client:
        response = client.get(
            "/indicators", headers={"Authorization": f"Bearer {secret}"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_access_token"
    assert secret not in response.text
    assert secret not in caplog.text


def test_unknown_and_known_credentials_have_coarsely_uniform_cost() -> None:
    hasher = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    verifier = PasswordVerifier(hasher)
    known_hash = hasher.hash("synthetic-correct-password")

    def duration(password_hash: str | None) -> float:
        started = perf_counter()
        assert verifier.verify(password_hash, "synthetic-wrong-password") is False
        return perf_counter() - started

    unknown = median(duration(None) for _ in range(3))
    known = median(duration(known_hash) for _ in range(3))

    assert max(unknown, known) / min(unknown, known) < 4
