"""Routing, schemas and projection of the additive execution contracts."""

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.authorization import (
    ActorContext,
    get_actor_context,
    get_authorization_repository,
)
from app.execution_monitoring import ExecutionCatalogItem, get_monitoring_repository
from app.execution_summary import ExecutionSummary
from app.main import create_app
from app.queries import ExecutionResponse


@pytest.fixture
def summary_api():
    organization = uuid4()
    requests = []

    class Repository:
        def summary(self, filters, *, organization_scopes):
            requests.append((filters, organization_scopes))
            return ExecutionSummary.model_validate(
                {
                    "generated_at": datetime.now(UTC),
                    "scope": {
                        "permission": "execution.read",
                        "organization_ids": list(organization_scopes),
                    },
                    "filters": asdict(filters),
                    "total": 0,
                    "by_outcome": {},
                    "by_source": [],
                }
            )

    application = create_app()
    application.dependency_overrides[get_actor_context] = lambda: ActorContext(
        user_id=uuid4(),
        session_id=uuid4(),
        token_id=uuid4(),
        correlation_id=uuid4(),
        permissions={"execution.read": frozenset({organization})},
    )
    application.dependency_overrides[get_monitoring_repository] = Repository
    application.dependency_overrides[get_authorization_repository] = lambda: object()
    with TestClient(application) as client:
        yield client, requests, organization


def test_static_summary_route_normalizes_and_declares_effective_filters(summary_api):
    client, requests, organization = summary_api
    response = client.get(
        "/executions/summary",
        params={
            "source": "OWM",
            "file_type": ".CSV",
            "outcome": "skipped_duplicate",
            "date_from": "2026-11-01T08:00:00-04:00",
            "date_to": "2026-11-01T12:00:00Z",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["scope"] == {
        "permission": "execution.read",
        "organization_ids": [str(organization)],
    }
    assert result["filters"]["file_type"] == "csv"
    assert result["filters"]["outcome"] == "skipped_duplicate"
    assert (
        result["filters"]["date_from"]
        == result["filters"]["date_to"]
        == "2026-11-01T12:00:00Z"
    )
    assert result["total"] == sum(result["by_outcome"].values()) == 0
    assert len(result["by_outcome"]) == 7
    assert requests[0][1] == frozenset({organization})


@pytest.mark.parametrize("query", ["outcome=success", "date_from=2026-11-01T12:00:00"])
def test_summary_rejects_invalid_outcome_and_naive_dates(summary_api, query):
    client, requests, _ = summary_api
    assert client.get(f"/executions/summary?{query}").status_code == 422
    assert requests == []


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("completed", "completed"),
        ("duplicate", "skipped_duplicate"),
        ("completed_with_errors", "partial"),
        ("cancelled", "cancelled"),
        ("future_state", "unknown"),
    ],
)
def test_detail_and_catalog_derive_outcome_from_the_persisted_status(status, expected):
    common = {
        "execution_id": "synthetic",
        "status": status,
        "attempt": 1,
        "started_at": datetime.now(UTC),
        "outcome": "completed",
    }
    detail = ExecutionResponse.model_validate(
        {
            **common,
            "pipeline_version": "1.0.0",
            "rule_catalog_version": "1.0.0",
            "state_version": 1,
        }
    )
    catalog = ExecutionCatalogItem.model_validate(
        {
            **common,
            "organization_id": uuid4(),
            "lifecycle": "completed",
            "source": "OWM",
            "file_types": [],
            "file_count": 0,
            "rows_read": 0,
            "error_count": 0,
            "warning_count": 0,
            "finished_at": None,
        }
    )
    assert detail.model_dump()["outcome"] == catalog.model_dump()["outcome"] == expected


def test_openapi_declares_outcomes_and_deprecates_only_the_legacy_contract():
    schema = create_app().openapi()
    assert schema["info"]["version"] == "0.17.0"
    assert set(schema["components"]["schemas"]["ExecutionOutcome"]["enum"]) == {
        "active",
        "completed",
        "partial",
        "skipped_duplicate",
        "failed",
        "cancelled",
        "unknown",
    }
    for name in ("ExecutionResponse", "ExecutionCatalogItem"):
        model = schema["components"]["schemas"][name]
        assert model["properties"]["lifecycle"]["deprecated"] is True
        assert "outcome" in model["required"]
    assert schema["paths"]["/executions/summary"]["get"]["security"]
    example = schema["components"]["schemas"]["ExecutionSummary"]["examples"][0]
    result = ExecutionSummary.model_validate(example)
    assert result.total == sum(result.by_outcome.model_dump().values())
    assert result.total == sum(source.total for source in result.by_source)
