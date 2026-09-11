from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.auth.config import configured_allowed_origins
from app.http_security import API_CSP, HttpSecurityConfig, HttpSecurityMiddleware
from app.main import app, create_app

EXPECTED_HEADERS = {
    "content-security-policy": API_CSP,
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-resource-policy": "same-site",
}


def _assert_baseline(response) -> None:
    for name, value in EXPECTED_HEADERS.items():
        assert response.headers[name] == value


def test_headers_cover_success_and_error_without_shared_cache() -> None:
    client = TestClient(app)

    success = client.get("/health")
    error = client.get("/route-that-does-not-exist")

    _assert_baseline(success)
    _assert_baseline(error)
    assert success.headers["cache-control"] == "no-cache"
    assert error.headers["cache-control"] == "no-store"
    assert "server" not in error.json().get("error", {}).get("details", {})


def test_unhandled_server_error_also_receives_complete_baseline() -> None:
    application = create_app()

    @application.get("/boom")
    def boom() -> None:
        raise RuntimeError("internal database password must never be serialized")

    response = TestClient(application, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    _assert_baseline(response)
    assert response.headers["cache-control"] == "no-store"
    assert "password" not in response.text


def test_allowed_origin_and_valid_preflight_are_explicit() -> None:
    client = TestClient(app)
    origin = "http://localhost:4200"

    simple = client.get("/health", headers={"Origin": origin})
    preflight = client.options(
        "/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-correlation-id",
        },
    )

    assert simple.headers["access-control-allow-origin"] == origin
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert preflight.headers["access-control-allow-credentials"] == "true"
    _assert_baseline(preflight)


def test_blocked_origin_and_invalid_preflight_receive_no_cors_access() -> None:
    client = TestClient(app)
    origin = "https://attacker.invalid"

    simple = client.get("/health", headers={"Origin": origin})
    preflight = client.options(
        "/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "TRACE",
            "Access-Control-Request-Headers": "x-unapproved-header",
        },
    )

    assert "access-control-allow-origin" not in simple.headers
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers
    _assert_baseline(preflight)


def test_wildcard_origin_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", "*")

    try:
        configured_allowed_origins()
    except ValueError as exc:
        assert "curingas" in str(exc)
    else:
        raise AssertionError("wildcard origin should not be accepted with credentials")


def test_hsts_is_only_emitted_by_production_baseline() -> None:
    inner = FastAPI()

    @inner.get("/")
    def root() -> dict[str, bool]:
        return {"ok": True}

    development = TestClient(
        HttpSecurityMiddleware(inner, HttpSecurityConfig("development"))
    ).get("/")
    production = TestClient(
        HttpSecurityMiddleware(inner, HttpSecurityConfig("production"))
    ).get("/")

    assert "strict-transport-security" not in development.headers
    assert production.headers["strict-transport-security"].startswith("max-age=")


def test_download_with_untrusted_extension_cannot_be_sniffed_or_cached() -> None:
    inner = FastAPI()

    @inner.get("/download")
    def download() -> Response:
        return Response(
            b"<script>alert(1)</script>",
            media_type="application/octet-stream",
            headers={"Content-Disposition": 'attachment; filename="report.html"'},
        )

    response = TestClient(
        HttpSecurityMiddleware(inner, HttpSecurityConfig("test"))
    ).get("/download")

    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
