"""Real authorization and reconciliation on a private, disposable dataset (#193)."""

# SQL fixtures stay aligned with their selected columns.
# ruff: noqa: E501

import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from app.auth.config import AuthConfig
from app.auth.security import TokenCodec
from app.execution_filters import ExecutionQueryFilters
from app.execution_summary import read_execution_aggregation, start_execution_snapshot
from app.main import create_app
from app.queries import PostgresQueryRepository

pytestmark = [pytest.mark.integration, pytest.mark.real_authorization]
INSTANT = datetime(2026, 11, 1, 12, tzinfo=UTC)


@pytest.fixture
def dataset():
    parent = os.environ["DATABASE_URL"]
    name = "synergia_issue_193_" + uuid4().hex
    url = make_conninfo(parent, dbname=name)
    with psycopg.connect(parent, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[2] / "scripts/apply_migrations.py"
                ),
            ],
            env={**os.environ, "DATABASE_URL": url},
            check=True,
            capture_output=True,
            text=True,
        )
        org_a, org_b = uuid4(), uuid4()
        ids = {"a": [], "b": []}
        selected_states = (
            ["completed"] * 3 + ["completed_with_errors"] * 2 + ["duplicate"] * 9
        )
        remaining = (
            [
                "pending",
                "validating",
                "normalizing",
                "consolidating",
                "applying_rules",
                "reprocessing",
                "failed",
                "validation_failed",
                "cancelled",
            ]
            + ["completed"] * 4
            + ["completed_with_errors"] * 2
            + ["duplicate"]
        )
        with psycopg.connect(url) as connection:
            for organization, label in ((org_a, "A"), (org_b, "B")):
                connection.execute(
                    "INSERT INTO synergia.iam_organizations (id,organization_code,display_name) VALUES (%s,%s,%s)",
                    (organization, f"syn193-{label.lower()}", f"Synthetic 193 {label}"),
                )
            for tenant, organization in (("a", org_a), ("b", org_b)):
                states = (
                    selected_states + remaining if tenant == "a" else ["completed"] * 30
                )
                for index, status in enumerate(states):
                    identifier = f"syn193-{tenant}-{index:02d}"
                    ids[tenant].append(identifier)
                    instant = (
                        INSTANT
                        if index < 14 or tenant == "b"
                        else INSTANT + timedelta(days=1)
                    )
                    source = "OWM" if index < 14 or tenant == "b" else "N-FP"
                    extension = "csv" if index < 14 or tenant == "b" else "json"
                    if tenant == "a" and index in (14, 15):
                        instant = INSTANT + timedelta(
                            microseconds=-1 if index == 14 else 1
                        )
                        source, extension = "OWM", "csv"
                    if tenant == "a" and index == 16:
                        source = None
                    if tenant == "b" and index == 29:
                        source = "Total Decision"
                    connection.execute(
                        "INSERT INTO synergia.executions (id,organization_id,status,source,started_at) VALUES (%s,%s,%s,%s,%s)",
                        (identifier, organization, status, source, instant),
                    )
                    if tenant == "a" and index == 16:
                        continue  # An execution with zero files/records still counts.
                    source_file = connection.execute(
                        "INSERT INTO synergia.source_files (execution_id,file_name,content_hash,extension) VALUES (%s,%s,%s,%s) RETURNING id",
                        (
                            identifier,
                            f"synthetic.{extension}",
                            uuid4().hex * 2,
                            extension,
                        ),
                    ).fetchone()[0]
                    if index == 0:
                        connection.execute(
                            "INSERT INTO synergia.source_files (execution_id,file_name,content_hash,extension) VALUES (%s,'synthetic.xlsx',%s,'xlsx')",
                            (identifier, uuid4().hex * 2),
                        )
                    if tenant == "a" and index in (0, 1):
                        rows = 5 if index == 0 else 7
                        connection.execute(
                            "INSERT INTO synergia.pipeline_summaries (execution_id,source_file_id,rows_read,valid_records,rejected_records,normalized_records,error_count,warning_count) "
                            "VALUES (%s,%s,%s,%s,0,%s,0,0)",
                            (identifier, source_file, rows, rows, rows),
                        )
                        workorder = connection.execute(
                            "INSERT INTO synergia.workorders (execution_id,source_file_id,workorder_number,processing_status,planned_quantity) "
                            "VALUES (%s,%s,%s,'consolidated',10) RETURNING id",
                            (identifier, source_file, f"SYN193-{index}"),
                        ).fetchone()[0]
                        connection.execute(
                            "INSERT INTO synergia.pending_items (execution_id,source_file_id,workorder_id,category) VALUES (%s,%s,%s,'oqc_pending')",
                            (identifier, source_file, workorder),
                        )
            connection.execute(
                "INSERT INTO synergia.executions (id,status,source,started_at) VALUES ('syn193-no-iam','completed','OWM',%s)",
                (INSTANT,),
            )
        yield url, org_a, org_b, ids
    finally:
        with psycopg.connect(parent, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture
def api(dataset, monkeypatch):
    url, org_a, org_b, ids = dataset
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv(
        "AUTH_JWT_SIGNING_KEY", "synthetic-193-signing-key-at-least-32-bytes"
    )
    monkeypatch.setenv("AUTH_JWT_ISSUER", "synergia-193-test")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "synergia-api-test")
    config = AuthConfig.from_env()

    def headers(grants):
        user, session = uuid4(), uuid4()
        with psycopg.connect(url) as connection:
            connection.execute(
                "INSERT INTO synergia.identity_users (id,status,display_name) VALUES (%s,'active','Synthetic 193')",
                (user,),
            )
            connection.execute(
                "INSERT INTO synergia.identity_sessions (id,user_id,status,idle_expires_at,absolute_expires_at,authentication_method) "
                "VALUES (%s,%s,'active',now()+interval '1 hour',now()+interval '2 hours','synthetic')",
                (session, user),
            )
            for permission, organizations in grants.items():
                for organization in organizations:
                    connection.execute(
                        "INSERT INTO synergia.user_permission_assignments (user_id,permission_id,organization_id) "
                        "SELECT %s,id,%s FROM synergia.permissions WHERE normalized_key=%s",
                        (user, organization, permission),
                    )
        return {
            "Authorization": f"Bearer {TokenCodec(config).issue_access(user, session)[0]}"
        }

    with TestClient(create_app()) as client:
        yield client, headers, org_a, org_b, ids


