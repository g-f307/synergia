from __future__ import annotations

import argparse
import os
from uuid import UUID

import psycopg
from argon2 import PasswordHasher

OPERATOR_ID = UUID("63000000-0000-4000-8000-000000000001")
READER_ID = UUID("63000000-0000-4000-8000-000000000002")
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revoke-email")
    args = parser.parse_args()
    revoke(args.revoke_email) if args.revoke_email else bootstrap()


if __name__ == "__main__":
    main()
