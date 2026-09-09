from __future__ import annotations

# Persistence fixtures keep their SQL aligned and readable.
# ruff: noqa: E501
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.auth.config import AuthConfig
from app.auth.security import TokenCodec
from app.main import app

pytestmark = [pytest.mark.integration, pytest.mark.real_authorization]
KEY = "notification-integration-signing-key-with-at-least-32-bytes"


def _identity(connection, *, locale="pt-BR", in_app=True):
    user_id, session_id = uuid4(), uuid4()
    connection.execute(
        """INSERT INTO synergia.identity_users (
             id, status, display_name, locale, notification_preferences
           ) VALUES (%s, 'active', 'Notification Test', %s, %s)""",
        (user_id, locale, Jsonb({"email": True, "in_app": in_app})),
    )
    connection.execute(
        """INSERT INTO synergia.identity_sessions (
             id, user_id, status, authenticated_at, last_seen_at,
             idle_expires_at, absolute_expires_at, authentication_method
           ) VALUES (%s, %s, 'active', now(), now(), now() + interval '8 hours',
             now() + interval '24 hours', 'synthetic')""",
        (session_id, user_id),
    )
    return user_id, session_id


def _token(monkeypatch, user_id, session_id):
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv("AUTH_JWT_SIGNING_KEY", KEY)
    monkeypatch.setenv("AUTH_JWT_ISSUER", "synergia-notification-test")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "synergia-notification-api")
    return TokenCodec(AuthConfig.from_env()).issue_access(user_id, session_id)[0]


def test_event_projection_preferences_locale_scope_and_read_audit(monkeypatch) -> None:
    database_url = os.environ["DATABASE_URL"]
    org_id, other_org_id = uuid4(), uuid4()
    execution_id = f"notification-{uuid4()}"
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO synergia.iam_organizations (id, organization_code, display_name)
               VALUES (%s, %s, 'Notification Org'), (%s, %s, 'Other Org')""",
            (org_id, f"notif-{org_id.hex[:10]}", other_org_id, f"other-{other_org_id.hex[:10]}"),
        )
        user_id, session_id = _identity(connection, locale="en-US")
        disabled_user_id, _ = _identity(connection, locale="es-ES", in_app=False)
        for current_user in (user_id, disabled_user_id):
            connection.execute(
                """INSERT INTO synergia.user_role_assignments (user_id, role_id, organization_id)
                   SELECT %s, id, %s FROM synergia.roles WHERE normalized_key = 'gestor'""",
                (current_user, org_id),
            )
        connection.execute(
            """INSERT INTO synergia.executions (
                 id, status, organization_id, initiated_by_user_id,
                 state_changed_by_type, state_changed_by, state_change_reason
               ) VALUES (%s, 'completed', %s, %s, 'system', 'notification-test', 'completed')""",
            (execution_id, org_id, user_id),
        )
        report_id, report_version_id = uuid4(), uuid4()
        connection.execute(
            """INSERT INTO synergia.reports (
                 id, report_type, organization_id, created_by_user_id
               ) VALUES (%s, 'workorder_consolidated', %s, %s)""",
            (report_id, org_id, user_id),
        )
        connection.execute(
            """INSERT INTO synergia.report_versions (
                 id, report_id, version, execution_id, organization_id,
                 requested_by_user_id, requested_by_session_id, reference_at,
                 schema_version, state, completeness, completed_at
               ) VALUES (%s, %s, 1, %s, %s, %s, %s, now(), '1.1.0',
                 'succeeded', 'complete', now())""",
            (report_version_id, report_id, execution_id, org_id, user_id, session_id),
        )
        connection.execute(
            """INSERT INTO synergia.report_events (
                 report_version_id, event_type, actor_user_id, correlation_id
               ) VALUES (%s, 'report.generation_succeeded', %s, %s)""",
            (report_version_id, user_id, uuid4()),
        )
        connection.execute(
            """INSERT INTO synergia.executions (
                 id, status, organization_id, initiated_by_user_id,
                 state_changed_by_type, state_changed_by, state_change_reason
               ) VALUES (%s, 'completed', %s, %s, 'system', 'notification-test', 'completed')""",
            (f"disabled-{uuid4()}", org_id, disabled_user_id),
        )
        suppressed = connection.execute(
            "SELECT state FROM synergia.notifications WHERE recipient_user_id = %s",
            (disabled_user_id,),
        ).fetchone()
        assert suppressed == ("suppressed",)

        connection.execute(
            """SELECT synergia.enqueue_internal_notification(
                 %s, %s, 'pending.summary', %s, %s, %s,
                 'audit_event', 900000001, now(), NULL)""",
            (user_id, org_id, execution_id, Jsonb({"execution_id": execution_id, "count": 2}), f"pending.summary:{execution_id}"),
        )
        connection.execute(
            """SELECT synergia.enqueue_internal_notification(
                 %s, %s, 'pending.summary', %s, %s, %s,
                 'audit_event', 900000002, now(), NULL)""",
            (user_id, org_id, execution_id, Jsonb({"execution_id": execution_id, "count": 3}), f"pending.summary:{execution_id}"),
        )
        consolidated = connection.execute(
            """SELECT occurrence_count, parameters->>'count'
               FROM synergia.notifications
               WHERE recipient_user_id = %s AND notification_type = 'pending.summary'""",
            (user_id,),
        ).fetchone()
        assert consolidated == (2, "3")
        out_of_scope_id = connection.execute(
            """SELECT synergia.enqueue_internal_notification(
                 %s, %s, 'execution.completed', 'outside-scope', %s, %s,
                 'audit_event', 900000003, now(), NULL)""",
            (
                user_id,
                other_org_id,
                Jsonb({"execution_id": "outside-scope"}),
                f"execution.completed:outside-{execution_id}",
            ),
        ).fetchone()[0]

    token = _token(monkeypatch, user_id, session_id)
    headers = {"Authorization": f"Bearer {token}", "X-Correlation-ID": str(uuid4())}
    with TestClient(app) as client:
        response = client.get("/notifications?page=1&page_size=10", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["pagination"]["total"] == 3
        items = response.json()["items"]
        assert {item["title"] for item in items} == {
            "Processing complete",
            "Pending items identified",
            "Report available",
        }
        assert any(item["resource_url"] for item in items)
        assert any(not item["resource_available"] for item in items)
        timestamps = [item["last_occurred_at"] for item in items]
        assert timestamps == sorted(timestamps, reverse=True)
        paged = client.get(
            "/notifications?page=1&page_size=1&sort=oldest", headers=headers
        )
        assert paged.status_code == 200
        assert paged.json()["pagination"]["pages"] == 3
        item = items[0]
        read = client.patch(
            f"/notifications/{item['id']}/read",
            headers=headers,
            json={"version": item["version"]},
        )
        assert read.status_code == 200, read.text
        assert read.json()["state"] == "read"
        denied = client.patch(
            f"/notifications/{out_of_scope_id}/read",
            headers=headers,
            json={"version": 1},
        )
        assert denied.status_code == 404

        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE synergia.identity_users SET locale = 'es-ES' WHERE id = %s",
                (user_id,),
            )
        fallback = client.get("/notifications?page_size=10", headers=headers)
        assert fallback.status_code == 200
        assert any(
            value in {"Processamento concluído", "Pendências identificadas"}
            for value in (entry["title"] for entry in fallback.json()["items"])
        )
        batch = client.post("/notifications/read-all", headers=headers)
        assert batch.status_code == 200
        assert batch.json() == {"count": 2}
        assert client.get("/notifications/unread-count", headers=headers).json() == {
            "count": 0
        }

    with psycopg.connect(database_url) as connection:
        audit = connection.execute(
            """SELECT actor_user_id, actor_session_id, correlation_id, payload
               FROM synergia.notification_events
               WHERE notification_id = %s AND event_type = 'notification.read'""",
            (item["id"],),
        ).fetchone()
        assert audit[0:2] == (user_id, session_id)
        assert audit[2] is not None
        assert audit[3] == {"mode": "individual"}
        serialized = str(audit[3]).lower()
        assert "token" not in serialized and "password" not in serialized and "/tmp/" not in serialized
        denial = connection.execute(
            """SELECT payload FROM synergia.identity_access_events
               WHERE actor_user_id = %s AND event_key = 'authorization.denied'
                 AND entity_id = '/notifications/{notification_id}/read'
               ORDER BY id DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        assert denial[0] == {"method": "PATCH", "permission": "notification.read"}
        batch_events = connection.execute(
            """SELECT count(*) FROM synergia.notification_events
               WHERE recipient_user_id = %s AND event_type = 'notification.read'
                 AND payload = '{"mode":"all"}'::jsonb""",
            (user_id,),
        ).fetchone()[0]
        assert batch_events == 2


