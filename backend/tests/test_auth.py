from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from fastapi.testclient import TestClient

from app.auth.config import AuthConfig
from app.auth.models import CredentialRecord, RefreshResult, SessionResult
from app.auth.routes import get_auth_config, get_auth_repository, get_auth_service
from app.auth.security import TokenCodec, sha256_token
from app.auth.service import AuthService
from app.main import app

NOW = datetime.now(UTC).replace(microsecond=0)
USER_ID = UUID("11111111-1111-1111-1111-111111111111")
SESSION_ID = UUID("22222222-2222-2222-2222-222222222222")
KEY = "synthetic-test-signing-key-with-at-least-32-bytes"


def config(**changes) -> AuthConfig:
    values = {
        "environment": "test",
        "local_auth_enabled": True,
        "signing_key": KEY,
        "issuer": "synergia-test",
        "audience": "synergia-api-test",
        "cookie_secure": False,
    }
    values.update(changes)
    return AuthConfig(**values)


class FakePasswords:
    def verify(self, password_hash, password):
        return password_hash == "$argon2id$synthetic" and password == "correct-password"

    def updated_hash(self, _password_hash, _password):
        return None


class FakeRepository:
    def __init__(self) -> None:
        self.credentials = CredentialRecord(USER_ID, "active", "$argon2id$synthetic")
        self.retry_after = None
        self.failed = []
        self.refresh_result = RefreshResult(status="invalid")
        self.revoked = []

    def begin_login_attempt(self, *_args):
        if self.retry_after:
            return None, self.retry_after
        return 7, None

    def credentials_for_email(self, _email):
        return self.credentials

    def fail_login(self, attempt_id, identifier_hash, reason):
        self.failed.append((attempt_id, identifier_hash, reason))

    def create_session(self, *_args):
        return SessionResult(
            USER_ID,
            SESSION_ID,
            "synthetic-refresh-token",
            NOW + timedelta(hours=8),
        )

    def rotate_refresh(self, token_hash, *_args):
        self.received_hash = token_hash
        return self.refresh_result

    def revoke_session(self, user_id, session_id, _now):
        self.revoked.append((user_id, session_id))
        return 1

    def revoke_all_sessions(self, user_id, _now):
        self.revoked.append((user_id, None))
        return 3


def service(repository=None, **config_changes) -> AuthService:
    selected = repository or FakeRepository()
    selected_config = config(**config_changes)
    codec = TokenCodec(selected_config, lambda: NOW)
    return AuthService(
        selected,
        selected_config,
        passwords=FakePasswords(),
        tokens=codec,
        clock=lambda: NOW,
    )


def test_access_token_contains_and_validates_required_claims() -> None:
    codec = TokenCodec(config(), lambda: NOW)
    token, expires_in = codec.issue_access(USER_ID, SESSION_ID)

    claims = codec.decode_access(token)
    unverified = jwt.decode(token, options={"verify_signature": False})

    assert claims.user_id == USER_ID
    assert claims.session_id == SESSION_ID
    assert expires_in == 900
    assert set(unverified) == {
        "iss", "aud", "sub", "sid", "jti", "iat", "nbf", "exp", "typ"
    }


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"iss": "wrong"}, jwt.InvalidIssuerError),
        ({"aud": "wrong"}, jwt.InvalidAudienceError),
        ({"typ": "refresh"}, jwt.InvalidTokenError),
    ],
)
def test_access_token_rejects_invalid_claims(mutation, error) -> None:
    payload = {
        "iss": "synergia-test",
        "aud": "synergia-api-test",
        "sub": str(USER_ID),
        "sid": str(SESSION_ID),
        "jti": "33333333-3333-3333-3333-333333333333",
        "iat": NOW,
        "nbf": NOW,
        "exp": NOW + timedelta(minutes=15),
        "typ": "access",
    }
    payload.update(mutation)
    token = jwt.encode(payload, KEY, algorithm="HS256")

    with pytest.raises(error):
        TokenCodec(config(), lambda: NOW).decode_access(token)


def test_access_token_rejects_tampering_algorithm_and_missing_claim() -> None:
    codec = TokenCodec(config(), lambda: NOW)
    valid, _ = codec.issue_access(USER_ID, SESSION_ID)
    tampered = valid[:-1] + ("a" if valid[-1] != "a" else "b")
    wrong_algorithm = jwt.encode(
        {
            "iss": "synergia-test", "aud": "synergia-api-test",
            "sub": str(USER_ID), "sid": str(SESSION_ID),
            "jti": "33333333-3333-3333-3333-333333333333",
            "iat": NOW, "nbf": NOW, "exp": NOW + timedelta(minutes=15),
            "typ": "access",
        },
        KEY,
        algorithm="HS384",
    )
    missing_jti = jwt.encode(
        {
            "iss": "synergia-test", "aud": "synergia-api-test",
            "sub": str(USER_ID), "sid": str(SESSION_ID),
            "iat": NOW, "nbf": NOW, "exp": NOW + timedelta(minutes=15),
            "typ": "access",
        },
        KEY,
        algorithm="HS256",
    )

    for token in (tampered, wrong_algorithm, missing_jti):
        with pytest.raises(jwt.InvalidTokenError):
            codec.decode_access(token)


