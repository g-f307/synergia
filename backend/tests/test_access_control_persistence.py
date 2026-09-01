from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _bootstrap(database_url: str, suffix: str) -> dict[str, UUID]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO synergia.identity_users (status, display_name)
            VALUES ('active', %s), ('active', %s)
            RETURNING id
            """,
            (f"Access Admin {suffix}", f"Access Subject {suffix}"),
        )
        actor_id, subject_id = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT id FROM synergia.roles WHERE normalized_key = 'admin'")
        admin_role_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM synergia.roles WHERE normalized_key = 'gestor'")
        gestor_role_id = cursor.fetchone()[0]
        cursor.execute(
            "SELECT id FROM synergia.roles WHERE normalized_key = 'consulta'"
        )
        consulta_role_id = cursor.fetchone()[0]
        cursor.execute(
            "SELECT id FROM synergia.permissions WHERE normalized_key = 'report.export'"
        )
        report_permission_id = cursor.fetchone()[0]
        cursor.execute(
            "SELECT id FROM synergia.permissions WHERE normalized_key = 'access.admin'"
        )
        access_admin_permission_id = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO synergia.user_role_assignments (user_id, role_id)
            VALUES (%s, %s)
            """,
            (actor_id, admin_role_id),
        )
        cursor.execute(
            """
            INSERT INTO synergia.iam_organizations (
                organization_code, display_name
            ) VALUES (%s, %s) RETURNING id
            """,
            (f"org-{suffix}", f"Organization {suffix}"),
        )
        organization_id = cursor.fetchone()[0]
        connection.commit()
        return {
            "actor": actor_id,
            "subject": subject_id,
            "admin_role": admin_role_id,
            "gestor_role": gestor_role_id,
            "consulta_role": consulta_role_id,
            "report_permission": report_permission_id,
            "access_admin_permission": access_admin_permission_id,
            "organization": organization_id,
        }


def _cleanup(database_url: str, ids: dict[str, UUID]) -> None:
    users = [ids["actor"], ids["subject"]]
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for table, trigger in (
            ("identity_access_events", "trg_identity_events_append_only"),
            ("identity_users", "trg_identity_users_no_delete"),
            ("identity_groups", "trg_identity_groups_no_delete"),
            ("roles", "trg_roles_no_delete"),
            ("iam_organizations", "trg_iam_organizations_no_delete"),
        ):
            cursor.execute(f"ALTER TABLE synergia.{table} DISABLE TRIGGER {trigger}")
        try:
            cursor.execute(
                """
                DELETE FROM synergia.identity_access_events
                WHERE actor_user_id = ANY(%s) OR subject_user_id = ANY(%s)
                """,
                (users, users),
            )
            cursor.execute(
                """
                DELETE FROM synergia.user_permission_assignments
                WHERE user_id = ANY(%s)
                """,
                (users,),
            )
            if "group" in ids:
                cursor.execute(
                    "DELETE FROM synergia.group_role_assignments WHERE group_id = %s",
                    (ids["group"],),
                )
                cursor.execute(
                    "DELETE FROM synergia.user_group_memberships WHERE group_id = %s",
                    (ids["group"],),
                )
            cursor.execute(
                "DELETE FROM synergia.user_role_assignments WHERE user_id = ANY(%s)",
                (users,),
            )
            if "custom_role" in ids:
                cursor.execute(
                    "DELETE FROM synergia.role_permissions WHERE role_id = %s",
                    (ids["custom_role"],),
                )
                cursor.execute(
                    "DELETE FROM synergia.roles WHERE id = %s",
                    (ids["custom_role"],),
                )
            if "group" in ids:
                cursor.execute(
                    "DELETE FROM synergia.identity_groups WHERE id = %s",
                    (ids["group"],),
                )
            cursor.execute(
                "DELETE FROM synergia.identity_users WHERE id = ANY(%s)",
                (users,),
            )
            cursor.execute(
                "DELETE FROM synergia.iam_organizations WHERE id = %s",
                (ids["organization"],),
            )
        finally:
            for table, trigger in reversed(
                (
                    ("identity_access_events", "trg_identity_events_append_only"),
                    ("identity_users", "trg_identity_users_no_delete"),
                    ("identity_groups", "trg_identity_groups_no_delete"),
                    ("roles", "trg_roles_no_delete"),
                    ("iam_organizations", "trg_iam_organizations_no_delete"),
                )
            ):
                cursor.execute(f"ALTER TABLE synergia.{table} ENABLE TRIGGER {trigger}")
        connection.commit()


