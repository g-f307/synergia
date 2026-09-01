from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.auth.config import AuthConfig
from app.auth.security import AccessClaims, TokenCodec
from app.authorization import AuthorizationRepository
from app.main import app

pytestmark = [pytest.mark.integration, pytest.mark.real_authorization]

KEY = "authorization-test-signing-key-with-at-least-32-bytes"

ROLE_PERMISSIONS = {
    "admin": {"audit.read", "access.admin", "session.revoke.any", "session.revoke.own"},
    "gestor": {
        "dashboard.read", "execution.read", "business.read", "pending.read",
        "import.create", "import.read", "artifact.read", "execution.reprocess",
        "audit.read", "artifact.export", "report.export", "session.revoke.own",
    },
    "analista": {
        "dashboard.read", "execution.read", "business.read", "pending.read",
        "import.read", "artifact.read", "audit.read", "artifact.export",
        "report.export", "session.revoke.own",
    },
    "operador": {
        "dashboard.read", "execution.read", "business.read", "pending.read",
        "import.create", "import.read", "artifact.read", "session.revoke.own",
    },
    "consulta": {
        "dashboard.read", "execution.read", "business.read", "pending.read",
        "session.revoke.own",
    },
}


def _configure(monkeypatch) -> AuthConfig:
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv("AUTH_JWT_SIGNING_KEY", KEY)
    monkeypatch.setenv("AUTH_JWT_ISSUER", "synergia-authorization-test")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "synergia-api-test")
    return AuthConfig.from_env()


def _bootstrap(database_url: str, role: str = "consulta") -> dict[str, UUID | str]:
    suffix = uuid4().hex[:10]
    user_id = uuid4()
    session_id = uuid4()
    organization_a = uuid4()
    organization_b = uuid4()
    execution_a = f"authz-a-{suffix}"
    execution_b = f"authz-b-{suffix}"
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO synergia.identity_users (id, status, display_name)
            VALUES (%s, 'active', %s)
            """,
            (user_id, f"Authorization {suffix}"),
        )
        cursor.execute(
            """
            INSERT INTO synergia.iam_organizations
                (id, organization_code, display_name)
            VALUES (%s, %s, %s), (%s, %s, %s)
            """,
            (
                organization_a,
                f"authz-a-{suffix}",
                f"Organization A {suffix}",
                organization_b,
                f"authz-b-{suffix}",
                f"Organization B {suffix}",
            ),
        )
        cursor.execute(
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
        cursor.execute(
            """
            INSERT INTO synergia.user_role_assignments
                (user_id, role_id, organization_id)
            SELECT %s, id, %s FROM synergia.roles WHERE normalized_key = %s
            RETURNING id
            """,
            (user_id, organization_a, role),
        )
        assignment_id = cursor.fetchone()[0]
        for execution_id, organization_id in (
            (execution_a, organization_a),
            (execution_b, organization_b),
        ):
            cursor.execute(
                """
                INSERT INTO synergia.executions (
                    id, status, source, actor_type, actor_identifier,
                    organization_id, initiated_by_user_id,
                    initiated_by_session_id
                ) VALUES (%s, 'pending', 'OWM', 'user', %s, %s, %s, %s)
                """,
                (execution_id, str(user_id), organization_id, user_id, session_id),
            )
    return {
        "user": user_id,
        "session": session_id,
        "organization_a": organization_a,
        "organization_b": organization_b,
        "execution_a": execution_a,
        "execution_b": execution_b,
        "assignment": assignment_id,
    }


def _token(config: AuthConfig, ids: dict[str, UUID | str]) -> str:
    return TokenCodec(config).issue_access(ids["user"], ids["session"])[0]


def _seed_duplicate_lots(
    database_url: str, ids: dict[str, UUID | str]
) -> None:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        resources = []
        for label, execution_id in (
            ("a", ids["execution_a"]),
            ("b", ids["execution_b"]),
        ):
            source_file_id = cursor.execute(
                """
                INSERT INTO synergia.source_files (
                    execution_id, file_name, content_hash
                ) VALUES (%s, %s, %s) RETURNING id
                """,
                (execution_id, f"lot-{label}.csv", label * 64),
            ).fetchone()[0]
            workorder_id = cursor.execute(
                """
                INSERT INTO synergia.workorders (
                    workorder_number, execution_id, source_file_id
                ) VALUES (%s, %s, %s) RETURNING id
                """,
                (f"WO-{label.upper()}", execution_id, source_file_id),
            ).fetchone()[0]
            lot_id = cursor.execute(
                """
                INSERT INTO synergia.lots (
                    lot_number, workorder_id, execution_id, source_file_id,
                    updated_at
                ) VALUES (
                    'LOT-001', %s, %s, %s,
                    now() + CASE WHEN %s = 'b' THEN interval '1 minute'
                                 ELSE interval '0 minutes' END
                ) RETURNING id
                """,
                (workorder_id, execution_id, source_file_id, label),
            ).fetchone()[0]
            resources.append(
                (label, execution_id, source_file_id, workorder_id, lot_id)
            )
        for label, execution_id, source_file_id, workorder_id, lot_id in resources:
            cursor.execute(
                """
                INSERT INTO synergia.serials (
                    serial_number, workorder_id, lot_id,
                    execution_id, source_file_id
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    f"SER-{execution_id}",
                    workorder_id,
                    lot_id,
                    execution_id,
                    source_file_id,
                ),
            )


