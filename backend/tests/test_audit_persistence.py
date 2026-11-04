from __future__ import annotations

import csv
import io
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.audit import AuditQuery, AuditRepository
from app.auth.config import AuthConfig
from app.auth.security import TokenCodec
from app.main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_authorization,
    pytest.mark.security,
]
START = datetime(2026, 8, 1, tzinfo=UTC)


@pytest.fixture
def dataset(monkeypatch):
    database_url = os.environ["DATABASE_URL"]
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv(
        "AUTH_JWT_SIGNING_KEY", "synthetic-audit-signing-key-at-least-32-bytes"
    )
    monkeypatch.setenv("AUTH_JWT_ISSUER", "synergia-audit-test")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "synergia-audit-api")
    org_a, org_b, actor, denied_actor, admin = [uuid4() for _ in range(5)]
    sessions = {user: uuid4() for user in (actor, denied_actor, admin)}
    resource = "audit-" + uuid4().hex
    with psycopg.connect(database_url) as connection:
        for organization in (org_a, org_b):
            connection.execute(
                """INSERT INTO synergia.iam_organizations
                (id, organization_code, display_name) VALUES (%s, %s, 'Audit Test')""",
                (organization, "audit-" + organization.hex),
            )
        for user, role in (
            (actor, "analista"),
            (denied_actor, "consulta"),
            (admin, "admin"),
        ):
            connection.execute(
                """INSERT INTO synergia.identity_users (id, status, display_name)
                VALUES (%s, 'active', 'Synthetic Audit Actor')""",
                (user,),
            )
            connection.execute(
                """INSERT INTO synergia.identity_sessions (
                    id, user_id, status, authenticated_at, last_seen_at,
                    idle_expires_at, absolute_expires_at, authentication_method
                ) VALUES (%s, %s, 'active', now(), now(), now() + interval '8 hours',
                          now() + interval '24 hours', 'synthetic')""",
                (sessions[user], user),
            )
            connection.execute(
                """INSERT INTO synergia.user_role_assignments
                (user_id, role_id, organization_id)
                SELECT %s, id, %s FROM synergia.roles WHERE normalized_key = %s""",
                (user, None if role == "admin" else org_a, role),
            )
        for organization, action, resource_id, time in [
            (org_a, "audit.fixture", resource, START),
            (org_a, "audit.fixture", resource, START),
            (org_a, "audit.fixture_failed", resource, START + timedelta(hours=1)),
            (org_a, "audit.fixture", resource, START + timedelta(days=1)),
            (org_b, "audit.fixture", resource, START),
            (None, "audit.fixture", resource, START),
        ]:
            connection.execute(
                """INSERT INTO synergia.identity_access_events (
                    event_key, actor_user_id, organization_id, entity_type,
                    entity_id, correlation_id, payload, occurred_at
                ) VALUES (%s, %s, %s, 'audit_test', %s, %s, %s, %s)""",
                (
                    action,
                    actor,
                    organization,
                    resource_id,
                    uuid4(),
                    Jsonb(
                        {
                            "token": "private-token",
                            "cells": ["private-cell"],
                            "cookie": "private-cookie",
                            "stack": "private-stack",
                        }
                    ),
                    time,
                ),
            )
    codec = TokenCodec(AuthConfig.from_env())
    headers = {
        user: {"Authorization": "Bearer " + codec.issue_access(user, sessions[user])[0]}
        for user in sessions
    }
    yield {
        "database_url": database_url,
        "org_a": org_a,
        "org_b": org_b,
        "actor": actor,
        "denied_actor": denied_actor,
        "admin": admin,
        "headers": headers,
        "resource": resource,
        "sessions": sessions,
        "params": {
            "organization_id": str(org_a),
            "occurred_from": START.isoformat(),
            "occurred_to": (START + timedelta(days=1)).isoformat(),
            "actor_id": str(actor),
            "resource_type": "audit_test",
            "resource_id": resource,
        },
    }
    # Preserve append-only audit evidence, but leave no active test identities
    # or global administrators that could affect the last-admin regression.
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """UPDATE synergia.user_role_assignments
            SET revoked_at = now(), revocation_reason = 'audit test cleanup'
            WHERE user_id = ANY(%s) AND revoked_at IS NULL""",
            (list(sessions),),
        )
        connection.execute(
            """UPDATE synergia.identity_sessions SET status = 'revoked',
            revoked_at = now(), revocation_reason = 'audit test cleanup'
            WHERE user_id = ANY(%s) AND status = 'active'""",
            (list(sessions),),
        )
        connection.execute(
            """UPDATE synergia.identity_users SET status = 'inactive',
            deactivated_at = now() WHERE id = ANY(%s)""",
            (list(sessions),),
        )


