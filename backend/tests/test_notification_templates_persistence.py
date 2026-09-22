from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from app.authorization import ActorContext
from app.errors import ApiError
from app.notification_templates import (
    DraftCreate,
    DraftUpdate,
    NotificationTemplateRepository,
    TransitionRequest,
)

pytestmark = pytest.mark.integration


def test_versioned_template_lifecycle_is_immutable_audited_and_used_by_events() -> None:
    database_url = os.environ["DATABASE_URL"]
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
