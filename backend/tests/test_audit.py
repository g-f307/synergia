from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import audit
from app.audit import AuditQuery, csv_cell, get_audit_repository, sanitize_event
from app.authorization import ActorContext, get_actor_context
from app.errors import ApiError
from app.main import app
from tests.conftest import TEST_ORGANIZATION_ID, TEST_USER_ID

pytestmark = pytest.mark.security
PERIOD = {
    "organization_id": str(TEST_ORGANIZATION_ID),
    "occurred_from": "2026-09-01T00:00:00Z",
    "occurred_to": "2026-09-02T00:00:00Z",
}


def event(**changes):
    return {
        "id": "identity:1",
        "occurred_at": datetime(2026, 9, 1, tzinfo=UTC),
        "organization_id": TEST_ORGANIZATION_ID,
        "actor_id": TEST_USER_ID,
        "actor_type": "user",
        "action": "user.admin_updated",
        "resource_type": "user",
        "resource_id": str(TEST_USER_ID),
        "outcome": "success",
        "correlation_id": uuid4(),
        "origin": "identity_access_events",
        "metadata": {},
        **changes,
    }


class MemoryAuditRepository:
    def __init__(self):
        self.rows = [event()]
        self.calls = []
        self.outcomes = []
        self.failure = None

    def read(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self.failure:
            raise self.failure
        offset = kwargs.get("offset", 0)
        return self.rows[offset : offset + kwargs["limit"]], len(self.rows)

    def record_export(self, export_id, action, actor, query, count=None):
        self.outcomes.append((export_id, action, query.filters(), count))


@pytest.fixture
def repository():
    repository = MemoryAuditRepository()
    app.dependency_overrides[get_audit_repository] = lambda: repository
    yield repository
    app.dependency_overrides.pop(get_audit_repository, None)


@pytest.fixture
def client(repository):
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def set_permissions(permissions):
    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        TEST_USER_ID, uuid4(), uuid4(), permissions, uuid4()
    )


def test_json_and_csv_reconcile_and_include_manifest_and_headers(client, repository):
    result = client.get("/audit/events/export", params=PERIOD)
    assert result.status_code == 200, result.text
    exported = result.json()
    assert exported["format_version"] == "1.0.0"
    assert exported["timezone"] == "UTC"
    assert exported["event_count"] == 1
    assert exported["filters"]["occurred_from"] == "2026-09-01T00:00:00Z"
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["content-type"] == "application/json; charset=utf-8"
    assert result.headers["x-content-type-options"] == "nosniff"
    assert result.headers["content-disposition"].endswith('.json"')
    assert result.headers["x-audit-export-id"]
    result = client.get("/audit/events/export", params=PERIOD | {"format": "csv"})
    assert result.status_code == 200, result.text
    assert result.headers["content-type"] == "text/csv; charset=utf-8"
    rows = list(csv.DictReader(io.StringIO(result.text)))
    assert rows[0]["record_type"] == "manifest"
    assert rows[0]["event_count"] == "1"
    assert json.loads(rows[0]["filters"]) == exported["filters"]
    assert rows[1]["record_type"] == "event"
    assert rows[1]["id"] == exported["events"][0]["id"]
    assert [outcome[1] for outcome in repository.outcomes] == [
        "requested",
        "succeeded",
        "requested",
        "succeeded",
    ]
    for start, end in zip(repository.outcomes[::2], repository.outcomes[1::2]):
        assert start[0] == end[0]
        assert end[3] == 1


