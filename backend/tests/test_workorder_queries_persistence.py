"""Workorder HTTP contracts with real JWT, IAM scope and private PostgreSQL."""

from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.auth.config import AuthConfig
from app.auth.security import TokenCodec
from app.main import create_app
from tests.test_workorder_snapshots_persistence import INSTANT, NUMBER

pytest_plugins = ("tests.test_workorder_snapshots_persistence",)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.real_authorization,
]


@pytest.fixture
def api(dataset, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", dataset.url)
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv(
        "AUTH_JWT_SIGNING_KEY", "synthetic-195-signing-key-at-least-32-bytes"
    )
    monkeypatch.setenv("AUTH_JWT_ISSUER", "synergia-195-test")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "synergia-195-api")
    codec = TokenCodec(AuthConfig.from_env())

    def headers(organizations, permission="business.read"):
        user, session = uuid4(), uuid4()
        with psycopg.connect(dataset.url) as connection:
            connection.execute(
                "INSERT INTO synergia.identity_users (id,status,display_name) "
                "VALUES (%s,'active','Synthetic 195')",
                (user,),
            )
            connection.execute(
                """INSERT INTO synergia.identity_sessions
                (id,user_id,status,idle_expires_at,absolute_expires_at,authentication_method)
                VALUES (%s,%s,'active',now()+interval '1 hour',
                        now()+interval '2 hours','synthetic')""",
                (session, user),
            )
            permissions = (permission,) if isinstance(permission, str) else permission
            for granted in permissions:
                for organization in organizations:
                    connection.execute(
                        """INSERT INTO synergia.user_permission_assignments
                        (user_id,permission_id,organization_id)
                        SELECT %s,id,%s FROM synergia.permissions
                        WHERE normalized_key=%s""",
                        (user, organization, granted),
                    )
        return {"Authorization": f"Bearer {codec.issue_access(user, session)[0]}"}

    with TestClient(create_app()) as client:
        yield client, headers


def test_api_preserves_history_default_and_exposes_current_snapshot_identity(
    api, dataset
):
    client, headers = api
    auth = headers([dataset.org_a])
    history = client.get(
        "/search", params={"type": "workorder", "query": NUMBER}, headers=auth
    )
    assert history.status_code == 200
    assert history.json()["view"] == "history"
    assert history.json()["pagination"]["total"] == 3
    current = client.get(
        "/search",
        params={"type": "workorder", "query": NUMBER, "view": "current"},
        headers=auth,
    )
    assert current.status_code == 200
    result = current.json()
    assert result["view"] == "current"
    assert result["pagination"]["total"] == 1
    row = result["items"][0]
    assert row["snapshot_id"] == dataset.snapshots["a-tie-later"]
    assert row["execution_id"] == dataset.executions["a-tie-later"]
    assert row["organization_id"] == str(dataset.org_a)
    assert row["organization_name"] == "Synthetic A"
    assert row["organization_code"] == "SAME-WORKBOOK-CODE"
    assert row["updated_at"]
    assert not {"business_organization_id", "source_file_id"} & row.keys()


def test_current_search_paginates_after_separating_iam_organizations(api, dataset):
    client, headers = api
    auth = headers([dataset.org_a, dataset.org_b])
    selected = []
    for page in (1, 2):
        response = client.get(
            "/search",
            params={
                "type": "workorder",
                "query": NUMBER,
                "view": "current",
                "page": page,
                "page_size": 1,
            },
            headers=auth,
        )
        assert response.status_code == 200
        result = response.json()
        assert result["pagination"] == {
            "page": page,
            "page_size": 1,
            "total": 2,
            "pages": 2,
        }
        selected.extend(result["items"])
    assert [item["snapshot_id"] for item in selected] == [
        dataset.snapshots["b-current"],
        dataset.snapshots["a-tie-later"],
    ]
    assert {item["organization_id"] for item in selected} == {
        str(dataset.org_a),
        str(dataset.org_b),
    }


@pytest.mark.parametrize("view", ["current", "history"])
def test_search_requested_organization_cannot_expand_real_permission_scope(
    api, dataset, view
):
    client, headers = api
    response = client.get(
        "/search",
        params={
            "type": "workorder",
            "query": NUMBER,
            "view": view,
            "organization_id": str(dataset.org_b),
        },
        headers=headers([dataset.org_a]),
    )
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["pagination"]["total"] == 0
    assert str(dataset.org_b) not in response.text
    assert "Synthetic B" not in response.text


def test_global_business_scope_still_excludes_unknown_iam_and_unpublished_snapshots(
    api, dataset
):
    client, headers = api
    auth = headers([None])
    response = client.get(
        "/search", params={"type": "workorder", "query": NUMBER}, headers=auth
    )
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 4
    assert {item["organization_id"] for item in response.json()["items"]} == {
        str(dataset.org_a),
        str(dataset.org_b),
    }
    for label in ("unknown-iam", "failed", "duplicate", "validating"):
        hidden = client.get(
            f"/workorders/{NUMBER}",
            params={"execution_id": dataset.executions[label]},
            headers=auth,
        )
        assert hidden.status_code == 404
        assert dataset.executions[label] not in hidden.text