def test_access_token_expiration_uses_injected_clock() -> None:
    issued_at = NOW - timedelta(minutes=16)
    issuer = TokenCodec(config(), lambda: issued_at)
    token, _ = issuer.issue_access(USER_ID, SESSION_ID)

    with pytest.raises(jwt.ExpiredSignatureError):
        TokenCodec(config(clock_skew_seconds=0), lambda: NOW).decode_access(token)


def test_login_is_uniform_for_unknown_wrong_password_and_inactive_user() -> None:
    cases = [
        None,
        CredentialRecord(USER_ID, "active", "$argon2id$synthetic"),
        CredentialRecord(USER_ID, "blocked", "$argon2id$synthetic"),
    ]
    passwords = ["correct-password", "wrong-password", "correct-password"]

    for credentials, password in zip(cases, passwords, strict=True):
        repository = FakeRepository()
        repository.credentials = credentials
        with pytest.raises(Exception) as captured:
            service(repository).login("user@example.invalid", password, "127.0.0.1")
        assert captured.value.code == "invalid_credentials"
        assert captured.value.message == "E-mail ou credencial invalidos"
        assert repository.failed


def test_local_login_is_disabled_and_rate_limit_has_retry_after() -> None:
    with pytest.raises(Exception) as disabled:
        service(local_auth_enabled=False).login(
            "user@example.invalid", "correct-password", None
        )
    assert disabled.value.code == "identity_adapter_unavailable"

    repository = FakeRepository()
    repository.retry_after = 120
    with pytest.raises(Exception) as limited:
        service(repository).login("user@example.invalid", "correct-password", None)
    assert limited.value.status_code == 429
    assert limited.value.headers == {"Retry-After": "120"}


def test_refresh_hashes_secret_and_replay_is_rejected() -> None:
    repository = FakeRepository()
    repository.refresh_result = RefreshResult(status="replayed")

    with pytest.raises(Exception) as captured:
        service(repository).refresh("plain-refresh-secret")

    assert captured.value.code == "refresh_token_reused"
    assert repository.received_hash == sha256_token("plain-refresh-secret")
    assert "plain-refresh-secret" not in repository.received_hash


def test_logout_uses_identity_from_validated_access_token() -> None:
    repository = FakeRepository()
    selected = service(repository)
    token, _ = selected.tokens.issue_access(USER_ID, SESSION_ID)
    claims = selected.access_claims(token)

    assert selected.logout(claims) == 1
    assert selected.logout_all(claims) == 3
    assert repository.revoked == [(USER_ID, SESSION_ID), (USER_ID, None)]


def test_auth_http_contract_sets_secure_cookie_and_hides_refresh() -> None:
    repository = FakeRepository()
    app.dependency_overrides[get_auth_repository] = lambda: repository
    app.dependency_overrides[get_auth_config] = lambda: config()
    app.dependency_overrides[get_auth_service] = lambda: service(repository)
    try:
        response = TestClient(app).post(
            "/auth/login",
            json={"email": "USER@example.invalid", "password": "correct-password"},
            headers={"Origin": "http://localhost:4200"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["session_id"] == str(SESSION_ID)
    assert "refresh" not in response.json()
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/auth" in cookie


def test_auth_http_rejects_untrusted_origin() -> None:
    repository = FakeRepository()
    app.dependency_overrides[get_auth_repository] = lambda: repository
    app.dependency_overrides[get_auth_config] = lambda: config()
    app.dependency_overrides[get_auth_service] = lambda: service(repository)
    try:
        response = TestClient(app).post(
            "/auth/login",
            json={"email": "user@example.invalid", "password": "correct-password"},
            headers={"Origin": "https://attacker.invalid"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_not_allowed"


def test_openapi_documents_credentials_cookie_and_bearer_security() -> None:
    schema = app.openapi()
    login_schema = schema["components"]["schemas"]["LoginRequest"]
    refresh_parameters = schema["paths"]["/auth/refresh"]["post"]["parameters"]
    logout_operation = schema["paths"]["/auth/logout"]["post"]

    assert login_schema["properties"]["password"]["writeOnly"] is True
    assert {
        "name": "synergia_refresh",
        "in": "cookie",
        "required": False,
    }.items() <= refresh_parameters[0].items()
    assert logout_operation["security"]


def test_auth_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("SYNERGIA_ENV", "production")
    monkeypatch.setenv("SYNERGIA_LOCAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_JWT_SIGNING_KEY", KEY)
    monkeypatch.setenv("AUTH_JWT_ISSUER", "issuer")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "audience")

    loaded = AuthConfig.from_env()

    assert loaded.local_auth_enabled is False
    assert loaded.cookie_secure is True
