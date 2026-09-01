from __future__ import annotations

import os
from io import BytesIO
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.auth.config import AuthConfig
from app.auth.security import TokenCodec
from app.main import app

pytestmark = pytest.mark.integration
KEY = "profile-integration-signing-key-with-at-least-32-bytes"


def image_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (16, 16), color=(165, 0, 52)).save(stream, format="PNG")
    return stream.getvalue()


def test_profile_preferences_avatar_and_audit_persist(monkeypatch, tmp_path) -> None:
    database_url = os.environ["DATABASE_URL"]
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv("AUTH_JWT_SIGNING_KEY", KEY)
    monkeypatch.setenv("AUTH_JWT_ISSUER", "synergia-profile-test")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "synergia-profile-api")
    monkeypatch.setenv("PROFILE_AVATAR_STORAGE_ROOT", str(tmp_path))
    user_id = uuid4()
    session_id = uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO synergia.identity_users (id, status, display_name)
            VALUES (%s, 'active', 'Profile Integration')
            """,
            (user_id,),
        )
        connection.execute(
            """
            INSERT INTO synergia.user_emails (
                user_id, email, is_primary, is_verified, verified_at
            ) VALUES (%s, %s, true, true, now())
            """,
            (user_id, f"profile-{user_id}@example.invalid"),
        )
        connection.execute(
            """
            INSERT INTO synergia.identity_sessions (
                id, user_id, status, authenticated_at, last_seen_at,
                idle_expires_at, absolute_expires_at, authentication_method
                ) VALUES (
                    %s, %s, 'active', now(), now(),
                    now() + interval '8 hours', now() + interval '24 hours',
                    'synthetic'
                )
            """,
            (
                session_id,
                user_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO synergia.user_role_assignments (user_id, role_id)
            SELECT %s, id FROM synergia.roles WHERE normalized_key = 'operador'
            """,
            (user_id,),
        )
    token = TokenCodec(AuthConfig.from_env()).issue_access(user_id, session_id)[0]
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        current = client.get("/me", headers=headers)
        assert current.status_code == 200, current.text
        assert current.json()["locale"] == "pt-BR"

        updated = client.patch(
            "/me",
            headers=headers,
            json={
                "version": current.json()["version"],
                "display_name": "Profile Updated",
                "locale": "en-US",
                "timezone": "UTC",
                "notifications": {"email": False, "in_app": True},
            },
        )
        assert updated.status_code == 200, updated.text

        stale = client.patch(
            "/me",
            headers=headers,
            json={"version": current.json()["version"], "locale": "es-ES"},
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "profile_version_conflict"

        avatar = client.post(
            "/me/avatar",
            headers=headers,
            files={"avatar": ("profile.png", image_bytes(), "image/png")},
        )
        assert avatar.status_code == 201, avatar.text
        assert avatar.json()["avatar"]["url"] == "/me/avatar"
        assert client.get("/me/avatar", headers=headers).content == image_bytes()
        assert client.delete("/me/avatar", headers=headers).status_code == 200

    with psycopg.connect(database_url) as connection:
        persisted = connection.execute(
            """
            SELECT display_name, locale, timezone, notification_preferences,
                   avatar_storage_key
            FROM synergia.identity_users WHERE id = %s
            """,
            (user_id,),
        ).fetchone()
        assert persisted == (
            "Profile Updated",
            "en-US",
            "UTC",
            {"email": False, "in_app": True},
            None,
        )
        events = connection.execute(
            """
            SELECT array_agg(event_key ORDER BY id)
            FROM synergia.identity_access_events WHERE subject_user_id = %s
              AND event_key LIKE 'profile.%%'
            """,
            (user_id,),
        ).fetchone()[0]
        assert events == [
            "profile.updated",
            "profile.avatar_updated",
            "profile.avatar_removed",
        ]
    assert not list(tmp_path.rglob("*.*"))