@pytest.mark.parametrize("suffix", ["", "/consolidated-result"])
def test_detail_requires_context_when_two_authorized_organizations_share_number(
    api, dataset, suffix
):
    client, headers = api
    response = client.get(
        f"/workorders/{NUMBER}{suffix}", headers=headers([dataset.org_a, dataset.org_b])
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ambiguous_workorder"
    assert str(dataset.org_a) not in response.text
    assert str(dataset.org_b) not in response.text
    assert "Synthetic A" not in response.text and "Synthetic B" not in response.text


@pytest.mark.parametrize("suffix", ["", "/consolidated-result"])
def test_organization_selects_current_and_explicit_execution_keeps_historical_snapshot(
    api, dataset, suffix
):
    client, headers = api
    auth = headers([dataset.org_a, dataset.org_b])
    path = f"/workorders/{NUMBER}{suffix}"
    current = client.get(
        path, params={"organization_id": str(dataset.org_a)}, headers=auth
    )
    assert current.status_code == 200
    now = current.json()["workorder"] if suffix else current.json()
    assert now["snapshot_id"] == dataset.snapshots["a-tie-later"]
    assert now["planned_quantity"] is None
    assert now["produced_quantity"] == 0
    old = client.get(
        path,
        params={
            "organization_id": str(dataset.org_a),
            "execution_id": dataset.executions["old"],
        },
        headers=auth,
    )
    assert old.status_code == 200
    selected = old.json()["workorder"] if suffix else old.json()
    assert selected["snapshot_id"] == dataset.snapshots["old"]
    assert selected["execution_id"] == dataset.executions["old"]
    assert selected["planned_quantity"] == 40
    assert selected["produced_quantity"] == 20
    assert selected["organization_id"] == str(dataset.org_a)
    assert not {"business_organization_id", "source_file_id"} & selected.keys()


@pytest.mark.parametrize("suffix", ["", "/consolidated-result"])
def test_mismatched_execution_organization_and_out_of_scope_detail_return_safe_404(
    api, dataset, suffix
):
    client, headers = api
    path = f"/workorders/{NUMBER}{suffix}"
    mismatched = client.get(
        path,
        params={
            "organization_id": str(dataset.org_b),
            "execution_id": dataset.executions["old"],
        },
        headers=headers([dataset.org_a, dataset.org_b]),
    )
    assert mismatched.status_code == 404
    forbidden = client.get(
        path,
        params={
            "organization_id": str(dataset.org_b),
            "execution_id": dataset.executions["b-current"],
        },
        headers=headers([dataset.org_a]),
    )
    assert forbidden.status_code == 404
    for response in (mismatched, forbidden):
        assert "Synthetic B" not in response.text
        assert str(dataset.org_b) not in response.text
        assert dataset.executions["b-current"] not in response.text


def test_period_is_applied_before_selection_in_search_and_detail(api, dataset):
    client, headers = api
    auth = headers([dataset.org_a])
    period = {
        "started_from": INSTANT.isoformat(),
        "started_to": (INSTANT + timedelta(days=1)).isoformat(),
    }
    search = client.get(
        "/search",
        params={"type": "workorder", "query": NUMBER, "view": "current", **period},
        headers=auth,
    )
    assert search.status_code == 200
    assert (
        search.json()["items"][0]["snapshot_id"] == dataset.snapshots["z-tie-earlier"]
    )
    for suffix in ("", "/consolidated-result"):
        detail = client.get(
            f"/workorders/{NUMBER}{suffix}", params=period, headers=auth
        )
        assert detail.status_code == 200
        selected = detail.json()["workorder"] if suffix else detail.json()
        assert selected["snapshot_id"] == dataset.snapshots["z-tie-earlier"]


@pytest.mark.parametrize(
    "params,code",
    [
        ({"started_from": "2026-10-01T00:00:00"}, "timezone_required"),
        (
            {
                "started_from": "2026-10-02T00:00:00Z",
                "started_to": "2026-10-01T00:00:00Z",
            },
            "invalid_period",
        ),
    ],
)
def test_period_validation_reuses_canonical_execution_contract(
    api, dataset, params, code
):
    client, headers = api
    auth = headers([dataset.org_a])
    paths = [
        ("/search", {"type": "workorder", "query": NUMBER}),
        (f"/workorders/{NUMBER}", {}),
        (f"/workorders/{NUMBER}/consolidated-result", {}),
    ]
    for path, defaults in paths:
        response = client.get(path, params={**defaults, **params}, headers=auth)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == code


@pytest.mark.parametrize("entity", ["lot", "serial"])
def test_other_entity_queries_keep_legacy_behavior_and_reject_workorder_only_selection(
    api, dataset, entity
):
    client, headers = api
    auth = headers([dataset.org_a])
    baseline = client.get(
        "/search", params={"type": entity, "query": NUMBER}, headers=auth
    )
    assert baseline.status_code == 200
    assert baseline.json()["view"] == "history"
    assert baseline.json()["items"] == []
    for selection in ({"view": "current"}, {"organization_id": str(dataset.org_a)}):
        response = client.get(
            "/search",
            params={"type": entity, "query": NUMBER, **selection},
            headers=auth,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "workorder_selection_not_supported"


def test_authentication_and_business_permission_are_required(api, dataset):
    client, headers = api
    forbidden = headers([dataset.org_a], permission="execution.read")
    for path in (
        f"/search?type=workorder&query={NUMBER}",
        f"/workorders/{NUMBER}",
        f"/workorders/{NUMBER}/consolidated-result",
    ):
        assert client.get(path).status_code == 401
        response = client.get(path, headers=forbidden)
        assert response.status_code == 403
        assert NUMBER not in response.text


def test_indicator_workorder_links_receive_snapshot_identity_without_changing_totals(
    api, dataset
):
    client, headers = api
    assert (
        client.get(
            "/indicators/workorders",
            headers=headers([dataset.org_a], permission="dashboard.read"),
        ).status_code
        == 403
    )
    response = client.get(
        "/indicators/workorders",
        headers=headers(
            [dataset.org_a], permission=("dashboard.read", "business.read")
        ),
    )
    assert response.status_code == 200
    result = response.json()
    assert result["pagination"]["total"] == 4
    assert {row["snapshot_id"] for row in result["items"]} == {
        dataset.snapshots[label]
        for label in ("old", "z-tie-earlier", "a-tie-later", "other-number")
    }
    assert all(row["organization_id"] == str(dataset.org_a) for row in result["items"])
    assert all(row["execution_id"] and row["updated_at"] for row in result["items"])


def test_consolidated_children_stay_on_the_explicitly_selected_execution(api, dataset):
    client, headers = api
    with psycopg.connect(dataset.url) as connection:
        for label in ("old", "a-tie-later"):
            snapshot = dataset.snapshots[label]
            execution = dataset.executions[label]
            source = connection.execute(
                "SELECT source_file_id FROM synergia.workorders WHERE id=%s",
                (snapshot,),
            ).fetchone()[0]
            lot = connection.execute(
                """INSERT INTO synergia.lots
                (lot_number,workorder_id,execution_id,source_file_id)
                VALUES (%s,%s,%s,%s) RETURNING id""",
                (f"LOT-{label}", snapshot, execution, source),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO synergia.serials
                (serial_number,workorder_id,lot_id,execution_id,source_file_id)
                VALUES (%s,%s,%s,%s,%s)""",
                (f"SER-{label}", snapshot, lot, execution, source),
            )
            connection.execute(
                """INSERT INTO synergia.pending_items
                (execution_id,workorder_id,source_file_id,category,reason,priority,priority_score)
                VALUES (%s,%s,%s,'oqc_hold',%s,'high',80)""",
                (execution, snapshot, source, f"Synthetic {label}"),
            )
    auth = headers([dataset.org_a])
    for label in ("old", "a-tie-later"):
        response = client.get(
            f"/workorders/{NUMBER}/consolidated-result",
            params={"execution_id": dataset.executions[label]},
            headers=auth,
        )
        assert response.status_code == 200
        result = response.json()
        assert result["workorder"]["lots"] == [f"LOT-{label}"]
        assert result["workorder"]["serials"] == [f"SER-{label}"]
        assert {item["execution_id"] for item in result["pending_items"]} == {
            dataset.executions[label]
        }
        assert [item["reason"] for item in result["pending_items"]] == [
            f"Synthetic {label}"
        ]


def test_openapi_publishes_additive_version_defaults_and_snapshot_identity(api):
    client, _ = api
    schema = client.get("/openapi.json").json()
    assert schema["info"]["version"] == "0.18.0"
    params = {
        item["name"]: item["schema"]
        for item in schema["paths"]["/search"]["get"]["parameters"]
    }
    assert params["view"]["default"] == "history"
    assert params["view"]["enum"] == ["current", "history"]
    assert {
        "organization_id",
        "execution_id",
        "started_from",
        "started_to",
    } <= params.keys()
    props = schema["components"]["schemas"]["WorkorderResponse"]["properties"]
    assert {
        "organization_id",
        "snapshot_id",
        "execution_id",
        "updated_at",
    } <= props.keys()
    assert (
        "409" in schema["paths"]["/workorders/{workorder_number}"]["get"]["responses"]
    )