def test_reconciles_three_two_nine_beyond_pagination_with_real_auth(api):
    client, headers, org_a, _, ids = api
    auth = headers({"execution.read": [org_a], "dashboard.read": [org_a]})
    period = {
        "date_from": INSTANT.isoformat(),
        "date_to": INSTANT.isoformat(),
        "source": "OWM",
        "file_type": ".CSV",
    }
    result = client.get("/executions/summary", params=period, headers=auth)
    assert result.status_code == 200
    summary = result.json()
    assert summary["total"] == 14
    assert summary["by_outcome"] == {
        "active": 0,
        "completed": 3,
        "partial": 2,
        "skipped_duplicate": 9,
        "failed": 0,
        "cancelled": 0,
        "unknown": 0,
    }
    assert len(summary["by_source"]) == 1
    assert summary["by_source"][0]["rows_read"] == 12
    assert summary["by_source"][0]["total"] == 14
    dashboard = client.get(
        "/indicators",
        params={
            "started_from": INSTANT.isoformat(),
            "started_to": INSTANT.isoformat(),
            "source": "OWM",
            "file_type": "csv",
        },
        headers=auth,
    ).json()
    assert dashboard["execution_summary"]["by_outcome"] == summary["by_outcome"]
    assert dashboard["executions"] == {
        "completed": 3,
        "completed_with_errors": 2,
        "duplicate": 9,
    }
    assert dashboard["workorders"]["total"] == dashboard["pending_items"]["open"] == 2
    assert dashboard["quantities"]["planned"] == 20
    first = client.get(
        "/executions", params={"page_size": 1, **period}, headers=auth
    ).json()
    second = client.get(
        "/executions", params={"page_size": 1, "page": 2, **period}, headers=auth
    ).json()
    assert first["pagination"]["total"] == second["pagination"]["total"] == 14
    assert first["items"][0]["execution_id"] != second["items"][0]["execution_id"]
    full = client.get("/executions/summary", headers=auth).json()
    assert full["total"] == 30
    assert sum(item["total"] for item in full["by_source"]) == 30
    assert any(item["source"] is None for item in full["by_source"])
    detail = client.get(f"/executions/{ids['a'][5]}", headers=auth).json()
    assert detail["status"] == "duplicate" and detail["lifecycle"] == "completed"
    assert detail["outcome"] == "skipped_duplicate"