@pytest.mark.parametrize(("role", "expected"), ROLE_PERMISSIONS.items())
def test_effective_permission_matrix_by_role(role, expected) -> None:
    database_url = os.environ["DATABASE_URL"]
    ids = _bootstrap(database_url, role)
    claims = AccessClaims(
        user_id=ids["user"], session_id=ids["session"], token_id=uuid4()
    )
    resolved = AuthorizationRepository(database_url).resolve(
        claims, datetime.now(UTC)
    )
    assert resolved is not None
    assert set(resolved) == expected
    assert all(scopes == {ids["organization_a"]} for scopes in resolved.values())
    if role == "admin":
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                UPDATE synergia.identity_users
                SET status = 'inactive', deactivated_at = now()
                WHERE id = %s
                """,
                (ids["user"],),
            )


def test_authentication_vertical_and_horizontal_access(monkeypatch) -> None:
    config = _configure(monkeypatch)
    database_url = os.environ["DATABASE_URL"]
    ids = _bootstrap(database_url, "analista")
    headers = {"Authorization": f"Bearer {_token(config, ids)}"}

    with TestClient(app) as client:
        assert client.get(f"/executions/{ids['execution_a']}").status_code == 401
        assert client.get(
            f"/executions/{ids['execution_a']}",
            headers={"Authorization": "Bearer invalid"},
        ).status_code == 401
        assert client.get(
            f"/executions/{ids['execution_a']}", headers=headers
        ).status_code == 200
        outside = client.get(f"/executions/{ids['execution_b']}", headers=headers)
        assert outside.status_code == 404
        evidence_outside = client.get(
            f"/executions/{ids['execution_b']}/evidences", headers=headers
        )
        assert evidence_outside.status_code == 404

        upload = client.post(
            "/imports",
            headers=headers,
            data={
                "source": "OWM",
                "organization_id": str(ids["organization_a"]),
            },
            files={"file": ("synthetic.csv", b"id\n1\n", "text/csv")},
        )
        assert upload.status_code == 403

        administration = client.get("/admin/users", headers=headers)
        assert administration.status_code == 403

        vertical = client.post(
            f"/executions/{ids['execution_a']}/reprocess",
            headers=headers,
            json={"technical_origin": "authorization-test"},
        )
        assert vertical.status_code == 403


def test_role_change_and_session_revocation_are_immediate(monkeypatch) -> None:
    config = _configure(monkeypatch)
    database_url = os.environ["DATABASE_URL"]
    ids = _bootstrap(database_url)
    headers = {"Authorization": f"Bearer {_token(config, ids)}"}

    with TestClient(app) as client:
        response = client.get(f"/executions/{ids['execution_a']}", headers=headers)
        assert response.status_code == 200
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                UPDATE synergia.user_role_assignments
                SET revoked_at = now() WHERE id = %s
                """,
                (ids["assignment"],),
            )
        response = client.get(f"/executions/{ids['execution_a']}", headers=headers)
        assert response.status_code == 403

        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                UPDATE synergia.identity_sessions
                SET status = 'revoked', revoked_at = now(),
                    revocation_reason = 'authorization_test'
                WHERE id = %s
                """,
                (ids["session"],),
            )
        response = client.get(f"/executions/{ids['execution_a']}", headers=headers)
        assert response.status_code == 401


def test_organization_and_global_scope_denials_are_audited(monkeypatch) -> None:
    config = _configure(monkeypatch)
    database_url = os.environ["DATABASE_URL"]
    upload_ids = _bootstrap(database_url, "operador")
    admin_ids = _bootstrap(database_url, "consulta")
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO synergia.user_permission_assignments (
                user_id, permission_id, organization_id
            )
            SELECT %s, id, %s
            FROM synergia.permissions
            WHERE normalized_key = 'access.admin'
            """,
            (admin_ids["user"], admin_ids["organization_a"]),
        )
    upload_correlation_id = uuid4()
    admin_correlation_id = uuid4()

    with TestClient(app) as client:
        upload = client.post(
            "/imports",
            headers={
                "Authorization": f"Bearer {_token(config, upload_ids)}",
                "X-Correlation-ID": str(upload_correlation_id),
            },
            data={
                "source": "OWM",
                "organization_id": str(upload_ids["organization_b"]),
            },
            files={"file": ("synthetic.csv", b"id\n1\n", "text/csv")},
        )
        assert upload.status_code == 403

        administration = client.get(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {_token(config, admin_ids)}",
                "X-Correlation-ID": str(admin_correlation_id),
            },
        )
        assert administration.status_code == 403

    with psycopg.connect(database_url) as connection:
        events = connection.execute(
            """
            SELECT actor_user_id, session_id, correlation_id, entity_id, payload
            FROM synergia.identity_access_events
            WHERE event_key = 'authorization.denied'
              AND correlation_id = ANY(%s)
            ORDER BY correlation_id
            """,
            ([upload_correlation_id, admin_correlation_id],),
        ).fetchall()
    assert len(events) == 2
    by_correlation = {event[2]: event for event in events}
    upload_event = by_correlation[upload_correlation_id]
    assert upload_event[:4] == (
        upload_ids["user"],
        upload_ids["session"],
        upload_correlation_id,
        "/imports",
    )
    assert upload_event[4] == {"method": "POST", "permission": "import.create"}
    admin_event = by_correlation[admin_correlation_id]
    assert admin_event[:4] == (
        admin_ids["user"],
        admin_ids["session"],
        admin_correlation_id,
        "/admin/users",
    )
    assert admin_event[4] == {"method": "GET", "permission": "access.admin"}
    serialized = str([event[4] for event in events])
    for sensitive_value in (
        str(upload_ids["organization_b"]),
        str(upload_ids["execution_b"]),
        "synthetic.csv",
        "id\\n1",
    ):
        assert sensitive_value not in serialized