def test_access_control_contracts_and_effective_permissions(monkeypatch) -> None:
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv("SYNERGIA_TRUSTED_ACTOR_HEADER_ENABLED", "true")
    database_url = os.environ["DATABASE_URL"]
    suffix = uuid4().hex[:10]
    ids = _bootstrap(database_url, suffix)
    headers = {"X-Actor-Id": str(ids["actor"])}
    try:
        with TestClient(app) as client:
            catalog = client.get("/admin/access/permissions", headers=headers)
            assert catalog.status_code == 200
            assert len(catalog.json()) == 14
            assert {item["catalog_version"] for item in catalog.json()} == {"1.0.0"}
            assert all(item["is_reserved"] for item in catalog.json())

            group = client.post(
                "/admin/access/groups",
                headers=headers,
                json={
                    "group_name": f"Quality {suffix}",
                    "external_reference": f"synthetic-{suffix}",
                    "reason": "integration group creation",
                },
            )
            assert group.status_code == 201, group.text
            ids["group"] = UUID(group.json()["id"])

            updated = client.patch(
                f"/admin/access/groups/{ids['group']}",
                headers=headers,
                json={
                    "version": group.json()["version"],
                    "group_name": f"Quality Updated {suffix}",
                    "reason": "integration group update",
                },
            )
            assert updated.status_code == 200

            deactivated_group = client.post(
                f"/admin/access/groups/{ids['group']}/deactivate",
                headers=headers,
                json={
                    "version": updated.json()["version"],
                    "reason": "integration group deactivation",
                },
            )
            assert deactivated_group.status_code == 200
            activated_group = client.post(
                f"/admin/access/groups/{ids['group']}/activate",
                headers=headers,
                json={
                    "version": deactivated_group.json()["version"],
                    "reason": "integration group activation",
                },
            )
            assert activated_group.status_code == 200

            custom_role = client.post(
                "/admin/access/roles",
                headers=headers,
                json={
                    "role_key": f"custom_{suffix}",
                    "description": "Synthetic custom role",
                    "reason": "integration role creation",
                },
            )
            assert custom_role.status_code == 201
            ids["custom_role"] = UUID(custom_role.json()["id"])
            role_detail = client.get(
                f"/admin/access/roles/{ids['custom_role']}", headers=headers
            )
            assert role_detail.status_code == 200
            updated_role = client.patch(
                f"/admin/access/roles/{ids['custom_role']}",
                headers=headers,
                json={
                    "version": role_detail.json()["version"],
                    "description": "Updated synthetic role",
                    "reason": "integration role update",
                },
            )
            assert updated_role.status_code == 200
            deactivated_role = client.post(
                f"/admin/access/roles/{ids['custom_role']}/deactivate",
                headers=headers,
                json={
                    "version": updated_role.json()["version"],
                    "reason": "integration role deactivation",
                },
            )
            assert deactivated_role.status_code == 200
            activated_role = client.post(
                f"/admin/access/roles/{ids['custom_role']}/activate",
                headers=headers,
                json={
                    "version": deactivated_role.json()["version"],
                    "reason": "integration role activation",
                },
            )
            assert activated_role.status_code == 200

            association_requests = [
                (
                    f"/admin/access/users/{ids['subject']}/groups/{ids['group']}",
                    {"reason": "group membership"},
                ),
                (
                    f"/admin/access/groups/{ids['group']}/roles/{ids['consulta_role']}",
                    {
                        "reason": "group role grant",
                        "organization_id": str(ids["organization"]),
                    },
                ),
                (
                    f"/admin/access/users/{ids['subject']}/roles/{ids['gestor_role']}",
                    {"reason": "direct role grant"},
                ),
                (
                    f"/admin/access/users/{ids['subject']}/permissions/{ids['report_permission']}",
                    {
                        "reason": "exceptional direct permission",
                        "organization_id": str(ids["organization"]),
                    },
                ),
                (
                    f"/admin/access/users/{ids['subject']}/permissions/{ids['access_admin_permission']}",
                    {
                        "reason": "organization scoped administration",
                        "organization_id": str(ids["organization"]),
                    },
                ),
                (
                    f"/admin/access/roles/{ids['custom_role']}/permissions/{ids['report_permission']}",
                    {"reason": "custom role permission"},
                ),
            ]
            for path, payload in association_requests:
                granted = client.put(path, headers=headers, json=payload)
                assert granted.status_code == 200, granted.text
                duplicate = client.put(path, headers=headers, json=payload)
                assert duplicate.status_code == 200
                assert duplicate.json()["idempotent"] is True

            effective = client.get(
                f"/admin/access/users/{ids['subject']}/effective-permissions",
                headers=headers,
                params={"organization_id": str(ids["organization"])},
            )
            assert effective.status_code == 200
            sources = {item["source"] for item in effective.json()["permissions"]}
            assert sources == {"direct", "role", "group"}
            keys = {item["permission_key"] for item in effective.json()["permissions"]}
            assert {"report.export", "dashboard.read"} <= keys

            subject_headers = {"X-Actor-Id": str(ids["subject"])}
            for protected_path in ("/admin/access/groups", "/admin/users"):
                scoped_admin = client.get(protected_path, headers=subject_headers)
                assert scoped_admin.status_code == 403

            direct_admin_path = (
                f"/admin/access/users/{ids['subject']}/permissions/"
                f"{ids['access_admin_permission']}"
            )
            global_direct_admin = client.put(
                direct_admin_path,
                headers=headers,
                json={"reason": "global direct administration"},
            )
            assert global_direct_admin.status_code == 200
            for protected_path in ("/admin/access/groups", "/admin/users"):
                direct_admin = client.get(protected_path, headers=subject_headers)
                assert direct_admin.status_code == 200
            revoke_direct_admin = client.request(
                "DELETE",
                direct_admin_path,
                headers=headers,
                json={"reason": "replace direct administration"},
            )
            assert revoke_direct_admin.status_code == 200

            group_admin_path = (
                f"/admin/access/groups/{ids['group']}/roles/{ids['admin_role']}"
            )
            global_group_admin = client.put(
                group_admin_path,
                headers=headers,
                json={"reason": "global group administration"},
            )
            assert global_group_admin.status_code == 200
            for protected_path in ("/admin/access/groups", "/admin/users"):
                group_admin = client.get(protected_path, headers=subject_headers)
                assert group_admin.status_code == 200
            revoke_group_admin = client.request(
                "DELETE",
                group_admin_path,
                headers=headers,
                json={"reason": "remove group administration"},
            )
            assert revoke_group_admin.status_code == 200

            invalid_scope = client.put(
                f"/admin/access/users/{ids['subject']}/roles/{ids['consulta_role']}",
                headers=headers,
                json={
                    "reason": "invalid organization scope",
                    "organization_id": str(uuid4()),
                },
            )
            assert invalid_scope.status_code == 409
            assert invalid_scope.json()["error"]["code"] == "invalid_organization_scope"

            associations = client.get(
                "/admin/access/associations?page=1&page_size=3", headers=headers
            )
            assert associations.status_code == 200
            assert associations.json()["page_size"] == 3
            assert associations.json()["total"] >= 6
            assert associations.json()["sort"] == "granted_at,kind,id"

            last_admin = client.request(
                "DELETE",
                f"/admin/access/users/{ids['actor']}/roles/{ids['admin_role']}",
                headers=headers,
                json={"reason": "must preserve administrator"},
            )
            assert last_admin.status_code == 409
            assert last_admin.json()["error"]["code"] == "last_active_admin"

            revoked = client.request(
                "DELETE",
                association_requests[0][0],
                headers=headers,
                json={"reason": "membership rotation"},
            )
            assert revoked.status_code == 200
            repeated = client.request(
                "DELETE",
                association_requests[0][0],
                headers=headers,
                json={"reason": "membership rotation"},
            )
            assert repeated.status_code == 200
            assert repeated.json()["idempotent"] is True

            denied = client.get(
                "/admin/access/groups",
                headers={"X-Actor-Id": str(ids["subject"])},
            )
            assert denied.status_code == 403

        with psycopg.connect(database_url) as connection:
            events = connection.execute(
                """
                SELECT event_key FROM synergia.identity_access_events
                WHERE actor_user_id = %s AND event_key LIKE 'access.%%'
                """,
                (ids["actor"],),
            ).fetchall()
            assert len(events) >= 8
            group_update = connection.execute(
                """
                SELECT payload
                FROM synergia.identity_access_events
                WHERE actor_user_id = %s
                  AND event_key = 'access.group_updated'
                ORDER BY id DESC
                LIMIT 1
                """,
                (ids["actor"],),
            ).fetchone()[0]
            assert group_update["before"]["group_name"] == f"Quality {suffix}"
            assert group_update["after"]["group_name"] == (
                f"Quality Updated {suffix}"
            )
            assert group_update["before"]["version"] < group_update["after"]["version"]

            scoped_event = connection.execute(
                """
                SELECT organization_id, payload
                FROM synergia.identity_access_events
                WHERE actor_user_id = %s
                  AND event_key = 'access.association_granted'
                  AND organization_id = %s
                ORDER BY id
                LIMIT 1
                """,
                (ids["actor"], ids["organization"]),
            ).fetchone()
            assert scoped_event[0] == ids["organization"]
            assert scoped_event[1]["change"] == "granted"
    finally:
        _cleanup(database_url, ids)


