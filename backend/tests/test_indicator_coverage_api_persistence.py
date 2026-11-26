"""Additive indicator coverage and current lists with real JWT and PostgreSQL."""

from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app.auth.config import AuthConfig
from app.auth.security import TokenCodec
from app.main import create_app
from app.queries import PostgresQueryRepository
from tests.test_workorder_indicators_persistence import INSTANT, add_version

pytest_plugins = ("tests.test_workorder_indicators_persistence",)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.real_authorization,
]


@pytest.fixture
def api(coverage_dataset, monkeypatch):
    ds = coverage_dataset
    monkeypatch.setenv("DATABASE_URL", ds.url)
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv(
        "AUTH_JWT_SIGNING_KEY", "synthetic-196-signing-key-at-least-32-bytes"
    )
    monkeypatch.setenv("AUTH_JWT_ISSUER", "synthetic-196")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "synthetic-196-api")
    codec = TokenCodec(AuthConfig.from_env())

    def headers(grants):
        user, session = uuid4(), uuid4()
        with psycopg.connect(ds.url) as c:
            c.execute(
                "INSERT INTO synergia.identity_users (id,status,display_name) "
                "VALUES (%s,'active','Synthetic indicators')",
                (user,),
            )
            c.execute(
                "INSERT INTO synergia.identity_sessions "
                "(id,user_id,status,idle_expires_at,absolute_expires_at,"
                "authentication_method) "
                "VALUES (%s,%s,'active',now()+interval '1 hour',"
                "now()+interval '2 hours','synthetic')",
                (session, user),
            )
            for permission, scopes in grants.items():
                for organization in scopes:
                    c.execute(
                        "INSERT INTO synergia.user_permission_assignments "
                        "(user_id,permission_id,organization_id) "
                        "SELECT %s,id,%s FROM synergia.permissions "
                        "WHERE normalized_key=%s",
                        (user, organization, permission),
                    )
        return {"Authorization": "Bearer " + codec.issue_access(user, session)[0]}

    with TestClient(create_app()) as client:
        yield client, headers, ds


def both_scopes(ds):
    return {"dashboard.read": [ds.org_a], "business.read": [ds.org_a]}


def test_indicators_add_current_coverage_without_redefining_legacy_values(api):
    client, headers, ds = api
    # Aggregate access remains dashboard.read; business.read is not newly required.
    response = client.get(
        "/indicators", headers=headers({"dashboard.read": [ds.org_a]})
    )
    assert response.status_code == 200
    body = response.json()
    assert body["workorders"] == {"total": 4, "partially_released": 1}
    assert body["quantities"] == {
        "planned": None,
        "produced": 500,
        "received": None,
        "released": None,
    }
    assert body["workorders_current"] == {"total": 3, "partially_released": 0}
    coverage = body["quantities_coverage"]
    assert coverage["planned"] == {
        "known_sum": 4,
        "known_count": 2,
        "total_count": 3,
        "coverage_percent": 200 / 3,
        "state": "partial",
    }
    assert coverage["produced"] == {
        "known_sum": 0,
        "known_count": 3,
        "total_count": 3,
        "coverage_percent": 100,
        "state": "complete",
    }
    assert coverage["received"] == {
        "known_sum": None,
        "known_count": 0,
        "total_count": 3,
        "coverage_percent": 0,
        "state": "missing",
    }
    assert coverage["released"]["state"] == "partial"
    assert coverage["released"]["known_sum"] == 0
    assert body["execution_summary"]["scope"]["permission"] == "dashboard.read"
    assert body["execution_summary"]["scope"]["organization_ids"] == [str(ds.org_a)]
    assert str(ds.org_b) not in str(body)


@pytest.mark.parametrize("view,total", [(None, 4), ("history", 4), ("current", 3)])
def test_related_workorders_preserve_default_history_and_explicit_current(
    api, view, total
):
    client, headers, ds = api
    params = {} if view is None else {"view": view}
    response = client.get(
        "/indicators/workorders", params=params, headers=headers(both_scopes(ds))
    )
    assert response.status_code == 200
    body = response.json()
    assert body["view"] == (view or "history")
    assert body["pagination"]["total"] == len(body["items"]) == total
    assert body["scope"] == {
        "permissions": ["dashboard.read", "business.read"],
        "organization_ids": [str(ds.org_a)],
    }
    assert all(item["organization_id"] == str(ds.org_a) for item in body["items"])
    assert all(
        item["execution_id"] and item["snapshot_id"] and item["updated_at"]
        for item in body["items"]
    )
    assert all(
        "business_organization_id" not in item and "source_file_id" not in item
        for item in body["items"]
    )


