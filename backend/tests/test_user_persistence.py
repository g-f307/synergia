from __future__ import annotations

import os
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration


def _bootstrap_admin(database_url: str, suffix: str) -> UUID:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO synergia.identity_users (status, display_name)
            VALUES ('active', %s) RETURNING id
            """,
            (f"Integration Admin {suffix}",),
        )
        actor_id = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO synergia.roles (role_key)
            VALUES (%s) RETURNING id
            """,
            (f"admin-{suffix}",),
        )
        role_id = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE synergia.roles SET role_key = 'admin' WHERE id = %s",
            (role_id,),
        )
        cursor.execute(
            """
            INSERT INTO synergia.user_role_assignments (user_id, role_id)
            VALUES (%s, %s)
            """,
            (actor_id, role_id),
        )
        connection.commit()
        return actor_id


def _cleanup(database_url: str, actor_id: UUID, subject_id: UUID | None) -> None:
    identifiers = [actor_id]
    if subject_id is not None:
        identifiers.append(subject_id)
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE synergia.identity_access_events "
            "DISABLE TRIGGER trg_identity_events_append_only"
        )
        cursor.execute(
            "ALTER TABLE synergia.identity_users "
            "DISABLE TRIGGER trg_identity_users_no_delete"
        )
        cursor.execute(
            "ALTER TABLE synergia.user_emails "
            "DISABLE TRIGGER trg_user_emails_no_delete"
        )
        cursor.execute(
            "ALTER TABLE synergia.roles DISABLE TRIGGER trg_roles_no_delete"
        )
        try:
            cursor.execute(
                """
                DELETE FROM synergia.identity_access_events
                WHERE actor_user_id = ANY(%s) OR subject_user_id = ANY(%s)
                """,
                (identifiers, identifiers),
            )
            cursor.execute(
                "DELETE FROM synergia.user_role_assignments WHERE user_id = ANY(%s)",
                (identifiers,),
            )
            cursor.execute(
                "DELETE FROM synergia.user_emails WHERE user_id = ANY(%s)",
                (identifiers,),
            )
            cursor.execute(
                "DELETE FROM synergia.identity_users WHERE id = ANY(%s)",
                (identifiers,),
            )
            cursor.execute(
                "DELETE FROM synergia.roles WHERE normalized_key = 'admin'"
            )
        finally:
            cursor.execute(
                "ALTER TABLE synergia.roles ENABLE TRIGGER trg_roles_no_delete"
            )
            cursor.execute(
                "ALTER TABLE synergia.user_emails "
                "ENABLE TRIGGER trg_user_emails_no_delete"
            )
            cursor.execute(
                "ALTER TABLE synergia.identity_users "
                "ENABLE TRIGGER trg_identity_users_no_delete"
            )
            cursor.execute(
                "ALTER TABLE synergia.identity_access_events "
                "ENABLE TRIGGER trg_identity_events_append_only"
            )
        connection.commit()


def test_user_api_uses_operational_identity_model() -> None:
    database_url = os.environ["DATABASE_URL"]
    suffix = uuid4().hex[:12]
    actor_id = _bootstrap_admin(database_url, suffix)
    subject_id: UUID | None = None
    headers = {"X-Actor-Id": str(actor_id)}
    try:
        with TestClient(app) as client:
            created = client.post(
                "/admin/users",
                headers=headers,
                json={
                    "display_name": "Integration Subject",
                    "status": "active",
                    "emails": [
                        {
                            "email": f" Subject-{suffix}@Example.Invalid ",
                            "is_primary": True,
                        }
                    ],
                    "reason": "integration provisioning",
                },
            )
            assert created.status_code == 201, created.text
            body = created.json()
            subject_id = UUID(body["id"])
            assert body["emails"][0]["email"] == (
                f"subject-{suffix}@example.invalid"
            )
            assert "local_password_hash" not in body

            duplicate = client.post(
                "/admin/users",
                headers=headers,
                json={
                    "display_name": "Duplicate Subject",
                    "emails": [{"email": f"SUBJECT-{suffix}@EXAMPLE.INVALID"}],
                    "reason": "duplicate validation",
                },
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["error"]["code"] == "user_data_conflict"

            updated = client.patch(
                f"/admin/users/{subject_id}",
                headers=headers,
                json={
                    "version": body["version"],
                    "display_name": "Integration Subject Updated",
                    "emails": [
                        {
                            "email": f"subject-{suffix}@example.invalid",
                            "is_primary": True,
                            "is_verified": True,
                        },
                        {"email": f"secondary-{suffix}@example.invalid"},
                    ],
                    "reason": "integration update",
                },
            )
            assert updated.status_code == 200, updated.text
            assert updated.json()["version"] == body["version"] + 1

            stale = client.patch(
                f"/admin/users/{subject_id}",
                headers=headers,
                json={
                    "version": body["version"],
                    "display_name": "Stale Update",
                    "reason": "concurrent request",
                },
            )
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "user_version_conflict"

            deactivated = client.post(
                f"/admin/users/{subject_id}/deactivate",
                headers=headers,
                json={
                    "version": updated.json()["version"],
                    "reason": "integration deactivation",
                },
            )
            assert deactivated.status_code == 200
            assert deactivated.json()["status"] == "inactive"

            reactivated = client.post(
                f"/admin/users/{subject_id}/reactivate",
                headers=headers,
                json={
                    "version": deactivated.json()["version"],
                    "reason": "integration reactivation",
                },
            )
            assert reactivated.status_code == 200
            assert reactivated.json()["status"] == "active"

            physical_delete = client.delete(
                f"/admin/users/{subject_id}", headers=headers
            )
            assert physical_delete.status_code == 409

            last_admin = client.post(
                f"/admin/users/{actor_id}/block",
                headers=headers,
                json={"version": 1, "reason": "must remain active"},
            )
            assert last_admin.status_code == 409
            assert last_admin.json()["error"]["code"] == "last_active_admin"

        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT event_key, actor_user_id
                FROM synergia.identity_access_events
                WHERE subject_user_id = %s
                  AND event_key LIKE 'user.admin_%%'
                ORDER BY id
                """,
                (subject_id,),
            )
            events = cursor.fetchall()
            assert [event[0] for event in events] == [
                "user.admin_created",
                "user.admin_updated",
                "user.admin_deactivate",
                "user.admin_reactivate",
            ]
            assert all(event[1] == actor_id for event in events)
    finally:
        _cleanup(database_url, actor_id, subject_id)