def test_migration_0015_rollback_preserves_preexisting_access_data() -> None:
    database_url = os.environ["DATABASE_URL"]
    permission_key = f"legacy_{uuid4().hex[:10]}.read"
    preexisting_role_key = f"legacy_{uuid4().hex[:10]}"
    migration_role_key = f"migration_{uuid4().hex[:10]}"
    rollback_sql = (
        ROOT / "database/rollbacks/0015_create_access_control_contracts.down.sql"
    ).read_text(encoding="utf-8")

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        try:
            cursor.execute(
                """
                INSERT INTO synergia.roles (
                    role_key, description, preexisting_in_0015
                ) VALUES (%s, 'Pre-migration role', true)
                RETURNING id
                """,
                (preexisting_role_key,),
            )
            preexisting_role_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO synergia.roles (
                    role_key, description, preexisting_in_0015
                ) VALUES (%s, 'Migration role', false)
                RETURNING id
                """,
                (migration_role_key,),
            )
            migration_role_id = cursor.fetchone()[0]
            cursor.execute(
                """
                SELECT normalized_key
                FROM synergia.roles
                WHERE normalized_key = ANY(%s) AND NOT preexisting_in_0015
                """,
                (["admin", "gestor", "analista", "operador", "consulta"],),
            )
            seeded_role_keys = {row[0] for row in cursor.fetchall()}
            assert seeded_role_keys == {
                "admin",
                "gestor",
                "analista",
                "operador",
                "consulta",
            }
            cursor.execute(
                """
                INSERT INTO synergia.permissions (
                    permission_key, resource_type, description,
                    catalog_version, is_reserved, preexisting_in_0015
                ) VALUES (
                    %s, 'legacy', 'Pre-migration permission', '1.0.0', false, true
                )
                RETURNING id
                """,
                (permission_key,),
            )
            permission_id = cursor.fetchone()[0]
            cursor.execute(
                "SELECT id FROM synergia.roles WHERE normalized_key = 'admin'"
            )
            role_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO synergia.role_permissions (
                    role_id, permission_id, preexisting_in_0015
                ) VALUES (%s, %s, true)
                RETURNING granted_by_user_id, granted_at
                """,
                (role_id, permission_id),
            )
            _, granted_at = cursor.fetchone()

            cursor.execute(rollback_sql, prepare=False)

            cursor.execute(
                "SELECT permission_key FROM synergia.permissions WHERE id = %s",
                (permission_id,),
            )
            assert cursor.fetchone()[0] == permission_key
            cursor.execute(
                "SELECT role_key FROM synergia.roles WHERE id = %s",
                (preexisting_role_id,),
            )
            assert cursor.fetchone()[0] == preexisting_role_key
            cursor.execute(
                "SELECT 1 FROM synergia.roles WHERE id = %s",
                (migration_role_id,),
            )
            assert cursor.fetchone() is None
            cursor.execute(
                """
                SELECT normalized_key
                FROM synergia.roles
                WHERE normalized_key = ANY(%s)
                """,
                (list(seeded_role_keys),),
            )
            assert cursor.fetchall() == []
            cursor.execute(
                """
                SELECT granted_at
                FROM synergia.role_permissions
                WHERE role_id = %s AND permission_id = %s
                """,
                (role_id, permission_id),
            )
            assert cursor.fetchone()[0] == granted_at
        finally:
            connection.rollback()