def test_concurrent_occurrences_are_consolidated_atomically() -> None:
    database_url = os.environ["DATABASE_URL"]
    org_id, user_id = uuid4(), uuid4()
    execution_id = f"concurrent-{uuid4()}"
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO synergia.iam_organizations (
                 id, organization_code, display_name
               ) VALUES (%s, %s, 'Concurrent Notification Org')""",
            (org_id, f"concurrent-{org_id.hex[:10]}"),
        )
        connection.execute(
            """INSERT INTO synergia.identity_users (id, status, display_name)
               VALUES (%s, 'active', 'Concurrent Notification User')""",
            (user_id,),
        )

    def enqueue(source_event_id: int):
        with psycopg.connect(database_url) as connection:
            return connection.execute(
                """SELECT synergia.enqueue_internal_notification(
                     %s, %s, 'pending.summary', %s, %s, %s,
                     'audit_event', %s, now(), NULL)""",
                (
                    user_id,
                    org_id,
                    execution_id,
                    Jsonb({"execution_id": execution_id, "count": 2}),
                    f"pending.summary:{execution_id}",
                    source_event_id,
                ),
            ).fetchone()[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        notification_ids = list(pool.map(enqueue, (910000001, 910000002)))

    assert notification_ids[0] == notification_ids[1]
    with psycopg.connect(database_url) as connection:
        persisted = connection.execute(
            """SELECT occurrence_count, version
               FROM synergia.notifications WHERE id = %s""",
            (notification_ids[0],),
        ).fetchone()
        assert persisted == (2, 2)
        occurrence_id = connection.execute(
            """SELECT id FROM synergia.notification_occurrences
               WHERE notification_id = %s ORDER BY id LIMIT 1""",
            (notification_ids[0],),
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """UPDATE synergia.notification_occurrences
                   SET occurred_at = occurred_at + interval '1 second'
                   WHERE id = %s""",
                (occurrence_id,),
            )
