from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.authorization import ActorContext
from app.email_delivery import EmailDeliveryRepository
from app.errors import ApiError
from app.notification_templates import (
    DraftCreate,
    DraftUpdate,
    NotificationTemplateRepository,
    TransitionRequest,
)

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def _database_url(database: str) -> str:
    parameters = conninfo_to_dict(os.environ["DATABASE_URL"])
    parameters["dbname"] = database
    return make_conninfo(**parameters)


def _create_database(name: str) -> None:
    parameters = conninfo_to_dict(os.environ["DATABASE_URL"])
    parameters["dbname"] = "postgres"
    with psycopg.connect(make_conninfo(**parameters), autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')


def _drop_database(name: str) -> None:
    parameters = conninfo_to_dict(os.environ["DATABASE_URL"])
    parameters["dbname"] = "postgres"
    with psycopg.connect(make_conninfo(**parameters), autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (name,),
        )
        connection.execute(f'DROP DATABASE IF EXISTS "{name}"')


@pytest.fixture
def isolated_template_database() -> str:
    database_name = f"synergia_template_rollback_{uuid4().hex[:10]}"
    _create_database(database_name)
    database_url = _database_url(database_name)
    try:
        with psycopg.connect(database_url) as connection:
            for migration in sorted((ROOT / "database/migrations").glob("*.sql")):
                connection.execute(migration.read_text(encoding="utf-8"))
        yield database_url
    finally:
        _drop_database(database_name)


def test_migration_activates_only_latest_legacy_template_version() -> None:
    database_name = f"synergia_template_upgrade_{uuid4().hex[:10]}"
    _create_database(database_name)
    database_url = _database_url(database_name)
    try:
        migrations = sorted((ROOT / "database/migrations").glob("*.sql"))
        with psycopg.connect(database_url) as connection:
            for migration in migrations:
                if migration.name.startswith("0030_"):
                    break
                connection.execute(migration.read_text(encoding="utf-8"))
            connection.execute(
                """INSERT INTO synergia.notification_template_versions (
                     notification_type, template_version,
                     required_permission, resource_type, created_at
                   ) VALUES (
                     'execution.completed', '2.0.0',
                     'execution.read', 'execution', now() + interval '1 second'
                   )"""
            )
            connection.execute(
                """INSERT INTO synergia.notification_templates (
                     notification_type, template_version, locale,
                     title_template, body_template
                   ) VALUES (
                     'execution.completed', '2.0.0', 'pt-BR',
                     'Concluída v2', 'Execução {execution_id} concluída v2.'
                   )"""
            )
            connection.execute(
                """INSERT INTO synergia.email_notification_templates (
                     notification_type, template_version, locale,
                     subject_template, body_template
                   ) VALUES (
                     'execution.completed', '2.0.0', 'pt-BR',
                     'Concluída v2', 'Execução {execution_id} concluída v2.'
                   )"""
            )
            migration = next(
                item for item in migrations if item.name.startswith("0030_")
            )
            connection.execute(migration.read_text(encoding="utf-8"))

            for channel in ("in_app", "email"):
                active = connection.execute(
                    """SELECT r.version_label
                       FROM synergia.notification_template_activations a
                       JOIN synergia.notification_template_revisions r
                         ON r.id = a.revision_id
                       WHERE a.notification_type = 'execution.completed'
                         AND a.channel = %s AND a.locale = 'pt-BR'
                         AND a.deactivated_at IS NULL""",
                    (channel,),
                ).fetchall()
                assert active == [("2.0.0",)]
                history = connection.execute(
                    """SELECT r.version_label
                       FROM synergia.notification_template_revisions r
                       WHERE r.notification_type = 'execution.completed'
                         AND r.channel = %s AND r.locale = 'pt-BR'
                       ORDER BY r.version_number""",
                    (channel,),
                ).fetchall()
                assert history == [("1.0.0",), ("2.0.0",)]
    finally:
        _drop_database(database_name)


def test_versioned_template_lifecycle_is_immutable_audited_and_used_by_events(
    isolated_template_database: str,
) -> None:
    database_url = isolated_template_database
    actor_id, session_id, token_id, correlation_id, organization_id = (
        uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    )
    suffix = uuid4().hex[:10]
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO synergia.identity_users
                   (id, status, display_name, locale)
               VALUES (%s, 'active', %s, 'pt-BR')""",
            (actor_id, f"Template administrator {suffix}"),
        )
        cursor.execute(
            """INSERT INTO synergia.iam_organizations
                   (id, organization_code, display_name)
               VALUES (%s, %s, %s)""",
            (organization_id, f"template-{suffix}", f"Template org {suffix}"),
        )
        now = datetime.now(UTC)
        cursor.execute(
            """INSERT INTO synergia.identity_sessions (
                   id, user_id, idle_expires_at, absolute_expires_at,
                   authentication_method
               ) VALUES (%s, %s, %s, %s, 'synthetic-test')""",
            (session_id, actor_id, now + timedelta(hours=1), now + timedelta(days=1)),
        )

    actor = ActorContext(
        user_id=actor_id,
        session_id=session_id,
        token_id=token_id,
        permissions={"access.admin": frozenset({None})},
        correlation_id=correlation_id,
    )
    repository = NotificationTemplateRepository(database_url)
    first = repository.create(
        DraftCreate(
            notification_type="execution.completed",
            channel="in_app",
            locale="pt-BR",
            title_template=f"Concluída {suffix}",
            body_template="Primeira versão para {execution_id}.",
            reason="homologação da primeira versão",
        ),
        actor,
    )
    updated = repository.update(
        first["id"],
        DraftUpdate(
            row_version=first["row_version"],
            title_template=f"Concluída {suffix}",
            body_template="Versão homologada para {execution_id}.",
            reason="ajuste antes da publicação",
        ),
        actor,
    )
    published = repository.publish(
        first["id"],
        TransitionRequest(
            row_version=updated["row_version"], reason="publicação homologada"
        ),
        actor,
    )

    execution_one = f"exec-template-{suffix}-one"
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO synergia.executions (
                   id, status, organization_id, initiated_by_user_id,
                   initiated_by_session_id, correlation_id
               ) VALUES (%s, 'completed', %s, %s, %s, %s)""",
            (
                execution_one,
                organization_id,
                actor_id,
                session_id,
                correlation_id,
            ),
        )
        cursor.execute(
            """SELECT template_revision_id
               FROM synergia.notifications WHERE resource_id = %s""",
            (execution_one,),
        )
        assert cursor.fetchone()[0] == published["id"]

    second = repository.create(
        DraftCreate(
            notification_type="execution.completed",
            channel="in_app",
            locale="pt-BR",
            title_template=f"Nova concluída {suffix}",
            body_template="Nova versão para {execution_id}.",
            reason="nova revisão controlada",
        ),
        actor,
    )
    second_published = repository.publish(
        second["id"],
        TransitionRequest(
            row_version=second["row_version"], reason="substituição homologada"
        ),
        actor,
    )
    execution_two = f"exec-template-{suffix}-two"
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO synergia.executions (
                   id, status, organization_id, initiated_by_user_id,
                   initiated_by_session_id, correlation_id
               ) VALUES (%s, 'completed', %s, %s, %s, %s)""",
            (
                execution_two,
                organization_id,
                actor_id,
                session_id,
                correlation_id,
            ),
        )
        cursor.execute(
            """SELECT resource_id, template_revision_id
               FROM synergia.notifications
               WHERE resource_id IN (%s, %s) ORDER BY resource_id""",
            (execution_one, execution_two),
        )
        revisions = dict(cursor.fetchall())
        assert revisions[execution_one] == published["id"]
        assert revisions[execution_two] == second_published["id"]
        cursor.execute(
            """SELECT count(*) FROM synergia.notification_template_activations
               WHERE notification_type = 'execution.completed'
                 AND channel = 'in_app' AND locale = 'pt-BR'
                 AND deactivated_at IS NULL"""
        )
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            """SELECT event_type, actor_user_id, actor_session_id,
                      correlation_id, payload::text
               FROM synergia.notification_template_events
               WHERE revision_id IN (%s, %s) ORDER BY id""",
            (published["id"], second_published["id"]),
        )
        events = cursor.fetchall()
        assert {event[0] for event in events} >= {
            "template.draft_created",
            "template.draft_updated",
            "template.published",
            "template.deactivated",
        }
        assert all(
            event[1:4] == (actor_id, session_id, correlation_id)
            for event in events
        )
        assert all(
            "title" not in event[4] and "body" not in event[4]
            for event in events
        )

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        with pytest.raises(psycopg.DatabaseError):
            cursor.execute(
                """UPDATE synergia.notification_template_revisions
                   SET body_template = 'mutated' WHERE id = %s""",
                (published["id"],),
            )

    with pytest.raises(ApiError) as unsafe:
        repository.create(
            DraftCreate(
                notification_type="execution.completed",
                channel="in_app",
                locale="pt-BR",
                title_template="Unsafe",
                body_template="<script>alert(1)</script>",
                reason="negative security test",
            ),
            actor,
        )
    assert unsafe.value.code == "template_active_content"

    concurrent = [
        repository.create(
            DraftCreate(
                notification_type="execution.completed",
                channel="in_app",
                locale="pt-BR",
                title_template=f"Concorrente {suffix} {index}",
                body_template="Execução concorrente {execution_id}.",
                reason=f"rascunho concorrente {index}",
            ),
            actor,
        )
        for index in (1, 2)
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        published_concurrently = list(
            executor.map(
                lambda item: repository.publish(
                    item["id"],
                    TransitionRequest(
                        row_version=item["row_version"],
                        reason="publicação concorrente homologada",
                    ),
                    actor,
                ),
                concurrent,
            )
        )
    assert all(item["published_at"] is not None for item in published_concurrently)
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT revision_id
               FROM synergia.notification_template_activations
               WHERE notification_type = 'execution.completed'
                 AND channel = 'in_app' AND locale = 'pt-BR'
                 AND deactivated_at IS NULL"""
        )
        active = cursor.fetchall()
        assert len(active) == 1
        assert active[0][0] in {item["id"] for item in published_concurrently}