def test_every_canonical_category_filters_the_same_catalog_and_summary(api):
    client, headers, org_a, _, _ = api
    auth = headers({"execution.read": [org_a], "dashboard.read": [org_a]})
    expected = {
        "active": 6,
        "completed": 7,
        "partial": 4,
        "skipped_duplicate": 10,
        "failed": 2,
        "cancelled": 1,
        "unknown": 0,
    }
    for outcome, count in expected.items():
        summary = client.get(
            "/executions/summary", params={"outcome": outcome}, headers=auth
        ).json()
        catalog = client.get(
            "/executions", params={"outcome": outcome, "page_size": 1}, headers=auth
        ).json()
        dashboard = client.get(
            "/indicators", params={"outcome": outcome}, headers=auth
        )
        assert dashboard.status_code == 200
        assert dashboard.json()["execution_summary"]["by_outcome"] == summary["by_outcome"]
        related = client.get(
            "/indicators/executions", params={"outcome": outcome}, headers=auth
        )
        assert related.status_code == 200
        assert related.json()["pagination"]["total"] == count
        assert (
            summary["total"]
            == summary["by_outcome"][outcome]
            == catalog["pagination"]["total"]
            == count
        )
        assert all(item["outcome"] == outcome for item in catalog["items"])


def test_indicators_preserve_technical_legacy_and_identifier_filters(api):
    client, headers, org_a, _, ids = api
    auth = headers({"execution.read": [org_a], "dashboard.read": [org_a]})
    for filters, expected in (
        ({"status": "duplicate"}, 10),
        ({"lifecycle": "completed"}, 17),
        ({"execution_id": ids["a"][0]}, 1),
        ({"outcome": "partial", "status": "completed"}, 0),
    ):
        summary = client.get("/executions/summary", params=filters, headers=auth).json()
        dashboard = client.get("/indicators", params=filters, headers=auth)
        related = client.get("/indicators/executions", params=filters, headers=auth)
        assert dashboard.status_code == related.status_code == 200
        assert dashboard.json()["execution_summary"]["by_outcome"] == summary["by_outcome"]
        assert summary["total"] == related.json()["pagination"]["total"] == expected


def test_dashboard_and_execution_scopes_are_independent(api):
    client, headers, org_a, org_b, _ = api
    auth = headers({"execution.read": [org_a], "dashboard.read": [org_a, org_b]})
    executions = client.get("/executions/summary", headers=auth).json()
    dashboard = client.get("/indicators", headers=auth).json()["execution_summary"]
    assert executions["total"] == 30 and dashboard["total"] == 60
    assert executions["scope"]["organization_ids"] == [str(org_a)]
    assert set(dashboard["scope"]["organization_ids"]) == {str(org_a), str(org_b)}
    assert executions["scope"]["permission"] == "execution.read"
    assert dashboard["scope"]["permission"] == "dashboard.read"
    related = client.get("/indicators/executions", headers=auth).json()
    assert related["pagination"]["total"] == 30  # Intersected entity permission.
    only_dashboard = headers({"dashboard.read": [org_a]})
    assert client.get("/indicators", headers=only_dashboard).status_code == 200
    assert client.get("/executions/summary", headers=only_dashboard).status_code == 403
    only_executions = headers({"execution.read": [org_a]})
    assert client.get("/executions/summary", headers=only_executions).status_code == 200
    assert client.get("/indicators", headers=only_executions).status_code == 403


@pytest.mark.parametrize("global_scope", [False, True])
def test_requested_organization_does_not_redefine_permission_scope(api, global_scope):
    client, headers, org_a, org_b, _ = api
    organizations = [None] if global_scope else [org_a, org_b]
    auth = headers({"execution.read": organizations, "dashboard.read": organizations})
    params = {"organization_id": str(org_a)}
    catalog = client.get("/executions/summary", params=params, headers=auth).json()
    dashboard = client.get("/indicators", params=params, headers=auth).json()["execution_summary"]
    assert catalog["total"] == dashboard["total"] == 30
    assert catalog["filters"] == dashboard["filters"]
    assert catalog["by_outcome"] == dashboard["by_outcome"]
    assert catalog["scope"]["organization_ids"] == dashboard["scope"]["organization_ids"]
    if global_scope:
        assert catalog["scope"]["organization_ids"] is None
    else:
        assert set(catalog["scope"]["organization_ids"]) == {str(org_a), str(org_b)}


