import hashlib
import os

import psycopg
import pytest
from psycopg import errors

pytestmark = pytest.mark.integration


def _create_user(cursor, suffix: str, status: str = "active") -> str:
    cursor.execute(
        """
        INSERT INTO synergia.identity_users (
            status, display_name, deactivated_at
        ) VALUES (
            %s, %s,
            CASE WHEN %s = 'inactive' THEN now() ELSE NULL END
        )
        RETURNING id;
        """,
        (status, f"Synthetic User {suffix}", status),
    )
    return str(cursor.fetchone()[0])


def _create_role(cursor, key: str = "analista") -> str:
    cursor.execute(
        "INSERT INTO synergia.roles (role_key) VALUES (%s) RETURNING id;",
        (key,),
    )
    return str(cursor.fetchone()[0])


def _insert_session(cursor, user_id: str) -> str:
    cursor.execute(
        """
        INSERT INTO synergia.identity_sessions (
            user_id, authentication_method,
            idle_expires_at, absolute_expires_at
        ) VALUES (%s, 'synthetic-test', now() + interval '8 hours',
                  now() + interval '24 hours')
        RETURNING id;
        """,
        (user_id,),
    )
    return str(cursor.fetchone()[0])


def test_supports_local_and_external_identity_with_multiple_emails() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            user_id = _create_user(cursor, "identity")
            cursor.execute(
                """
                UPDATE synergia.identity_users
                SET local_password_hash =
                    '$argon2id$v=19$m=65536,t=3,p=4$synthetic$safehash'
                WHERE id = %s;
                """,
                (user_id,),
            )
            cursor.execute(
                """
                INSERT INTO synergia.user_external_identities (
                    user_id, provider_key, subject_identifier
                ) VALUES (%s, 'corporate-oidc', 'synthetic-subject');
                """,
                (user_id,),
            )
            cursor.execute(
                """
                INSERT INTO synergia.user_emails (user_id, email, is_primary)
                VALUES
                    (%s, 'primary@example.invalid', true),
                    (%s, 'secondary@example.invalid', false);
                """,
                (user_id, user_id),
            )
            cursor.execute(
                """
                SELECT count(*), min(normalized_email), max(normalized_email)
                FROM synergia.user_emails
                WHERE user_id = %s;
                """,
                (user_id,),
            )
            assert cursor.fetchone() == (
                2,
                "primary@example.invalid",
                "secondary@example.invalid",
            )
        connection.rollback()


