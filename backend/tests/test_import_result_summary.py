from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.authorization import (
    ActorContext,
    get_actor_context,
    get_authorization_repository,
)
from app.errors import ApiError
from app.execution import TERMINAL_STATES, ExecutionState
from app.import_result_summary import ImportResultSummary, project_import_result
from app.imports import get_repository
from app.main import create_app


def snapshot(status="completed", *, persisted=False, rejected=False, **overrides):
    return {
        "execution_id": "synthetic-194",
        "status": status,
        "failure_reason": None,
        "summary_execution_id": "synthetic-194" if persisted else None,
        "rows_read": 0,
        "valid_records": 0,
        "rejected_records": 0,
        "normalized_records": 0,
        "error_count": 0,
        "warning_count": 0,
        "issues_total": 0,
        "rejected_inspection_id": 1 if rejected else None,
        "inspection_reason_code": "macro_or_active_content" if rejected else None,
        "authorized_duplicate_id": None,
        "generated_at": datetime(2026, 11, 17, 12, tzinfo=UTC),
        **overrides,
    }


@pytest.mark.parametrize("status", list(ExecutionState) + ["future_state"])
def test_persisted_summary_is_ready_including_zero_counts(status):
    result = project_import_result(snapshot(status, persisted=True))
    assert result.summary_status == "ready"
    assert result.summary.rows_read == result.summary.errors == 0
    assert result.reason_code == "summary_persisted"
    assert result.duplicate_of_execution_id is None


@pytest.mark.parametrize("status", list(ExecutionState) + ["future_state"])
def test_absence_is_not_zero_and_terminal_is_never_processing(status):
    result = project_import_result(snapshot(status))
    assert result.summary is None
    if status == "duplicate":
        assert result.summary_status == "not_applicable"
    elif status in frozenset(ExecutionState) - TERMINAL_STATES:
        assert result.summary_status == "processing"
    else:
        assert result.summary_status == "unavailable"


def test_unknown_state_and_preparation_have_safe_distinct_reasons():
    result = project_import_result(
        snapshot("failed", failure_reason="preparation_error")
    )
    assert result.summary_status == "unavailable"
    assert result.reason_code == "preparation_error"
    unknown = project_import_result(snapshot("future_state"))
    assert unknown.reason_code == "unknown_execution_state"
    secret = project_import_result(snapshot("failed", failure_reason="/private/token"))
    assert secret.reason_code == "summary_unavailable"
    assert "/private" not in secret.model_dump_json()


def test_rejection_uses_only_safe_inspection_code_and_not_pipeline_counts():
    result = project_import_result(snapshot("failed", rejected=True))
    assert result.summary_status == "not_applicable"
    assert result.reason_code == "security_rejected"
    assert result.inspection_reason_code == "macro_or_active_content"
    assert result.summary is None
    unknown = project_import_result(
        snapshot(
            "failed", rejected=True, inspection_reason_code="/private/file token=secret"
        )
    )
    assert unknown.inspection_reason_code == "security_rejected"
    assert "secret" not in unknown.model_dump_json()


def test_issues_total_is_independent_of_row_and_error_counts():
    result = project_import_result(
        snapshot(
            "completed_with_errors",
            persisted=True,
            rows_read=3,
            valid_records=2,
            rejected_records=1,
            normalized_records=2,
            error_count=1,
            warning_count=2,
            issues_total=3,
        )
    )
    assert result.issues_total == result.summary.errors + result.summary.warnings == 3
    assert result.summary.rejected_records == 1


@pytest.fixture
def api(monkeypatch, tmp_path):
    organization, outside = uuid4(), uuid4()
    grants = {"import.read": frozenset({organization})}
    requests = []

    class Repository:
        failure = False
        missing = False

        def get(self, execution_id):
            return {"source": "N-FP"}

        def result_summary(self, execution_id, *, organization_scopes):
            requests.append((execution_id, organization_scopes))
            if self.failure:
                raise psycopg.OperationalError("private database credentials")
            return (
                None
                if self.missing
                else project_import_result(snapshot(persisted=True))
            )

    class Authorization:
        def execution_organization(self, execution_id):
            return {"synthetic-194": organization, "outside": outside}.get(execution_id)

        def audit_denial(self, *_args, **_kwargs):
            pass

    def actor(request: Request):
        if not request.headers.get("Authorization"):
            raise ApiError(401, "authentication_required", "Autenticação necessária")
        return ActorContext(
            user_id=uuid4(),
            session_id=uuid4(),
            token_id=uuid4(),
            correlation_id=uuid4(),
            permissions=grants,
        )

    application = create_app()
    repository = Repository()
    application.dependency_overrides[get_actor_context] = actor
    application.dependency_overrides[get_authorization_repository] = Authorization
    application.dependency_overrides[get_repository] = lambda: repository
    storage = tmp_path / "absent-storage"
    monkeypatch.setenv("IMPORT_STORAGE_DIR", str(storage))
    with TestClient(application) as client:
        yield client, repository, grants, organization, requests, storage


HEADERS = {"Authorization": "Bearer synthetic"}


def test_http_uses_only_import_read_and_does_not_touch_missing_storage(api):
    client, _, _, organization, requests, storage = api
    result = client.get("/imports/synthetic-194/result-summary", headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["summary_status"] == "ready"
    assert result.json()["summary"]["rows_read"] == 0
    assert requests == [("synthetic-194", frozenset({organization}))]
    assert not storage.exists()


def test_http_distinguishes_auth_missing_resource_and_unavailable(api):
    client, repository, grants, organization, requests, _ = api
    path = "/imports/synthetic-194/result-summary"
    assert client.get(path).status_code == 401
    grants.clear()
    grants["execution.read"] = frozenset({organization})
    assert client.get(path, headers=HEADERS).status_code == 403
    assert not requests
    grants["import.read"] = frozenset({organization})
    assert (
        client.get("/imports/outside/result-summary", headers=HEADERS).status_code
        == 404
    )
    assert (
        client.get("/imports/missing/result-summary", headers=HEADERS).status_code
        == 404
    )
    assert not requests
    repository.missing = True
    assert client.get(path, headers=HEADERS).status_code == 404
    repository.missing = False
    repository.failure = True
    response = client.get(path, headers=HEADERS)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "import_result_unavailable"
    assert "credentials" not in response.text and "private" not in response.text


@pytest.mark.parametrize(
    "artifact", ["pipeline-summary", "validation-report", "normalized-data"]
)
def test_legacy_artifact_get_does_not_create_storage(api, artifact):
    client, _, grants, organization, _, storage = api
    grants["artifact.read"] = frozenset({organization})
    response = client.get(f"/imports/synthetic-194/{artifact}", headers=HEADERS)
    assert response.status_code == 404
    assert not storage.exists()


def test_openapi_result_summary_documents_availability_and_nullable_counts():
    schema = create_app().openapi()
    assert schema["info"]["version"] == "0.19.0"
    operation = schema["paths"]["/imports/{execution_id}/result-summary"]["get"]
    assert {"200", "401", "403", "404", "503"} <= set(operation["responses"])
    model = schema["components"]["schemas"]["ImportResultSummary"]
    assert {
        "execution_status",
        "issues_total",
        "generated_at",
        "summary_status",
    } <= set(model["required"])
    assert {"type": "null"} in model["properties"]["summary"]["anyOf"]
    for example in model["examples"]:
        ImportResultSummary.model_validate(example)
