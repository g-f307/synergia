from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.auth.config import AuthConfig
from app.auth.security import TokenCodec
from app.main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_authorization,
    pytest.mark.security,
]
PAYLOAD = {
    "kind": "bug",
    "title": "Synthetic feedback",
    "description": "Private synthetic description",
    "source_id": "profile",
}


@pytest.fixture
def dataset(monkeypatch):
    database = os.environ["DATABASE_URL"]
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv(
        "AUTH_JWT_SIGNING_KEY", "synthetic-feedback-signing-key-at-least-32-bytes"
    )
    monkeypatch.setenv("AUTH_JWT_ISSUER", "feedback-test")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "feedback-api")
    org_a, org_b = uuid4(), uuid4()
    users = {
        key: uuid4()
        for key in (
            "author",
            "peer",
            "foreign",
            "triage",
            "foreign_triage",
            "missing",
            "ambiguous",
        )
    }
    sessions = {key: uuid4() for key in users}
    with psycopg.connect(database) as connection:
        for org in (org_a, org_b):
            connection.execute(
                """INSERT INTO synergia.iam_organizations (id,
                organization_code, display_name) VALUES (%s, %s, 'Feedback
                test')""",
                (org, org.hex),
            )
        for name, user in users.items():
            connection.execute(
                """INSERT INTO synergia.identity_users (id, status,
                display_name) VALUES (%s, 'active', 'Synthetic feedback
                actor')""",
                (user,),
            )
            connection.execute(
                """INSERT INTO synergia.identity_sessions
                (id, user_id, status, authenticated_at, last_seen_at,
                 idle_expires_at, absolute_expires_at, authentication_method)
                VALUES (%s, %s, 'active', now(), now(), now() + interval '8 hours',
                        now() + interval '24 hours', 'synthetic')""",
                (sessions[name], user),
            )
            if name != "missing":
                organization = org_b if name.startswith("foreign") else org_a
                connection.execute(
                    """INSERT INTO synergia.user_role_assignments
                    (user_id, role_id, organization_id)
                    SELECT %s, id, %s FROM synergia.roles
                    WHERE normalized_key = 'consulta'""",
                    (user, organization),
                )
            if "triage" in name:
                # Direct grant proves authorization is independent of role name.
                connection.execute(
                    """INSERT INTO synergia.user_permission_assignments
                    (user_id, permission_id, organization_id)
                    SELECT %s, id, %s FROM synergia.permissions
                    WHERE normalized_key = 'feedback.triage'""",
                    (user, organization),
                )
        connection.execute(
            """INSERT INTO synergia.user_role_assignments
            (user_id, role_id, organization_id)
            SELECT %s, id, %s FROM synergia.roles WHERE normalized_key = 'consulta'""",
            (users["ambiguous"], org_b),
        )
    codec = TokenCodec(AuthConfig.from_env())
    headers = {
        key: {"Authorization": "Bearer " + codec.issue_access(user, sessions[key])[0]}
        for key, user in users.items()
    }
    with TestClient(app) as client:
        yield client, headers, users, database, org_a, org_b


def create(dataset, actor="author", **changes):
    client, headers, *_ = dataset
    result = client.post("/feedback", json=PAYLOAD | changes, headers=headers[actor])
    assert result.status_code == 201, result.text
    return result.json()