def test_rejects_case_insensitive_duplicate_email_role_and_permission() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            first_user = _create_user(cursor, "email-a")
            second_user = _create_user(cursor, "email-b")
            cursor.execute(
                "INSERT INTO synergia.user_emails (user_id, email) VALUES (%s, %s);",
                (first_user, "CaseSensitive@Example.Invalid"),
            )

            cursor.execute("SAVEPOINT duplicate_email")
            with pytest.raises(errors.UniqueViolation):
                cursor.execute(
                    """
                    INSERT INTO synergia.user_emails (user_id, email)
                    VALUES (%s, %s);
                    """,
                    (second_user, "  casesensitive@example.invalid  "),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT duplicate_email")

            _create_role(cursor, "Gestor")
            cursor.execute("SAVEPOINT duplicate_role")
            with pytest.raises(errors.UniqueViolation):
                _create_role(cursor, " gestor ")
            cursor.execute("ROLLBACK TO SAVEPOINT duplicate_role")

            cursor.execute(
                """
                INSERT INTO synergia.permissions (permission_key, resource_type)
                VALUES ('artifact.export', 'artifact');
                """
            )
            cursor.execute("SAVEPOINT duplicate_permission")
            with pytest.raises(errors.UniqueViolation):
                cursor.execute(
                    """
                    INSERT INTO synergia.permissions
                        (permission_key, resource_type)
                    VALUES ('ARTIFACT.EXPORT', 'artifact');
                    """
                )
            cursor.execute("ROLLBACK TO SAVEPOINT duplicate_permission")
        connection.rollback()


def test_rejects_duplicate_group_role_and_permission_associations() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            user_id = _create_user(cursor, "associations")
            cursor.execute(
                """
                INSERT INTO synergia.identity_groups (group_name)
                VALUES ('Synthetic Group') RETURNING id;
                """
            )
            group_id = str(cursor.fetchone()[0])
            role_id = _create_role(cursor)
            cursor.execute(
                """
                INSERT INTO synergia.permissions (permission_key, resource_type)
                VALUES ('business.read', 'business') RETURNING id;
                """
            )
            permission_id = str(cursor.fetchone()[0])
            cursor.execute(
                """
                INSERT INTO synergia.user_group_memberships (user_id, group_id)
                VALUES (%s, %s);
                """,
                (user_id, group_id),
            )
            cursor.execute(
                """
                INSERT INTO synergia.user_role_assignments (user_id, role_id)
                VALUES (%s, %s);
                """,
                (user_id, role_id),
            )
            cursor.execute(
                """
                INSERT INTO synergia.role_permissions (role_id, permission_id)
                VALUES (%s, %s);
                """,
                (role_id, permission_id),
            )

            duplicate_statements = [
                (
                    "INSERT INTO synergia.user_group_memberships "
                    "(user_id, group_id) VALUES (%s, %s)",
                    (user_id, group_id),
                ),
                (
                    "INSERT INTO synergia.user_role_assignments "
                    "(user_id, role_id) VALUES (%s, %s)",
                    (user_id, role_id),
                ),
                (
                    "INSERT INTO synergia.role_permissions "
                    "(role_id, permission_id) VALUES (%s, %s)",
                    (role_id, permission_id),
                ),
            ]
            for index, (statement, parameters) in enumerate(duplicate_statements):
                cursor.execute(f"SAVEPOINT duplicate_association_{index}")
                with pytest.raises(errors.UniqueViolation):
                    cursor.execute(statement, parameters)
                cursor.execute(f"ROLLBACK TO SAVEPOINT duplicate_association_{index}")
        connection.rollback()


def test_preserves_audit_history_and_blocks_physical_identity_deletion() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            user_id = _create_user(cursor, "audit")
            cursor.execute(
                """
                SELECT count(*) FROM synergia.identity_access_events
                WHERE subject_user_id = %s AND event_key = 'user.created';
                """,
                (user_id,),
            )
            assert cursor.fetchone()[0] == 1

            cursor.execute("SAVEPOINT forbidden_delete")
            with pytest.raises(errors.RestrictViolation):
                cursor.execute(
                    "DELETE FROM synergia.identity_users WHERE id = %s;", (user_id,)
                )
            cursor.execute("ROLLBACK TO SAVEPOINT forbidden_delete")

            cursor.execute(
                """
                SELECT count(*) FROM synergia.identity_access_events
                WHERE subject_user_id = %s;
                """,
                (user_id,),
            )
            assert cursor.fetchone()[0] >= 1

            cursor.execute("SAVEPOINT immutable_event")
            with pytest.raises(errors.RestrictViolation):
                cursor.execute(
                    """
                    DELETE FROM synergia.identity_access_events
                    WHERE subject_user_id = %s;
                    """,
                    (user_id,),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT immutable_event")
        connection.rollback()


def test_rejects_invalid_session_owners_and_revokes_on_deactivation() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SAVEPOINT missing_user")
            with pytest.raises(errors.ForeignKeyViolation):
                _insert_session(cursor, "00000000-0000-0000-0000-000000000000")
            cursor.execute("ROLLBACK TO SAVEPOINT missing_user")

            inactive_user = _create_user(cursor, "inactive", status="inactive")
            cursor.execute("SAVEPOINT inactive_user")
            with pytest.raises(errors.CheckViolation):
                _insert_session(cursor, inactive_user)
            cursor.execute("ROLLBACK TO SAVEPOINT inactive_user")

            active_user = _create_user(cursor, "deactivate")
            session_id = _insert_session(cursor, active_user)
            cursor.execute(
                """
                UPDATE synergia.identity_users
                SET status = 'inactive', deactivated_at = now()
                WHERE id = %s;
                """,
                (active_user,),
            )
            cursor.execute(
                """
                SELECT status, revocation_reason
                FROM synergia.identity_sessions WHERE id = %s;
                """,
                (session_id,),
            )
            assert cursor.fetchone() == ("revoked", "user_status_changed")
        connection.rollback()


def test_enforces_organization_scope_and_global_assignment_uniqueness() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            user_id = _create_user(cursor, "scope")
            role_id = _create_role(cursor, "operador")
            cursor.execute(
                """
                INSERT INTO synergia.iam_organizations (
                    organization_code, display_name
                ) VALUES ('org-synthetic', 'Synthetic Organization')
                RETURNING id;
                """
            )
            organization_id = str(cursor.fetchone()[0])
            cursor.execute(
                """
                INSERT INTO synergia.user_role_assignments
                    (user_id, role_id, organization_id)
                VALUES (%s, %s, NULL), (%s, %s, %s);
                """,
                (user_id, role_id, user_id, role_id, organization_id),
            )

            cursor.execute("SAVEPOINT duplicate_global_scope")
            with pytest.raises(errors.UniqueViolation):
                cursor.execute(
                    """
                    INSERT INTO synergia.user_role_assignments
                        (user_id, role_id, organization_id)
                    VALUES (%s, %s, NULL);
                    """,
                    (user_id, role_id),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT duplicate_global_scope")

            cursor.execute("SAVEPOINT invalid_organization")
            with pytest.raises(errors.ForeignKeyViolation):
                cursor.execute(
                    """
                    INSERT INTO synergia.user_role_assignments
                        (user_id, role_id, organization_id)
                    VALUES (%s, %s, %s);
                    """,
                    (user_id, role_id, "00000000-0000-0000-0000-000000000000"),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT invalid_organization")
        connection.rollback()


def test_persists_only_non_reversible_refresh_token_hash() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            user_id = _create_user(cursor, "refresh")
            session_id = _insert_session(cursor, user_id)
            plaintext_token = "synthetic-refresh-token-never-store"
            token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()
            cursor.execute(
                """
                INSERT INTO synergia.session_refresh_tokens (
                    session_id, family_id, token_hash, expires_at
                ) VALUES (%s, gen_random_uuid(), %s, now() + interval '24 hours')
                RETURNING token_hash;
                """,
                (session_id, token_hash),
            )
            assert cursor.fetchone()[0] == token_hash

            cursor.execute("SAVEPOINT plaintext_refresh")
            with pytest.raises(errors.CheckViolation):
                cursor.execute(
                    """
                    INSERT INTO synergia.session_refresh_tokens (
                        session_id, family_id, token_hash, expires_at
                    ) VALUES (
                        %s, gen_random_uuid(), %s, now() + interval '24 hours'
                    );
                    """,
                    (session_id, plaintext_token),
                )
            cursor.execute("ROLLBACK TO SAVEPOINT plaintext_refresh")

            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'synergia'
                  AND table_name = 'session_refresh_tokens';
                """
            )
            columns = {row[0] for row in cursor.fetchall()}
            assert "token" not in columns
            assert "token_hash" in columns
        connection.rollback()


def test_identity_indexes_cover_login_associations_and_session_validation() -> None:
    expected_indexes = {
        "idx_external_identities_login",
        "idx_user_emails_login",
        "idx_user_group_memberships_group",
        "idx_user_role_assignments_user",
        "idx_role_permissions_permission",
        "idx_identity_sessions_user_active",
        "idx_identity_sessions_validation",
        "idx_refresh_tokens_validation",
        "idx_identity_events_subject",
    }
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'synergia';"
            )
            indexes = {row[0] for row in cursor.fetchall()}
            assert expected_indexes <= indexes