def test_rollback_preserves_new_templates_used_by_notification_and_delivery(
    isolated_template_database: str,
) -> None:
    database_url = isolated_template_database
    actor_id, session_id, token_id, correlation_id, organization_id = (
        uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    )
    suffix = uuid4().hex[:10]
    now = datetime.now(UTC)
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO synergia.identity_users
                   (id, status, display_name, locale)
               VALUES (%s, 'active', %s, 'pt-BR')""",
            (actor_id, f"Rollback template administrator {suffix}"),
        )
        cursor.execute(
            """INSERT INTO synergia.user_emails (
                   user_id, email, is_primary, is_verified, verified_at
               ) VALUES (%s, %s, true, true, now())""",
            (actor_id, f"rollback-{suffix}@example.test"),
        )
        cursor.execute(
            """INSERT INTO synergia.iam_organizations
                   (id, organization_code, display_name)
               VALUES (%s, %s, %s)""",
            (organization_id, f"rollback-{suffix}", f"Rollback org {suffix}"),
        )
        cursor.execute(
            """INSERT INTO synergia.identity_sessions (
                   id, user_id, idle_expires_at, absolute_expires_at,
                   authentication_method
               ) VALUES (%s, %s, %s, %s, 'synthetic-test')""",
            (session_id, actor_id, now + timedelta(hours=1), now + timedelta(days=1)),
        )

    actor = ActorContext(
        user_id=actor_id,
        session_id=session_id,
        token_id=token_id,
        permissions={"access.admin": frozenset({None})},
        correlation_id=correlation_id,
    )
    repository = NotificationTemplateRepository(database_url)
    published: dict[str, dict] = {}
    for channel in ("in_app", "email"):
        draft = repository.create(
            DraftCreate(
                notification_type="execution.completed",
                channel=channel,
                locale="pt-BR",
                title_template=f"Rollback {channel} {suffix}",
                body_template="Execução preservada {execution_id}.",
                reason="validar rollback compatível",
            ),
            actor,
        )
        published[channel] = repository.publish(
            draft["id"],
            TransitionRequest(
                row_version=draft["row_version"],
                reason="publicar para validar rollback",
            ),
            actor,
        )

    execution_id = f"exec-template-rollback-{suffix}"
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO synergia.executions (
                   id, status, organization_id, initiated_by_user_id,
                   initiated_by_session_id, correlation_id
               ) VALUES (%s, 'completed', %s, %s, %s, %s)""",
            (
                execution_id,
                organization_id,
                actor_id,
                session_id,
                correlation_id,
            ),
        )
        cursor.execute(
            """SELECT id FROM synergia.notifications
               WHERE resource_id = %s AND template_revision_id = %s""",
            (execution_id, published["in_app"]["id"]),
        )
        notification_id = cursor.fetchone()[0]

    deliveries = EmailDeliveryRepository(database_url).claim(
        limit=1000,
        provider="local_capture",
        max_attempts=3,
        consolidation_seconds=0,
    )
    delivery = next(
        item for item in deliveries if item["notification_id"] == notification_id
    )
    assert delivery["template_revision_id"] == published["email"]["id"]

    rollback_sql = (
        ROOT
        / "database/rollbacks/0030_create_notification_template_administration.down.sql"
    ).read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        try:
            cursor.execute(rollback_sql, prepare=False)
            cursor.execute(
                """SELECT t.title_template, t.body_template
                   FROM synergia.notifications n
                   JOIN synergia.identity_users u ON u.id = n.recipient_user_id
                   JOIN synergia.notification_templates t
                     ON t.notification_type = n.notification_type
                    AND t.template_version = n.template_version
                    AND t.locale = u.locale
                   WHERE n.id = %s""",
                (notification_id,),
            )
            assert cursor.fetchone() == (
                published["in_app"]["title_template"],
                published["in_app"]["body_template"],
            )
            cursor.execute(
                """SELECT t.subject_template, t.body_template
                   FROM synergia.email_deliveries d
                   JOIN synergia.notifications n ON n.id = d.notification_id
                   JOIN synergia.email_notification_templates t
                     ON t.notification_type = n.notification_type
                    AND t.template_version = d.template_version
                    AND t.locale = d.locale
                   WHERE d.id = %s AND d.state = 'processing'""",
                (delivery["id"],),
            )
            assert cursor.fetchone() == (
                published["email"]["title_template"],
                published["email"]["body_template"],
            )
        finally:
            connection.rollback()