@pytest.mark.parametrize("kind", ["bug", "suggestion"])
def test_creation_trusted_context_history_and_plain_text(dataset, kind, caplog):
    client, headers, users, database, org, _ = dataset
    title = "<script>alert(1)</script>"
    item = create(dataset, kind=kind, title=title)
    assert item["organization_id"] == str(org)
    assert item["author_user_id"] == str(users["author"])
    assert item["source_route"] == "/profile"
    assert item["protocol"] == "FB-" + item["id"].replace("-", "").upper()
    assert item["state"] == "received" and item["version"] == 1
    assert item["title"] == title and item["allowed_transitions"] == []
    event = item["history"][0]
    assert event["actor_user_id"] == str(users["author"])
    assert event["from_state"] is None and event["to_state"] == "received"
    assert (
        client.get("/feedback/" + item["id"], headers=headers["author"]).json() == item
    )
    with psycopg.connect(database) as connection:
        row = connection.execute(
            """SELECT actor_user_id, session_id, organization_id,
            correlation_id, payload FROM synergia.identity_access_events
            WHERE event_key = 'feedback.created' AND entity_id = %s""",
            (item["id"],),
        ).fetchone()
    assert row[0] == users["author"] and row[1] and row[2] == org and row[3]
    assert "description" not in row[4] and "title" not in row[4]
    assert title not in caplog.text and PAYLOAD["description"] not in caplog.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("organization_id", str(uuid4())),
        ("author_user_id", str(uuid4())),
        ("created_at", "2026-01-01T00:00:00Z"),
        ("history", []),
        ("source_route", "https://evil.example/secret"),
        ("attachment", "data"),
        ("title", "x" * 161),
        ("title", "    "),
        ("description", "x" * 4001),
        ("description", "bad\x00content"),
        ("title", "bidi\u202econtrol"),
        ("expected_result", "x" * 2001),
        ("source_id", "https://evil.example"),
        ("source_id", "admin/users"),
        ("source_id", "profile?token=private"),
    ],
)
def test_payload_limits_no_spoofing_or_unapproved_origins(dataset, field, value):
    client, headers, *_ = dataset
    result = client.post(
        "/feedback", json=PAYLOAD | {field: value}, headers=headers["author"]
    )
    assert result.status_code == 422
    assert (
        value not in result.text
        if isinstance(value, str) and len(value) > 160
        else True
    )


def test_normalizes_text_and_rejects_bug_fields_on_suggestions(dataset):
    item = create(
        dataset,
        title="  Composição  teste ",
        description="  linha 1\r\nlinha 2  ",
        expected_result="  ",
    )
    assert item["title"] == "Composição teste"
    assert item["description"] == "linha 1\nlinha 2"
    assert item["expected_result"] is None
    client, headers, *_ = dataset
    result = client.post(
        "/feedback",
        json=PAYLOAD | {"kind": "suggestion", "expected_result": "Something"},
        headers=headers["author"],
    )
    assert result.status_code == 422


@pytest.mark.parametrize(
    "actor,issue", [("missing", "missing"), ("ambiguous", "ambiguous")]
)
def test_missing_or_ambiguous_membership_fails_closed_with_guidance(
    dataset, actor, issue
):
    client, headers, *_ = dataset
    policy = client.get("/feedback/policy", headers=headers[actor]).json()
    assert not policy["can_create"] and policy["organization_issue"] == issue
    for method, path, payload in [
        ("POST", "/feedback", PAYLOAD),
        ("GET", "/feedback", None),
        ("GET", "/feedback/" + str(uuid4()), None),
    ]:
        result = client.request(method, path, json=payload, headers=headers[actor])
        assert result.status_code == 409
        assert result.json()["error"]["code"] == "feedback_organization_" + issue


def test_own_list_counts_and_details_do_not_expose_peers_or_other_organizations(
    dataset,
):
    client, headers, *_ = dataset
    own = create(dataset)
    create(dataset, "peer")
    foreign = create(dataset, "foreign")
    response = client.get("/feedback", headers=headers["author"]).json()
    assert response["pagination"]["total"] == 1
    assert [item["id"] for item in response["items"]] == [own["id"]]
    for actor, target in [
        ("peer", own),
        ("foreign", own),
        ("author", foreign),
        ("foreign_triage", own),
    ]:
        prefix = "/feedback/triage/" if "triage" in actor else "/feedback/"
        denied = client.get(prefix + target["id"], headers=headers[actor])
        missing = client.get(prefix + str(uuid4()), headers=headers[actor])
        assert denied.status_code == missing.status_code == 404
        assert denied.json() == missing.json()
    for method, path in [
        ("GET", "/feedback/triage"),
        ("GET", "/feedback/triage/" + own["id"]),
        ("PATCH", "/feedback/triage/" + own["id"]),
    ]:
        result = client.request(
            method,
            path,
            json={"version": 1, "state": "under_review"},
            headers=headers["author"],
        )
        assert result.status_code == 403
    assert (
        client.patch(
            "/feedback/triage/" + own["id"],
            json={"version": 1, "state": "under_review"},
            headers=headers["foreign_triage"],
        ).status_code
        == 404
    )


