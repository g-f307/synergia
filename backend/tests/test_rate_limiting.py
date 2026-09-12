from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.auth.security import AccessClaims
from app.main import create_app
from app.rate_limiting import (
    RateLimitMiddleware,
    classify_operation,
    client_origin,
    policies_from_env,
)


def test_operation_matrix_covers_every_critical_contract() -> None:
    cases = {
        ("POST", "/auth/login"): "login",
        ("POST", "/auth/refresh"): "refresh",
        ("POST", "/imports"): "upload",
        ("GET", "/search"): "search",
        ("POST", "/executions/ex-1/reprocess"): "reprocess",
        ("POST", "/reports"): "report_generate",
        ("POST", "/reports/id/versions"): "report_generate",
        ("GET", "/reports/id/versions/2/export"): "report_export",
        ("POST", "/pending-items/1/approval"): "decision",
        ("POST", "/approvals/id/approve"): "decision",
        ("POST", "/approvals/id/reject"): "decision",
        ("POST", "/approvals/id/return"): "decision",
        ("POST", "/approvals/id/assign"): "decision",
        ("POST", "/approvals/id/resubmit"): "decision",
    }
    for request, expected in cases.items():
        assert classify_operation(*request) == expected


def test_invalid_configuration_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_LOGIN_LIMIT", "0")
    with pytest.raises(ValueError, match="RATE_LIMIT_LOGIN_LIMIT"):
        policies_from_env()


def test_forwarded_origin_cannot_be_spoofed_through_a_trusted_proxy(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    scope = {"client": ("10.0.0.2", 443)}
    headers = Headers({"X-Forwarded-For": "198.51.100.8, 203.0.113.9"})
    assert client_origin(scope, headers) == "203.0.113.9"

    untrusted_scope = {"client": ("192.0.2.15", 443)}
    assert client_origin(untrusted_scope, headers) == "192.0.2.15"


def test_429_contract_is_stable_and_hides_sensitive_data(monkeypatch) -> None:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.post("/auth/login")
    def login() -> dict[str, bool]:
        return {"ok": True}

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("RATE_LIMIT_KEY_SECRET", "x" * 32)
    monkeypatch.setenv("RATE_LIMIT_LOGIN_LIMIT", "1")
    with patch(
        "app.rate_limiting.PostgresRateLimiter.consume",
        side_effect=[None, None, 17, 17],
    ):
        client = TestClient(app)
        payload = {"email": "secret@example.invalid", "password": "secret"}
        first = client.post("/auth/login", json=payload)
        limited = client.post("/auth/login", json=payload)

    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "17"
    assert limited.json()["error"]["code"] == "rate_limit_exceeded"
    assert limited.json()["error"]["details"] == {"retry_after_seconds": 17}
    assert "secret" not in limited.text


def test_429_keeps_cors_security_and_correlation_headers(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("RATE_LIMIT_KEY_SECRET", "x" * 32)
    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", "http://localhost:4200")
    with patch(
        "app.rate_limiting.PostgresRateLimiter.consume",
        side_effect=[11, 11],
    ):
        response = TestClient(create_app()).post(
            "/auth/login",
            headers={"Origin": "http://localhost:4200"},
            json={"email": "person@example.invalid", "password": "not-exposed"},
        )
    assert response.status_code == 429
    assert response.headers["access-control-allow-origin"] == "http://localhost:4200"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-correlation-id"]


def test_store_failure_is_closed_for_mutation_and_search(monkeypatch) -> None:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.post("/imports")
    def upload() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/search")
    def search() -> dict[str, bool]:
        return {"ok": True}

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("RATE_LIMIT_KEY_SECRET", "x" * 32)
    with patch(
        "app.rate_limiting.PostgresRateLimiter.consume",
        side_effect=psycopg.OperationalError("unavailable"),
    ):
        client = TestClient(app)
        assert client.post("/imports").status_code == 503
        assert client.get("/search?type=serial&query=x").status_code == 503


def test_organization_quota_uses_only_authorized_scope(monkeypatch) -> None:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/search")
    def search() -> dict[str, bool]:
        return {"ok": True}

    organization_a = uuid4()
    organization_b = uuid4()
    arbitrary = uuid4()
    claims = AccessClaims(uuid4(), uuid4(), uuid4())
    consumed: list[tuple[str, str]] = []

    def consume(_self, _policy, dimension, value, *_args):
        consumed.append((dimension, value))
        return None

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("RATE_LIMIT_KEY_SECRET", "x" * 32)
    monkeypatch.setenv("AUTH_JWT_SIGNING_KEY", "x" * 32)
    monkeypatch.setenv("AUTH_JWT_ISSUER", "rate-limit-test")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "rate-limit-test")
    headers = {"Authorization": "Bearer valid-test-token"}
    with (
        patch("app.rate_limiting.TokenCodec.decode_access", return_value=claims),
        patch(
            "app.rate_limiting.AuthorizationRepository.resolve",
            return_value={
                "business.read": frozenset({organization_a, organization_b})
            },
        ),
        patch("app.rate_limiting.PostgresRateLimiter.consume", new=consume),
    ):
        client = TestClient(app)
        assert client.get(
            f"/search?organization_id={organization_a}", headers=headers
        ).status_code == 200
        assert client.get(
            f"/search?organization_id={organization_b}", headers=headers
        ).status_code == 200

    organization_values = [
        value for dimension, value in consumed if dimension == "organization"
    ]
    assert organization_values == [str(organization_a), str(organization_b)]

    consumed.clear()
    with (
        patch("app.rate_limiting.TokenCodec.decode_access", return_value=claims),
        patch(
            "app.rate_limiting.AuthorizationRepository.resolve",
            return_value={"business.read": frozenset({organization_a})},
        ),
        patch("app.rate_limiting.PostgresRateLimiter.consume", new=consume),
    ):
        client = TestClient(app)
        response_b = client.get(
            f"/search?organization_id={organization_b}", headers=headers
        )
        response_arbitrary = client.get(
            f"/search?organization_id={arbitrary}", headers=headers
        )
        response_a = client.get(
            f"/search?organization_id={organization_a}", headers=headers
        )
    assert response_b.status_code == 200
    assert response_arbitrary.status_code == 200
    assert response_a.status_code == 200
    assert [value for dimension, value in consumed if dimension == "organization"] == [
        str(organization_a)
    ]


def test_invalid_trusted_proxy_cidr_fails_closed_with_stable_contract(
    monkeypatch,
) -> None:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/search")
    def search() -> dict[str, bool]:
        return {"ok": True}

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("RATE_LIMIT_KEY_SECRET", "x" * 32)
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "not-a-cidr")
    response = TestClient(app, client=("127.0.0.1", 50000)).get(
        "/search?type=serial&query=x"
    )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json()["error"] == {
        "code": "rate_limit_unavailable",
        "message": "Limite temporario de requisicoes atingido",
        "details": {"retry_after_seconds": 1},
    }
