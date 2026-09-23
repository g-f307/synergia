from __future__ import annotations

import argparse
import os
from uuid import UUID, uuid4

import psycopg
from argon2 import PasswordHasher

OPERATOR_ID = UUID("63000000-0000-4000-8000-000000000001")
READER_ID = UUID("63000000-0000-4000-8000-000000000002")
MANAGER_ID = UUID("63000000-0000-4000-8000-000000000003")
ADMIN_ID = UUID("63000000-0000-4000-8000-000000000004")
ORGANIZATION_A = UUID("63000000-0000-4000-8000-000000000011")
ORGANIZATION_B = UUID("63000000-0000-4000-8000-000000000012")


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


def bootstrap() -> None:
    password = os.getenv("E2E_PASSWORD", "synthetic-e2e-password-63")
    password_hash = PasswordHasher().hash(password)
    users = (
        (OPERATOR_ID, "E2E Operator", "pt-BR", "operator.e2e@example.invalid"),
        (READER_ID, "E2E Reader", "en-US", "reader.e2e@example.invalid"),
        (MANAGER_ID, "E2E Manager", "en-US", "manager.e2e@example.invalid"),
        (ADMIN_ID, "E2E Administrator", "pt-BR", "admin.e2e@example.invalid"),
    )
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO synergia.iam_organizations
                (id, organization_code, display_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                organization_code = EXCLUDED.organization_code,
                display_name = EXCLUDED.display_name,
                is_active = true,
                deactivated_at = NULL,
                updated_at = now()
            """,
            (
                (ORGANIZATION_A, "syn-org-001", "Synthetic Organization A"),
                (ORGANIZATION_B, "syn-org-002", "Synthetic Organization B"),
            ),
        )
        for user_id, name, locale, email in users:
            cursor.execute(
                """
                INSERT INTO synergia.identity_users
                    (id, status, display_name, local_password_hash, locale)
                VALUES (%s, 'active', %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    status = 'active', display_name = EXCLUDED.display_name,
                    local_password_hash = EXCLUDED.local_password_hash,
                    locale = EXCLUDED.locale, deactivated_at = NULL,
                    updated_at = now()
                """,
                (user_id, name, password_hash, locale),
            )
            cursor.execute(
                """
                INSERT INTO synergia.user_emails
                    (user_id, email, is_primary, is_verified, verified_at)
                VALUES (%s, %s, true, true, now())
                ON CONFLICT (normalized_email) DO UPDATE SET
                    user_id = EXCLUDED.user_id, disabled_at = NULL
                """,
                (user_id, email),
            )
        cursor.execute(
            """
            INSERT INTO synergia.user_role_assignments
                (user_id, role_id, organization_id)
            SELECT %s, id, %s FROM synergia.roles
            WHERE normalized_key = 'operador'
            ON CONFLICT (user_id, role_id, organization_id)
                WHERE organization_id IS NOT NULL AND revoked_at IS NULL DO NOTHING
            """,
            (OPERATOR_ID, ORGANIZATION_A),
        )
        cursor.execute(
            """
            INSERT INTO synergia.user_role_assignments
                (user_id, role_id, organization_id)
            SELECT %s, id, %s FROM synergia.roles
            WHERE normalized_key = 'consulta'
            ON CONFLICT (user_id, role_id, organization_id)
                WHERE organization_id IS NOT NULL AND revoked_at IS NULL DO NOTHING
            """,
            (READER_ID, ORGANIZATION_B),
        )
        cursor.execute(
            """
            INSERT INTO synergia.user_role_assignments
                (user_id, role_id, organization_id)
            SELECT %s, id, %s FROM synergia.roles
            WHERE normalized_key = 'gestor'
            ON CONFLICT (user_id, role_id, organization_id)
                WHERE organization_id IS NOT NULL AND revoked_at IS NULL DO NOTHING
            """,
            (MANAGER_ID, ORGANIZATION_A),
        )
        cursor.execute(
            """
            INSERT INTO synergia.user_role_assignments (user_id, role_id)
            SELECT %s, id FROM synergia.roles WHERE normalized_key = 'admin'
            ON CONFLICT (user_id, role_id)
                WHERE organization_id IS NULL AND revoked_at IS NULL DO NOTHING
            """,
            (ADMIN_ID,),
        )
    print("E2E users and organizations are ready (no credentials emitted).")


def revoke(email: str) -> None:
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE synergia.identity_sessions s
            SET status = 'revoked', revoked_at = now(),
                revocation_reason = 'e2e_expiration'
            FROM synergia.user_emails e
            WHERE e.user_id = s.user_id AND e.normalized_email = lower(btrim(%s))
              AND s.status = 'active'
            """,
            (email,),
        )


def emit_execution_notification() -> None:
    execution_id = f"exec-template-e2e-{uuid4().hex[:12]}"
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO synergia.executions (
                   id, status, organization_id, initiated_by_user_id,
                   state_changed_by_type, state_changed_by, state_change_reason
               ) VALUES (%s, 'completed', %s, %s, 'system',
                         'notification-template-e2e', 'synthetic_event')""",
            (execution_id, ORGANIZATION_A, OPERATOR_ID),
        )
    print(execution_id)


def assert_admin_audit(email: str) -> None:
    expected = [
        ("user.admin_created", "identity_user"),
        ("access.role_created", "role"),
        ("access.association_granted", "role_permission"),
        ("access.group_created", "identity_group"),
        ("access.association_granted", "user_group"),
        ("access.association_granted", "group_role"),
        ("user.admin_updated", "identity_user"),
        ("user.admin_block", "identity_user"),
        ("user.admin_unblock", "identity_user"),
        ("user.admin_deactivate", "identity_user"),
        ("user.admin_reactivate", "identity_user"),
        ("access.association_revoked", "user_group"),
    ]
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT event.event_key, event.entity_type, event.actor_user_id
            FROM synergia.identity_access_events event
            WHERE event.id >= (
                SELECT min(created.id)
                FROM synergia.identity_access_events created
                JOIN synergia.user_emails email
                  ON email.user_id = created.subject_user_id
                WHERE email.normalized_email = lower(btrim(%s))
                  AND created.event_key = 'user.admin_created'
            )
              AND (
                event.event_key LIKE 'user.admin_%%'
                OR event.event_key LIKE 'access.%%'
              )
            ORDER BY event.id
            """,
            (email,),
        )
        events = cursor.fetchall()
    mutations = [(event[0], event[1]) for event in events]
    position = 0
    for mutation in mutations:
        if position < len(expected) and mutation == expected[position]:
            position += 1
    if position != len(expected):
        raise RuntimeError(
            "administrative audit is incomplete: "
            f"expected ordered events {expected}, received {mutations}"
        )
    if any(actor_id != ADMIN_ID for _event_key, _entity_type, actor_id in events):
        raise RuntimeError("administrative audit contains an unexpected actor")
    print(f"Administrative audit verified: {len(expected)} ordered mutations.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revoke-email")
    parser.add_argument("--emit-execution-notification", action="store_true")
    parser.add_argument("--assert-admin-audit")
    args = parser.parse_args()
    if args.revoke_email:
        revoke(args.revoke_email)
    elif args.emit_execution_notification:
        emit_execution_notification()
    elif args.assert_admin_audit:
        assert_admin_audit(args.assert_admin_audit)
    else:
        bootstrap()


if __name__ == "__main__":
    main()