def test_filters_counts_pagination_and_stable_order(dataset):
    client, headers, *_ = dataset
    bug = create(dataset)
    create(dataset, kind="suggestion")
    for filters in [
        {"protocol": bug["protocol"].lower().replace("fb-", "FB-")},
        {"kind": "bug"},
        {"state": "received", "kind": "bug"},
        {
            "created_from": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            "created_to": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "kind": "bug",
        },
    ]:
        result = client.get("/feedback", params=filters, headers=headers["author"])
        assert result.status_code == 200, result.text
        assert [i["id"] for i in result.json()["items"]] == [bug["id"]]
    first = client.get(
        "/feedback",
        params={"sort": "oldest", "page_size": 1},
        headers=headers["author"],
    ).json()
    assert (
        first["items"][0]["id"] == bug["id"]
        and first["pagination"]["total"] == 2
        and first["pagination"]["pages"] == 2
    )
    for filters in [
        {"page_size": 101},
        {"organization_id": str(uuid4())},
        {"created_from": "2026-01-01"},
        {"created_from": "2026-01-02T00:00:00Z", "created_to": "2026-01-01T00:00:00Z"},
    ]:
        assert (
            client.get(
                "/feedback", params=filters, headers=headers["author"]
            ).status_code
            == 422
        )


def test_triage_transitions_justification_history_and_conflicts(dataset):
    client, headers, users, _, _, _ = dataset
    item = create(dataset)
    path = "/feedback/triage/" + item["id"]
    assert (
        client.patch(
            path,
            json={"version": 1, "state": "resolved", "reason": "not yet"},
            headers=headers["triage"],
        ).status_code
        == 409
    )
    for reason in [None, "", "four", " " * 10]:
        assert (
            client.patch(
                path,
                json={"version": 1, "state": "discarded", "reason": reason},
                headers=headers["triage"],
            ).status_code
            == 422
        )
    for version, state in [
        (1, "under_review"),
        (2, "planned"),
        (3, "under_review"),
        (4, "resolved"),
    ]:
        result = client.patch(
            path,
            json={"version": version, "state": state, "reason": "Synthetic decision"},
            headers=headers["triage"],
        )
        assert result.status_code == 200, result.text
    item = result.json()
    assert item["version"] == 5 and item["allowed_transitions"] == []
    assert len(item["history"]) == 5
    assert item["history"][-1]["from_state"] == "under_review"
    assert item["history"][-1]["actor_user_id"] == str(users["triage"])
    assert item["history"][-1]["reason"] == "Synthetic decision"
    assert (
        client.patch(
            path,
            json={"version": 4, "state": "discarded", "reason": "Stale decision"},
            headers=headers["triage"],
        ).json()["error"]["code"]
        == "feedback_conflict"
    )
    assert (
        client.patch(
            path,
            json={"version": 5, "state": "under_review"},
            headers=headers["triage"],
        ).status_code
        == 409
    )
    assert (
        client.get("/feedback/" + item["id"], headers=headers["author"]).json()["state"]
        == "resolved"
    )


def test_concurrent_updates_have_one_winner_and_no_lost_decision(dataset):
    _, headers, _, database, _, _ = dataset
    item = create(dataset)

    def update(state):
        with TestClient(app) as client:
            return client.patch(
                "/feedback/triage/" + item["id"],
                json={"version": 1, "state": state, "reason": "Concurrent decision"},
                headers=headers["triage"],
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update, ["under_review", "discarded"]))
    assert sorted(r.status_code for r in results) == [200, 409]
    with psycopg.connect(database) as connection:
        assert connection.execute(
            "SELECT count(*) FROM synergia.feedback_events WHERE feedback_id=%s",
            (item["id"],),
        ).fetchone() == (2,)


