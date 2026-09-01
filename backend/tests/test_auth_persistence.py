from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.auth.repository import PostgresAuthRepository
from app.auth.security import PasswordVerifier, protected_identifier, sha256_token
from app.main import app

pytestmark = pytest.mark.integration

KEY = "synthetic-integration-signing-key-at-least-32-bytes"


def _create_user(database_url: str, password: str = "synthetic-password-123") -> tuple:
    user_id = uuid4()
    email = f"auth-{user_id}@example.invalid"
    password_hash = PasswordHasher().hash(password)
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO synergia.identity_users (
                id, status, display_name, local_password_hash
            ) VALUES (%s, 'active', 'Synthetic Auth User', %s)
            """,
            (user_id, password_hash),
        )
        cursor.execute(
            """
            INSERT INTO synergia.user_emails (user_id, email, is_primary)
            VALUES (%s, %s, true)
            """,
            (user_id, email),
        )
    return user_id, email, password, password_hash


def _login(repository, email, password, now):
    identifier_hash = protected_identifier(email, KEY)
    attempt_id, retry = repository.begin_login_attempt(
        identifier_hash, None, now, 900, 5, 900
    )
    assert retry is None and attempt_id is not None
    credentials = repository.credentials_for_email(email)
    assert credentials is not None
    assert PasswordVerifier().verify(credentials.password_hash, password)
    return repository.create_session(
        attempt_id, credentials.user_id, now, 8, 24, None
    )


def test_refresh_rotation_and_replay_revoke_the_family() -> None:
    database_url = os.environ["DATABASE_URL"]
    _user_id, email, password, _hash = _create_user(database_url)
    repository = PostgresAuthRepository(database_url)
    now = datetime.now(UTC)
    session = _login(repository, email, password, now)

    rotated = repository.rotate_refresh(
        sha256_token(session.refresh_token), now, idle_hours=8
    )
    replayed = repository.rotate_refresh(
        sha256_token(session.refresh_token), now, idle_hours=8
    )

    assert rotated.status == "rotated"
    assert replayed.status == "replayed"
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT status, revocation_reason
            FROM synergia.identity_sessions WHERE id = %s
            """,
            (session.session_id,),
        )
        assert cursor.fetchone() == ("revoked", "refresh_token_reuse")
        cursor.execute(
            """
            SELECT status FROM synergia.session_refresh_tokens
            WHERE session_id = %s ORDER BY issued_at, id
            """,
            (session.session_id,),
        )
        assert sorted(row[0] for row in cursor.fetchall()) == ["revoked", "used"]
        cursor.execute(
            """
            SELECT count(*) FROM synergia.session_refresh_tokens
            WHERE token_hash IN (%s, %s)
            """,
            (session.refresh_token, rotated.refresh_token),
        )
        assert cursor.fetchone()[0] == 0


def test_two_concurrent_refreshes_do_not_return_an_internal_failure() -> None:
    database_url = os.environ["DATABASE_URL"]
    _user_id, email, password, _hash = _create_user(database_url)
    repository = PostgresAuthRepository(database_url)
    now = datetime.now(UTC)
    session = _login(repository, email, password, now)
    token_hash = sha256_token(session.refresh_token)

    def rotate():
        return PostgresAuthRepository(database_url).rotate_refresh(token_hash, now, 8)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(rotate), executor.submit(rotate)]
        results = [future.result() for future in futures]

    assert sorted(result.status for result in results) == ["replayed", "rotated"]
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT status, revocation_reason
            FROM synergia.identity_sessions WHERE id = %s
            """,
            (session.session_id,),
        )
        assert cursor.fetchone() == ("revoked", "refresh_token_reuse")


def test_global_logout_and_user_status_change_prevent_refresh() -> None:
    database_url = os.environ["DATABASE_URL"]
    user_id, email, password, _hash = _create_user(database_url)
    repository = PostgresAuthRepository(database_url)
    now = datetime.now(UTC)
    first = _login(repository, email, password, now)
    second = _login(repository, email, password, now)

    assert repository.revoke_all_sessions(user_id, now) == 2
    assert repository.rotate_refresh(
        sha256_token(first.refresh_token), now, 8
    ).status == "invalid"
    assert repository.rotate_refresh(
        sha256_token(second.refresh_token), now, 8
    ).status == "invalid"

    third = _login(repository, email, password, now)
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE synergia.identity_users SET status = 'blocked' WHERE id = %s",
            (user_id,),
        )
    assert repository.rotate_refresh(
        sha256_token(third.refresh_token), now, 8
    ).status == "invalid"


def test_http_login_refresh_logout_and_rate_limit(monkeypatch) -> None:
    database_url = os.environ["DATABASE_URL"]
    user_id, email, password, _hash = _create_user(database_url)
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv("SYNERGIA_LOCAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_JWT_SIGNING_KEY", KEY)
    monkeypatch.setenv("AUTH_JWT_ISSUER", "synergia-integration")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "synergia-api-integration")
    monkeypatch.setenv("AUTH_REFRESH_COOKIE_SECURE", "false")
    monkeypatch.setenv("AUTH_LOGIN_MAX_ATTEMPTS", "2")

    with TestClient(app) as client:
        logged_in = client.post(
            "/auth/login",
            json={"email": email, "password": password},
            headers={"Origin": "http://localhost:4200"},
        )
        assert logged_in.status_code == 200
        access_token = logged_in.json()["access_token"]
        assert "synergia_refresh" in client.cookies

        refreshed = client.post(
            "/auth/refresh", headers={"Origin": "http://localhost:4200"}
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["access_token"] != access_token

        logged_out = client.post(
            "/auth/logout",
            headers={
                "Authorization": f"Bearer {refreshed.json()['access_token']}",
                "Origin": "http://localhost:4200",
            },
        )
        assert logged_out.status_code == 200
        assert logged_out.json() == {"revoked_sessions": 1}
        assert "synergia_refresh" not in client.cookies

        missing_email = f"missing-{user_id}@example.invalid"
        for expected in (401, 401, 429):
            failed = client.post(
                "/auth/login",
                json={"email": missing_email, "password": "wrong"},
            )
            assert failed.status_code == expected
        assert failed.headers["retry-after"]

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT event_key FROM synergia.identity_access_events
            WHERE subject_user_id = %s OR event_key = 'auth.login_failed'
            ORDER BY id
            """,
            (user_id,),
        )
        events = {row[0] for row in cursor.fetchall()}
    assert {"auth.login_succeeded", "auth.refresh_rotated", "auth.logout"} <= events