def export_outcomes(dataset):
    with psycopg.connect(dataset["database_url"], row_factory=dict_row) as conn:
        return conn.execute(
            """SELECT export_id, action, event_count, correlation_id
            FROM synergia.audit_export_events WHERE actor_user_id = %s
            ORDER BY id""",
            (dataset["actor"],),
        ).fetchall()


def test_persisted_query_and_formats_share_filters_and_stable_order(dataset):
    headers = dataset["headers"][dataset["actor"]]
    params = dataset["params"] | {"action": "audit.fixture", "outcome": "success"}
    with TestClient(app) as client:
        first = client.get(
            "/audit/events", headers=headers, params=params | {"page_size": 1}
        ).json()
        second = client.get(
            "/audit/events",
            headers=headers,
            params=params | {"page_size": 1, "page": 2},
        ).json()
        document = client.get("/audit/events/export", headers=headers, params=params)
        spreadsheet = client.get(
            "/audit/events/export", headers=headers, params=params | {"format": "csv"}
        )
        newest = client.get(
            "/audit/events/export", headers=headers, params=params | {"sort": "newest"}
        )
    assert document.status_code == spreadsheet.status_code == 200
    events = document.json()["events"]
    assert len(events) == first["total"] == second["total"] == 2
    ids = [event["id"] for event in events]
    assert ids == sorted(ids)
    assert [first["items"][0]["id"], second["items"][0]["id"]] == ids
    assert [row["id"] for row in newest.json()["events"]] == ids[::-1]
    csv_events = [
        r
        for r in csv.DictReader(io.StringIO(spreadsheet.text))
        if r["record_type"] == "event"
    ]
    assert [row["id"] for row in csv_events] == ids
    assert all(row["organization_id"] == str(dataset["org_a"]) for row in events)
    assert "private-" not in document.text + spreadsheet.text
    assert all(event["metadata"] == {} for event in events)
    outcomes = export_outcomes(dataset)
    assert [r["action"] for r in outcomes] == ["requested", "succeeded"] * 3
    assert [r["event_count"] for r in outcomes[1::2]] == [2, 2, 2]


@pytest.mark.parametrize(
    "filter,expected",
    [
        ({}, 3),
        ({"outcome": "failure"}, 1),
        ({"action": "audit.fixture"}, 2),
        ({"resource_type": "missing"}, 0),
        ({"resource_id": "missing"}, 0),
    ],
)
def test_repository_filters_and_half_open_period(dataset, filter, expected):
    query = AuditQuery(**(dataset["params"] | filter))
    rows, total = AuditRepository(dataset["database_url"]).read(query, limit=100)
    assert len(rows) == total == expected
    assert all(row["organization_id"] == dataset["org_a"] for row in rows)
    assert all(row["occurred_at"] < START + timedelta(days=1) for row in rows)


@pytest.mark.parametrize("path", ["/audit/events", "/audit/events/export"])
def test_real_authorization_and_tenant_boundary_have_no_disclosure(dataset, path):
    with TestClient(app) as client:
        anonymous = client.get(path, params=dataset["params"])
        denied = client.get(
            path,
            params=dataset["params"],
            headers=dataset["headers"][dataset["denied_actor"]],
        )
        foreign = client.get(
            path,
            params=dataset["params"] | {"organization_id": str(dataset["org_b"])},
            headers=dataset["headers"][dataset["actor"]],
        )
        unknown = client.get(
            path,
            params=dataset["params"] | {"organization_id": str(uuid4())},
            headers=dataset["headers"][dataset["actor"]],
        )
    assert anonymous.status_code == 401
    assert denied.status_code == foreign.status_code == unknown.status_code == 403
    assert denied.json() == foreign.json() == unknown.json()
    assert "total" not in denied.text
    assert export_outcomes(dataset) == []


def test_null_organization_is_global_only_and_admin_cannot_export(dataset):
    params = {k: v for k, v in dataset["params"].items() if k != "organization_id"}
    with TestClient(app) as client:
        global_only = client.get(
            "/audit/events",
            params=params,
            headers=dataset["headers"][dataset["admin"]],
        )
        scoped = client.get(
            "/audit/events",
            params=params,
            headers=dataset["headers"][dataset["actor"]],
        )
        export = client.get(
            "/audit/events/export",
            params=params,
            headers=dataset["headers"][dataset["admin"]],
        )
    assert global_only.status_code == 200
    assert global_only.json()["total"] == 1
    assert global_only.json()["items"][0]["organization_id"] is None
    assert scoped.status_code == export.status_code == 403