def test_database_guards_and_rollback_preserve_protocol_and_history(dataset):
    item = create(dataset)
    database = dataset[3]
    with psycopg.connect(database) as connection:
        for statement in [
            """UPDATE synergia.feedback SET title='Changed',
            version=version+1, state='under_review' WHERE id=%s""",
            "DELETE FROM synergia.feedback WHERE id=%s",
            "DELETE FROM synergia.feedback_events WHERE feedback_id=%s",
        ]:
            with pytest.raises(
                (psycopg.errors.CheckViolation, psycopg.errors.RestrictViolation)
            ):
                with connection.transaction():
                    connection.execute(statement, (item["id"],))
        for filename in (
            "0037_create_ai_assistance_permissions.down.sql",
            "0036_create_graylog_delivery.down.sql",
        ):
            connection.execute(
                (Path(__file__).resolve().parents[2] / "database/rollbacks" /
                 filename).read_text(), prepare=False,
            )
        connection.execute(
            (
                Path(__file__).resolve().parents[2]
                / "database/rollbacks/0035_create_product_feedback.down.sql"
            ).read_text(),
            prepare=False,
        )
        assert connection.execute(
            "SELECT protocol FROM synergia.feedback WHERE id=%s", (item["id"],)
        ).fetchone() == (item["protocol"],)
        assert connection.execute(
            "SELECT count(*) FROM synergia.feedback_events WHERE feedback_id=%s",
            (item["id"],),
        ).fetchone() == (1,)
        connection.rollback()


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/feedback/policy"),
        ("POST", "/feedback"),
        ("GET", "/feedback"),
        ("GET", "/feedback/" + str(uuid4())),
        ("GET", "/feedback/triage"),
        ("PATCH", "/feedback/triage/" + str(uuid4())),
    ],
)
def test_authentication_is_required(method, path, dataset):
    assert dataset[0].request(method, path, json=PAYLOAD).status_code == 401


def test_global_permission_does_not_invent_membership(dataset):
    client, headers, users, database, *_ = dataset
    with psycopg.connect(database) as connection:
        connection.execute(
            """INSERT INTO synergia.user_permission_assignments
            (user_id, permission_id, organization_id)
            SELECT %s, id, NULL FROM synergia.permissions
            WHERE normalized_key = 'feedback.triage'""",
            (users["missing"],),
        )
    result = client.get("/feedback/policy", headers=headers["missing"])
    assert result.json()["organization_issue"] == "missing"
    assert client.get("/feedback/triage", headers=headers["missing"]).status_code == 409


def test_audit_export_includes_feedback_without_user_text(dataset):
    client, headers, users, database, org, _ = dataset
    item = create(dataset)
    with psycopg.connect(database) as connection:
        connection.execute(
            """INSERT INTO synergia.user_permission_assignments
            (user_id, permission_id, organization_id)
            SELECT %s, id, %s FROM synergia.permissions
            WHERE normalized_key IN ('audit.read', 'audit.export')""",
            (users["triage"], org),
        )
    response = client.get(
        "/audit/events/export",
        params={
            "organization_id": str(org),
            "action": "feedback.created",
            "resource_id": item["id"],
            "occurred_from": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        },
        headers=headers["triage"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["event_count"] == 1
    assert item["description"] not in response.text
    assert item["title"] not in response.text


def test_origin_catalog_covers_authenticated_routes_without_resource_values():
    import sys

    from app.feedback import SOURCE_CATALOG

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.validate_web_journey_map import _current_routes

    routes = _current_routes() - {"/login"}
    assert {source["route"] for source in SOURCE_CATALOG.values()} == routes
    assert all("?" not in source["route"] for source in SOURCE_CATALOG.values())