def test_no_counts_names_or_details_leak_across_organizations_or_unknown_iam(api):
    client, headers, org_a, org_b, ids = api
    auth = headers({"execution.read": [org_a], "dashboard.read": [org_a]})
    for filters in (
        {"organization_id": str(org_b)},
        {"source": "Total Decision"},
        {"execution_id": ids["b"][0]},
    ):
        summary = client.get("/executions/summary", params=filters, headers=auth).json()
        assert summary["total"] == 0 and summary["by_source"] == []
    assert (
        client.get(
            "/indicators", params={"organization_id": str(org_b)}, headers=auth
        ).status_code
        == 403
    )
    assert client.get(f"/executions/{ids['b'][0]}", headers=auth).status_code == 404
    global_auth = headers({"execution.read": [None], "dashboard.read": [None]})
    assert client.get("/executions/summary", headers=global_auth).json()["total"] == 60
    assert (
        client.get("/indicators", headers=global_auth).json()["execution_summary"][
            "total"
        ]
        == 60
    )
    assert client.get("/executions/summary").status_code == 401
    assert client.get("/executions/summary", headers=headers({})).status_code == 403


def test_format_filters_do_not_multiply_files_or_mix_indicator_denominators(api):
    client, headers, org_a, _, _ = api
    auth = headers(
        {
            "execution.read": [org_a],
            "dashboard.read": [org_a],
            "business.read": [org_a],
            "pending.read": [org_a],
        }
    )
    result = client.get(
        "/indicators", params={"file_type": "xlsx"}, headers=auth
    ).json()
    assert result["execution_summary"]["total"] == 1
    assert result["execution_summary"]["by_source"][0]["rows_read"] == 5
    assert result["workorders"]["total"] == result["pending_items"]["open"] == 1
    assert result["quantities"]["planned"] == 10
    for entity in ("executions", "workorders", "pending-items"):
        related = client.get(
            f"/indicators/{entity}", params={"file_type": "xlsx"}, headers=auth
        ).json()
        assert related["pagination"]["total"] == 1


@pytest.mark.parametrize("timezone", ["UTC", "America/Manaus"])
def test_legacy_calendar_dates_preserve_database_timezone(dataset, timezone):
    url, org_a, _, _ = dataset
    zoned_url = make_conninfo(url, options=f"-c timezone={timezone}")
    with psycopg.connect(zoned_url) as connection:
        expected = connection.execute(
            "SELECT count(*) FROM synergia.executions WHERE organization_id=%s AND started_at::date >= %s AND started_at::date <= %s",
            (org_a, date(2026, 11, 1), date(2026, 11, 1)),
        ).fetchone()[0]
    result = PostgresQueryRepository(zoned_url).indicators(
        frozenset({org_a}), date(2026, 11, 1), date(2026, 11, 1)
    )
    summary = result["execution_summary"]
    assert summary.total == sum(result["executions"].values()) == expected
    assert summary.filters.date_from.tzinfo is UTC
    assert summary.filters.date_to.tzinfo is UTC
    assert summary.filters.date_to > summary.filters.date_from


@pytest.mark.parametrize("timezone", ["UTC", "America/Manaus"])
def test_legacy_full_calendar_range_remains_supported(dataset, timezone):
    url, org_a, _, _ = dataset
    result = PostgresQueryRepository(
        make_conninfo(url, options=f"-c timezone={timezone}")
    ).indicators(frozenset({org_a}), date.min, date.max)
    assert result["execution_summary"].total == 30


def test_aggregation_uses_a_read_only_repeatable_snapshot(dataset):
    url, _, _, _ = dataset
    organization = uuid4()
    with psycopg.connect(url) as writer:
        writer.execute(
            "INSERT INTO synergia.iam_organizations (id,organization_code,display_name) VALUES (%s,%s,'Synthetic snapshot')",
            (organization, f"syn193-{organization.hex}"),
        )
    with psycopg.connect(url, row_factory=dict_row) as reader:
        start_execution_snapshot(reader)
        filters = ExecutionQueryFilters()
        kwargs = {
            "organization_scopes": frozenset({organization}),
            "permission": "execution.read",
        }
        assert read_execution_aggregation(reader, filters, **kwargs).summary.total == 0
        assert (
            reader.execute("SHOW transaction_read_only").fetchone()[
                "transaction_read_only"
            ]
            == "on"
        )
        with psycopg.connect(url) as writer:
            writer.execute(
                "INSERT INTO synergia.executions (id,organization_id,status) VALUES (%s,%s,'completed')",
                (f"syn193-{organization.hex}", organization),
            )
        assert read_execution_aggregation(reader, filters, **kwargs).summary.total == 0
    with psycopg.connect(url) as fresh:
        assert read_execution_aggregation(fresh, filters, **kwargs).summary.total == 1