def test_updated_version_reconciles_coverage_current_list_and_exact_detail(api):
    client, headers, ds = api
    with psycopg.connect(ds.url) as c:
        newest, execution = add_version(
            c, organization=ds.org_a, day=2, quantities=(7, 0, None, 0)
        )
    auth = headers(both_scopes(ds))
    indicators = client.get("/indicators", headers=auth).json()
    assert indicators["workorders"]["total"] == 5
    assert indicators["workorders_current"]["total"] == 3
    assert indicators["quantities"]["planned"] is None
    assert indicators["quantities_coverage"]["planned"]["known_sum"] == 7
    items = []
    for page, size in [(1, 2), (2, 2)]:
        response = client.get(
            "/indicators/workorders",
            params={"view": "current", "page": page, "page_size": size},
            headers=auth,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["pagination"] == {
            "page": page,
            "page_size": 2,
            "pages": 2,
            "total": 3,
        }
        items += body["items"]
    assert len({item["snapshot_id"] for item in items}) == 3
    selected = next(item for item in items if item["identifier"] == "WO-001")
    assert selected["snapshot_id"] == newest and selected["execution_id"] == execution
    historical = client.get(
        "/workorders/WO-001",
        headers=auth,
        params={"organization_id": str(ds.org_a), "execution_id": ds.executions["old"]},
    )
    assert historical.status_code == 200
    assert historical.json()["planned_quantity"] == 400
    assert historical.json()["execution_id"] == ds.executions["old"]


def test_same_number_in_two_iam_organizations_counts_twice_without_leaking(api):
    client, headers, ds = api
    for grants in (
        {"dashboard.read": [ds.org_a, ds.org_b], "business.read": [ds.org_a, ds.org_b]},
        {"dashboard.read": [None], "business.read": [None]},
    ):
        auth = headers(grants)
        body = client.get("/indicators", headers=auth).json()
        assert body["workorders_current"]["total"] == 4
        assert body["quantities_coverage"]["planned"]["known_sum"] == 1003
        related = client.get(
            "/indicators/workorders", params={"view": "current"}, headers=auth
        ).json()
        assert related["pagination"]["total"] == 4
        assert (
            len([item for item in related["items"] if item["identifier"] == "WO-001"])
            == 2
        )
        assert {item["organization_id"] for item in related["items"]} == {
            str(ds.org_a),
            str(ds.org_b),
        }


def test_current_scope_is_permission_intersection_not_an_expansion(api):
    client, headers, ds = api
    auth = headers(
        {"dashboard.read": [ds.org_a, ds.org_b], "business.read": [ds.org_a]}
    )
    summary = client.get("/indicators", headers=auth).json()
    assert summary["workorders_current"]["total"] == 4
    related = client.get(
        "/indicators/workorders", params={"view": "current"}, headers=auth
    ).json()
    assert related["pagination"]["total"] == 3
    assert related["scope"]["organization_ids"] == [str(ds.org_a)]
    assert str(ds.org_b) not in str(related)
    assert (
        client.get(
            "/indicators/workorders",
            params={"view": "current", "organization_id": str(ds.org_b)},
            headers=auth,
        ).status_code
        == 403
    )
    a_headers = headers(both_scopes(ds))
    assert (
        client.get(
            "/indicators", params={"organization_id": str(ds.org_b)}, headers=a_headers
        ).status_code
        == 403
    )
    empty = client.get(
        "/indicators",
        params={"execution_id": ds.executions["outside"]},
        headers=a_headers,
    ).json()
    assert empty["workorders_current"]["total"] == 0
    assert all(
        item["state"] == "empty"
        and item["known_sum"] is None
        and item["coverage_percent"] is None
        for item in empty["quantities_coverage"].values()
    )


def test_no_known_values_and_empty_period_have_distinct_contracts(api):
    client, headers, ds = api
    with psycopg.connect(ds.url) as c:
        for number in ("WO-001", "WO-002", "WO-003"):
            add_version(
                c,
                organization=ds.org_a,
                number=number,
                day=2,
                quantities=(None, None, None, None),
            )
    auth = headers(both_scopes(ds))
    body = client.get("/indicators", headers=auth).json()
    assert body["workorders_current"]["total"] == 3
    assert all(
        value
        == {
            "known_sum": None,
            "known_count": 0,
            "total_count": 3,
            "coverage_percent": 0,
            "state": "missing",
        }
        for value in body["quantities_coverage"].values()
    )
    empty = client.get(
        "/indicators", params={"started_from": "2026-11-01T00:00:00Z"}, headers=auth
    ).json()
    assert empty["workorders_current"]["total"] == 0
    assert all(
        value
        == {
            "known_sum": None,
            "known_count": 0,
            "total_count": 0,
            "coverage_percent": None,
            "state": "empty",
        }
        for value in empty["quantities_coverage"].values()
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_period_precedes_selection_and_matches_list_with_timezone(api, legacy):
    client, headers, ds = api
    auth = headers(both_scopes(ds))
    params = (
        {"date_from": "2026-10-01", "date_to": "2026-10-01"}
        if legacy
        else {"started_from": INSTANT.isoformat(), "started_to": INSTANT.isoformat()}
    )
    body = client.get("/indicators", params=params, headers=auth).json()
    assert body["workorders_current"]["total"] == 1
    assert body["quantities_coverage"]["planned"]["known_sum"] == 400
    related = client.get(
        "/indicators/workorders", params={**params, "view": "current"}, headers=auth
    ).json()
    assert related["pagination"]["total"] == 1
    assert related["items"][0]["execution_id"] == ds.executions["old"]


def test_selection_validation_and_permissions_remain_explicit(api):
    client, headers, ds = api
    assert client.get("/indicators").status_code == 401
    assert (
        client.get(
            "/indicators", headers=headers({"business.read": [ds.org_a]})
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/indicators/workorders",
            params={"view": "current"},
            headers=headers({"dashboard.read": [ds.org_a]}),
        ).status_code
        == 403
    )
    auth = headers(both_scopes(ds))
    for entity in ("executions", "pending-items"):
        response = client.get(
            f"/indicators/{entity}", params={"view": "current"}, headers=auth
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "workorder_selection_not_supported"
    assert (
        client.get(
            "/indicators/workorders", params={"view": "invalid"}, headers=auth
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/indicators", params={"started_from": "2026-10-01T00:00:00"}, headers=auth
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/indicators/workorders",
            params={
                "view": "current",
                "started_from": "2026-10-03T00:00:00Z",
                "started_to": "2026-10-01T00:00:00Z",
            },
            headers=auth,
        ).status_code
        == 422
    )


def test_openapi_documents_new_fields_and_preserves_related_default(api):
    client, _, _ = api
    schema = client.get("/openapi.json").json()
    assert schema["info"]["version"] == "0.19.0"
    props = schema["components"]["schemas"]["IndicatorsResponse"]["properties"]
    assert "workorders" in props and "quantities" in props
    assert props["workorders_current"]["$ref"].endswith("/CurrentWorkordersResponse")
    assert props["quantities_coverage"]["$ref"].endswith("/QuantitiesCoverageResponse")
    parameters = {
        item["name"]: item["schema"]
        for item in schema["paths"]["/indicators/{entity}"]["get"]["parameters"]
    }
    assert parameters["view"]["default"] == "history"
    assert parameters["view"]["enum"] == ["current", "history"]


def test_current_list_count_and_rows_share_the_same_read_snapshot(coverage_dataset):
    ds = coverage_dataset
    scopes = frozenset([ds.org_a])

    class ConcurrentImport:
        def __init__(self, c):
            self.connection = c
            self.inserted = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def execute(self, statement, parameters=None):
            result = self.connection.execute(statement, parameters)
            if (
                not self.inserted
                and "SELECT count(*) AS total FROM workorder_snapshots" in statement
            ):
                with psycopg.connect(ds.url) as writer:
                    add_version(writer, organization=ds.org_a, number="WO-004")
                self.inserted = True
            return result

        def __getattr__(self, name):
            return getattr(self.connection, name)

    repository = PostgresQueryRepository(ds.url)
    wrapper = ConcurrentImport(psycopg.connect(ds.url, row_factory=dict_row))
    repository._connect = lambda: wrapper
    rows, total = repository.indicator_related(
        "workorders", scopes, None, None, 1, 25, view="current"
    )
    assert wrapper.inserted
    assert total == len(rows) == 3
    assert (
        PostgresQueryRepository(ds.url).indicators(scopes)["workorders_current"][
            "total"
        ]
        == 4
    )