def test_query_forwards_every_filter_and_pagination(client, repository):
    result = client.get(
        "/audit/events",
        params=PERIOD
        | {
            "actor_id": str(TEST_USER_ID),
            "action": "user.admin_updated",
            "resource_type": "user",
            "resource_id": str(TEST_USER_ID),
            "outcome": "success",
            "sort": "newest",
            "page": 2,
            "page_size": 1,
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["items"] == []
    query, options = repository.calls[0]
    assert query.actor_id == TEST_USER_ID
    assert query.organization_id == TEST_ORGANIZATION_ID
    assert query.action == "user.admin_updated"
    assert query.resource_type == "user"
    assert query.resource_id == str(TEST_USER_ID)
    assert query.outcome == "success"
    assert query.sort == "newest"
    assert options == {"limit": 1, "offset": 1}


@pytest.mark.parametrize("path", ["/audit/events", "/audit/events/export"])
@pytest.mark.parametrize("organization", [str(uuid4()), None])
def test_out_of_scope_and_global_scope_deny_without_read_or_count(
    client,
    repository,
    path,
    organization,
):
    params = {k: v for k, v in PERIOD.items() if k != "organization_id"}
    if organization:
        params["organization_id"] = organization
    result = client.get(path, params=params)
    assert result.status_code == 403
    assert result.json()["error"]["code"] == "access_denied"
    assert not repository.calls
    assert not repository.outcomes


@pytest.mark.parametrize(
    "permissions",
    [
        {},
        {"audit.read": frozenset({TEST_ORGANIZATION_ID})},
        {"audit.export": frozenset({TEST_ORGANIZATION_ID})},
        {
            "audit.read": frozenset({uuid4()}),
            "audit.export": frozenset({TEST_ORGANIZATION_ID}),
        },
    ],
)
def test_export_requires_both_permissions_in_same_scope(
    client,
    repository,
    permissions,
):
    set_permissions(permissions)
    result = client.get("/audit/events/export", params=PERIOD)
    assert result.status_code == 403
    assert not repository.calls
    assert not repository.outcomes


def test_global_permission_selects_global_only(client, repository):
    set_permissions(
        {"audit.read": frozenset({None}), "audit.export": frozenset({None})}
    )
    result = client.get(
        "/audit/events/export",
        params={k: v for k, v in PERIOD.items() if k != "organization_id"},
    )
    assert result.status_code == 200
    assert repository.calls[0][0].organization_id is None


@pytest.mark.parametrize(
    "extra",
    [
        {"occurred_from": "2026-09-01T00:00:00"},
        {"occurred_to": "2026-09-02T00:00:00"},
        {"occurred_to": "2026-08-01T00:00:00Z"},
        {"occurred_to": "2026-12-01T00:00:00Z"},
        {"page": 0},
        {"page_size": 101},
        {"page": 10001},
        {"format": "xlsx"},
        {"sort": "anything"},
        {"action": "' OR 1=1--"},
        {"resource_id": "../../private"},
        {"resource_id": "Bearer-private-value"},
        {"timezone": "local"},
    ],
)
def test_invalid_query_is_rejected_before_export(client, repository, extra):
    result = client.get("/audit/events/export", params=PERIOD | extra)
    assert result.status_code == 422
    assert not repository.calls
    assert not repository.outcomes


def test_timezone_normalizes_to_utc_and_period_is_half_open(client, repository):
    result = client.get(
        "/audit/events",
        params=PERIOD
        | {
            "occurred_from": "2026-08-31T20:00:00-04:00",
            "occurred_to": "2026-09-01T20:00:00-04:00",
        },
    )
    assert result.status_code == 200
    assert result.json()["filters"]["occurred_from"] == "2026-09-01T00:00:00Z"
    query = repository.calls[0][0]
    assert query.occurred_to - query.occurred_from == timedelta(days=1)


@pytest.mark.parametrize("format", ["json", "csv"])
def test_empty_export_still_has_manifest(client, repository, format):
    repository.rows = []
    result = client.get("/audit/events/export", params=PERIOD | {"format": format})
    assert result.status_code == 200
    if format == "json":
        assert result.json()["event_count"] == 0
        assert result.json()["events"] == []
    else:
        rows = list(csv.DictReader(io.StringIO(result.text)))
        assert len(rows) == 1
        assert rows[0]["record_type"] == "manifest"
        assert rows[0]["event_count"] == "0"


@pytest.mark.parametrize(
    "value",
    [
        "=1+1",
        "+cmd",
        "-cmd",
        "@SUM(A1)",
        "  =1+1",
        "\tformula",
        "\rformula",
        "\nformula",
        "\u2003=1+1",
    ],
)
def test_csv_formula_injection_is_neutralized(value):
    assert csv_cell(value) == "'" + value


def test_metadata_allowlist_discards_nested_secrets_and_invalid_values():
    result = sanitize_event(
        event(
            metadata={
                "token": "private-token",
                "password": "private-password",
                "payload": {"cells": ["private-cell"]},
                "reason": "private-stack",
                "format": "json",
                "version": 3,
                "consent": True,
                "to_state": "completed",
                "from_state": "private-state",
                "event_count": {"secret": "private"},
                "state_version": True,
                "duration_ms": -1,
            },
            resource_id="person@example.invalid",
        )
    )
    assert result.metadata == {
        "format": "json",
        "version": 3,
        "consent": True,
        "to_state": "completed",
    }
    assert result.resource_id == "[redacted]"
    assert "private" not in result.model_dump_json()


@pytest.mark.parametrize(
    "state",
    [
        "pending",
        "applying_rules",
        "reprocessing",
        "duplicate",
        "cancelled",
    ],
)
def test_official_execution_states_are_preserved(state):
    result = sanitize_event(event(metadata={"from_state": state, "to_state": state}))
    assert result.metadata == {"from_state": state, "to_state": state}


def test_credential_resource_type_is_preserved_but_identifier_is_redacted():
    result = sanitize_event(
        event(
            action="auth.refresh_failed",
            resource_type="refresh_token",
            resource_id="a" * 64,
        )
    )
    assert result.action == "auth.refresh_failed"
    assert result.resource_type == "refresh_token"
    assert result.resource_id == "[redacted]"


def test_credential_resource_type_remains_filterable(client, repository):
    response = client.get(
        "/audit/events",
        params=PERIOD
        | {
            "resource_type": "refresh_token",
            "action": "auth.refresh_failed",
        },
    )
    assert response.status_code == 200
    assert repository.calls[0][0].resource_type == "refresh_token"


@pytest.mark.parametrize(
    "failure",
    [
        ApiError(413, "audit_volume_limit", "Refine os filtros"),
        RuntimeError("private-database-or-render-message"),
    ],
)
def test_failed_export_records_failure_without_returning_content(
    client,
    repository,
    failure,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    repository.failure = failure
    result = client.get("/audit/events/export", params=PERIOD)
    assert result.status_code in {413, 500}
    assert "Content-Disposition" not in result.headers
    assert "private-database" not in result.text
    assert [outcome[1] for outcome in repository.outcomes] == ["requested", "failed"]
    assert repository.outcomes[0][0] == repository.outcomes[1][0]
    assert list(tmp_path.iterdir()) == []


def test_render_failure_records_failed_and_size_limit_is_not_truncated(
    client,
    repository,
    monkeypatch,
):
    monkeypatch.setattr(audit, "MAX_BYTES", 10)
    result = client.get("/audit/events/export", params=PERIOD)
    assert result.status_code == 413
    assert result.json()["error"]["code"] == "audit_size_limit"
    assert [entry[1] for entry in repository.outcomes] == ["requested", "failed"]


def test_unknown_origin_and_naive_event_timestamp_fail_closed():
    with pytest.raises(ApiError):
        sanitize_event(event(origin="private_table"))
    with pytest.raises(ApiError):
        sanitize_event(event(occurred_at=datetime(2026, 9, 1)))
    with pytest.raises(ValidationError):
        AuditQuery(occurred_from=datetime(2026, 9, 1))


def test_inventory_covers_persisted_event_tables_and_actual_emitters():
    root = Path(__file__).resolve().parents[2]
    inventory = json.loads((root / "docs/audit-event-inventory.json").read_text())
    assert inventory["format_version"] == audit.FORMAT_VERSION
    assert set(inventory["approved_fields"]) == set(audit.AuditEvent.model_fields)
    assert {source["table"] for source in inventory["sources"]} == audit.ORIGINS
    tables = set()
    for migration in (root / "database/migrations").glob("*.sql"):
        tables.update(
            re.findall(
                r"CREATE TABLE synergia\.([a-z_]+(?:events|reconciliations))\b",
                migration.read_text(),
            )
        )
    assert tables <= audit.ORIGINS | set(inventory["excluded_sources"])
    for source in inventory["sources"]:
        assert source["actions"]
        assert source["organization"]
        assert all((root / emitter).is_file() for emitter in source["emitters"])
        assert all(
            source["table"] in (root / emitter).read_text()
            for emitter in source["emitters"]
        )


def test_synthetic_examples_match_export_contract_and_reconcile():
    root = Path(__file__).resolve().parents[2] / "data/synthetic/audit-export"
    document = json.loads((root / "example.json").read_text())
    rows = list(csv.DictReader(io.StringIO((root / "example.csv").read_text())))
    assert document["format_version"] == audit.FORMAT_VERSION
    assert document["event_count"] == 1
    assert rows[0]["record_type"] == "manifest"
    assert rows[0]["event_count"] == "1"
    assert json.loads(rows[0]["filters"]) == document["filters"]
    assert rows[0]["generated_at"] == document["generated_at"]
    assert rows[1]["id"] == document["events"][0]["id"]
    assert set(document["events"][0]) == set(audit.AuditEvent.model_fields)
    audit.AuditExportDocument.model_validate(document)


def test_openapi_publishes_export_schema_and_csv():
    operation = app.openapi()["paths"]["/audit/events/export"]["get"]
    content = operation["responses"]["200"]["content"]
    assert "text/csv" in content
    assert "application/json" in content
    assert "AuditExportDocument" in json.dumps(content)


def test_completion_audit_failure_refuses_download_and_records_failure(
    client,
    repository,
    monkeypatch,
):
    original = repository.record_export

    def record(export_id, action, *args):
        if action == "succeeded":
            raise RuntimeError("private-audit-store-message")
        return original(export_id, action, *args)

    monkeypatch.setattr(repository, "record_export", record)
    result = client.get("/audit/events/export", params=PERIOD)
    assert result.status_code == 500
    assert "content-disposition" not in result.headers
    assert "private-audit-store-message" not in result.text
    assert [entry[1] for entry in repository.outcomes] == ["requested", "failed"]