def test_lot_query_uses_the_same_workorder_and_organization_scope(monkeypatch) -> None:
    config = _configure(monkeypatch)
    database_url = os.environ["DATABASE_URL"]
    ids = _bootstrap(database_url, "analista")
    _seed_duplicate_lots(database_url, ids)
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            UPDATE synergia.user_role_assignments
            SET organization_id = %s WHERE id = %s
            """,
            (ids["organization_b"], ids["assignment"]),
        )
    correlation_id = uuid4()
    headers = {
        "Authorization": f"Bearer {_token(config, ids)}",
        "X-Correlation-ID": str(correlation_id),
    }

    with TestClient(app) as client:
        allowed = client.get(
            "/lots/LOT-001?workorder_number=WO-B", headers=headers
        )
        assert allowed.status_code == 200
        assert allowed.json()["workorder_number"] == "WO-B"
        assert allowed.json()["serials"] == [f"SER-{ids['execution_b']}"]

        crossed = client.get(
            "/lots/LOT-001?workorder_number=WO-A", headers=headers
        )
        assert crossed.status_code == 404
        assert crossed.json()["error"]["code"] == "lot_not_found"
        assert "WO-A" not in crossed.text
        assert f"SER-{ids['execution_a']}" not in crossed.text

        missing_correlation_id = uuid4()
        missing = client.get(
            "/lots/LOT-INEXISTENTE?workorder_number=WO-INEXISTENTE",
            headers={
                **headers,
                "X-Correlation-ID": str(missing_correlation_id),
            },
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "lot_not_found"

    with psycopg.connect(database_url) as connection:
        events = connection.execute(
            """
            SELECT actor_user_id, session_id, correlation_id, entity_id, payload
            FROM synergia.identity_access_events
            WHERE event_key = 'authorization.denied'
              AND correlation_id = %s
            """,
            (correlation_id,),
        ).fetchall()
    assert len(events) == 1
    event = events[0]
    assert event[:4] == (
        ids["user"],
        ids["session"],
        correlation_id,
        "/lots/{lot_number}",
    )
    assert event[4] == {"method": "GET", "permission": "business.read"}
    serialized = str(event[4])
    for sensitive_value in (
        "LOT-001",
        "WO-A",
        str(ids["execution_a"]),
        str(ids["organization_a"]),
    ):
        assert sensitive_value not in serialized
    with psycopg.connect(database_url) as connection:
        missing_event_count = connection.execute(
            """
            SELECT count(*) FROM synergia.identity_access_events
            WHERE event_key = 'authorization.denied'
              AND correlation_id = %s
            """,
            (missing_correlation_id,),
        ).fetchone()[0]
    assert missing_event_count == 0


def test_denial_audit_uses_safe_technical_identity_and_correlation(monkeypatch) -> None:
    config = _configure(monkeypatch)
    database_url = os.environ["DATABASE_URL"]
    ids = _bootstrap(database_url)
    correlation_id = uuid4()
    headers = {
        "Authorization": f"Bearer {_token(config, ids)}",
        "X-Correlation-ID": str(correlation_id),
    }
    with TestClient(app) as client:
        response = client.post(
            f"/executions/{ids['execution_a']}/reprocess",
            headers=headers,
            json={"technical_origin": "authorization-test"},
        )
    assert response.status_code == 403
    assert response.headers["X-Correlation-ID"] == str(correlation_id)
    with psycopg.connect(database_url) as connection:
        event = connection.execute(
            """
            SELECT actor_user_id, session_id, correlation_id, entity_id, payload
            FROM synergia.identity_access_events
            WHERE event_key = 'authorization.denied' AND correlation_id = %s
            """,
            (correlation_id,),
        ).fetchone()
    assert event[:4] == (
        ids["user"],
        ids["session"],
        correlation_id,
        "/executions/{execution_id}/reprocess",
    )
    serialized = str(event[4])
    assert "authorization" not in serialized.lower()
    assert "bearer" not in serialized.lower()