@pytest.mark.parametrize("count,expected", [(10000, 200), (10001, 413)])
def test_volume_limit_refuses_instead_of_truncating_and_records_failure(
    dataset,
    count,
    expected,
):
    with psycopg.connect(dataset["database_url"]) as connection:
        connection.execute(
            """INSERT INTO synergia.identity_access_events (
                event_key, actor_user_id, organization_id, entity_type,
                entity_id, occurred_at
            ) SELECT 'audit.volume', %s, %s, 'audit_test', %s, %s
              FROM generate_series(1, %s)""",
            (dataset["actor"], dataset["org_a"], dataset["resource"], START, count),
        )
    params = dataset["params"] | {"action": "audit.volume"}
    with TestClient(app) as client:
        result = client.get(
            "/audit/events/export",
            params=params,
            headers=dataset["headers"][dataset["actor"]],
        )
    assert result.status_code == expected, result.json().get("error")
    if expected == 413:
        assert result.json()["error"]["code"] == "audit_volume_limit"
        assert "content-disposition" not in result.headers
        terminal = "failed"
    else:
        assert result.json()["event_count"] == count
        terminal = "succeeded"
    assert [r["action"] for r in export_outcomes(dataset)] == ["requested", terminal]


def test_export_events_are_append_only_and_do_not_recurse(dataset):
    headers = dataset["headers"][dataset["actor"]]
    params = {
        "organization_id": str(dataset["org_a"]),
        "occurred_from": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "occurred_to": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        "resource_type": "audit_export",
    }
    with TestClient(app) as client:
        result = client.get("/audit/events/export", headers=headers, params=params)
        assert result.status_code == 200, result.text
        assert result.json()["events"] == []
        second = client.get("/audit/events/export", headers=headers, params=params)
        assert second.status_code == 200, second.text
    assert second.json()["event_count"] == 2
    assert len(export_outcomes(dataset)) == 4
    with psycopg.connect(dataset["database_url"]) as connection:
        for statement in (
            "UPDATE synergia.audit_export_events SET event_count = 0",
            "DELETE FROM synergia.audit_export_events",
        ):
            with pytest.raises(psycopg.errors.RestrictViolation):
                with connection.transaction():
                    connection.execute(
                        statement + " WHERE actor_user_id = %s", (dataset["actor"],)
                    )


def test_concurrent_exports_each_record_exactly_one_terminal_outcome(dataset):
    def export(_):
        with TestClient(app) as client:
            return client.get(
                "/audit/events/export",
                params=dataset["params"],
                headers=dataset["headers"][dataset["actor"]],
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(export, range(2)))
    assert [result.status_code for result in results] == [200, 200]
    outcomes = export_outcomes(dataset)
    assert len(outcomes) == 4
    for result in results:
        export_id = result.headers["x-audit-export-id"]
        matching = [row for row in outcomes if str(row["export_id"]) == export_id]
        assert [row["action"] for row in matching] == ["requested", "succeeded"]
        assert matching[1]["event_count"] == result.json()["event_count"]


def test_manual_feature_rollback_preserves_export_history(dataset):
    with TestClient(app) as client:
        result = client.get(
            "/audit/events/export",
            params=dataset["params"],
            headers=dataset["headers"][dataset["actor"]],
        )
    assert result.status_code == 200
    root = Path(__file__).resolve().parents[2]
    with psycopg.connect(dataset["database_url"]) as connection:
        try:
            connection.execute(
                (
                    root / "database/rollbacks/0034_create_audit_export.down.sql"
                ).read_text(),
                prepare=False,
            )
            assert connection.execute(
                "SELECT to_regclass('synergia.audit_event_catalog')"
            ).fetchone() == (None,)
            assert connection.execute(
                """SELECT count(*) FROM synergia.audit_export_events
                WHERE actor_user_id = %s""",
                (dataset["actor"],),
            ).fetchone() == (2,)
            assert connection.execute(
                """SELECT is_active FROM synergia.permissions
                WHERE normalized_key = 'audit.export'"""
            ).fetchone() == (False,)
        finally:
            connection.rollback()
