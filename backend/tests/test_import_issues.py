import csv
from contextlib import contextmanager
from datetime import UTC, datetime
from io import StringIO
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
from app.import_issues import (
    CSV_FIELDS,
    ISSUE_REASONS,
    ImportIssuePage,
    ImportIssuePagination,
    _csv_chunks,
    public_import_issue,
    safe_csv_cell,
)
from app.imports import get_repository
from app.main import create_app
from app.pipeline_issue_query import pipeline_issue_query

NOW = datetime(2026, 11, 17, 12, tzinfo=UTC)
HEADERS = {"Authorization": "Bearer synthetic"}


def issue_row(**changes):
    return {
        "id": 1,
        "source_file_id": 12,
        "extension": "xlsx",
        "severity": "error",
        "code": "invalid_quantity",
        "scope": "record",
        "sheet_name": "Sheet1",
        "row_number": 8,
        "column_name": "AX",
        "occurred_at": NOW,
        "reason": "secret-cell /private/secret.xlsx Traceback password=synthetic",
        "details": {"original_value": "sensitive-cell"},
        **changes,
    }


def test_public_projection_locates_error_without_using_raw_reason_or_details():
    item = public_import_issue(issue_row())
    assert item.safe_file_name == "arquivo-12.xlsx"
    assert (item.sheet_name, item.row_number, item.column_name) == ("Sheet1", 8, "AX")
    assert item.code == "invalid_quantity"
    assert item.reason == ISSUE_REASONS["invalid_quantity"]
    assert set(item.model_dump()) == set(CSV_FIELDS)
    assert all(
        word not in item.model_dump_json()
        for word in (
            "secret",
            "private",
            "Traceback",
            "password",
            "sensitive",
            "details",
        )
    )


@pytest.mark.parametrize(
    "value",
    [
        "=HYPERLINK(secret)",
        "person@example.invalid",
        "/private/path",
        "C:\\private",
        "\npassword=synthetic",
        "Bearer synthetic",
        "secret-cell",
        "<script>",
    ],
)
def test_untrusted_metadata_and_unknown_code_fail_closed(value):
    item = public_import_issue(
        issue_row(
            sheet_name=value,
            column_name=value,
            code=value,
            extension=value,
        )
    )
    assert item.sheet_name is None and item.column_name is None
    assert item.code == "unmapped_issue"
    assert item.safe_file_name == "arquivo-12"
    assert value not in item.model_dump_json()


@pytest.mark.parametrize(
    ("sheet", "column"),
    [
        ("CSV", "workorder_number"),
        ("Dados", "status"),
        ("Planilha 2", "A"),
        ("OWM SN", "O:Serial Number"),
        ("LOT PENDING_OQC", "status_changed_at"),
    ],
)
def test_contract_locations_are_preserved(sheet, column):
    item = public_import_issue(issue_row(sheet_name=sheet, column_name=column))
    assert (item.sheet_name, item.column_name) == (sheet, column)


def test_unknown_location_is_null_not_invented_and_bad_file_reference_is_hidden():
    item = public_import_issue(
        issue_row(
            sheet_name=None,
            column_name="ZZZ",
            row_number=-1,
            source_file_id=None,
        )
    )
    assert item.sheet_name is item.column_name is item.row_number is None
    assert item.safe_file_name is None


@pytest.mark.parametrize("value", ["=1+1", "+1", "-1", "@SUM(A1)", " \t=1+1"])
def test_csv_protects_formula_cells(value):
    assert safe_csv_cell(value) == "'" + value


def test_csv_has_bom_and_same_fields_and_rows_in_bounded_batches():
    class Cursor:
        remaining = [issue_row(id=index) for index in range(501, 1002)]
        calls = []

        def fetchmany(self, size):
            self.calls.append(size)
            rows, self.remaining = self.remaining[:size], self.remaining[size:]
            return rows

    cursor = Cursor()
    content = "".join(
        _csv_chunks(cursor, [issue_row(id=index) for index in range(1, 501)])
    )
    assert content.startswith("\ufeff")
    rows = list(csv.DictReader(StringIO(content.lstrip("\ufeff"))))
    assert len(rows) == 1001
    assert list(rows[0]) == list(CSV_FIELDS)
    assert [int(row["id"]) for row in rows] == list(range(1, 1002))
    assert cursor.calls == [500, 500, 500]
    assert "secret" not in content and "sensitive" not in content


def test_shared_query_import_projection_never_selects_private_record_content():
    organization = uuid4()
    query = pipeline_issue_query(
        "synthetic",
        projection="import",
        organization_scopes=frozenset({organization}),
        severity="error",
        sort="newest",
    )
    sql = query.select_sql()
    for forbidden in (
        "details",
        "normalized_records",
        "file_name",
        "storage_key",
        "reason",
    ):
        assert forbidden not in sql
    assert "sf.execution_id=e.id" in sql
    assert "e.organization_id=ANY(%s::uuid[])" in sql
    assert query.parameters == ("synthetic", [organization], "error")
    assert query.ordering == "pi.created_at DESC,pi.id DESC"


@pytest.fixture
def api(monkeypatch, tmp_path):
    organization, outside = uuid4(), uuid4()
    grants = {"import.read": frozenset({organization})}

    class Authorization:
        def execution_organization(self, identifier):
            return {"synthetic": organization, "outside": outside}.get(identifier)

        def audit_denial(self, *_args, **_kwargs):
            pass

    class Repository:
        failure = False
        missing = False
        closed = False
        calls = []

        def issues(self, execution_id, **filters):
            self.calls.append((execution_id, filters))
            if self.failure:
                raise psycopg.OperationalError("password=synthetic /private/db")
            return (
                None
                if self.missing
                else ImportIssuePage(
                    items=[public_import_issue(issue_row())],
                    pagination=ImportIssuePagination(
                        page=1, page_size=20, total=1, pages=1
                    ),
                    sort="oldest",
                    generated_at=NOW,
                )
            )

        @contextmanager
        def issue_csv(self, execution_id, **filters):
            self.calls.append((execution_id, filters))
            if self.failure:
                raise psycopg.OperationalError("password=synthetic /private/db")
            try:
                yield (
                    None if self.missing else iter(["\ufeffid,reason\r\n1,Seguro\r\n"])
                )
            finally:
                self.closed = True

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
        yield client, repository, grants, organization, storage


def test_http_page_passes_scope_severity_paging_sort_and_does_not_touch_storage(api):
    client, repository, _, organization, storage = api
    response = client.get(
        "/imports/synthetic/issues?severity=warning&page=3&page_size=25&sort=newest",
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert repository.calls[-1] == (
        "synthetic",
        {
            "organization_scopes": frozenset({organization}),
            "severity": "warning",
            "page": 3,
            "page_size": 25,
            "sort": "newest",
        },
    )
    assert not storage.exists()


@pytest.mark.parametrize("endpoint", ["issues", "issues/export"])
def test_http_auth_scope_missing_failure_and_recovery_are_explicit(api, endpoint):
    client, repository, grants, organization, storage = api
    path = f"/imports/synthetic/{endpoint}"
    assert client.get(path).status_code == 401
    grants.clear()
    grants["artifact.read"] = frozenset({organization})
    assert client.get(path, headers=HEADERS).status_code == 403
    grants["import.read"] = frozenset({organization})
    for identifier in ("outside", "missing"):
        assert (
            client.get(
                f"/imports/{identifier}/{endpoint}",
                headers=HEADERS,
            ).status_code
            == 404
        )
    repository.missing = True
    assert client.get(path, headers=HEADERS).status_code == 404
    repository.missing = False
    repository.failure = True
    failure = client.get(path, headers=HEADERS)
    assert failure.status_code == 503
    assert failure.json()["error"]["code"] == "import_issues_unavailable"
    assert "password" not in failure.text and "/private" not in failure.text
    repository.failure = False
    assert client.get(path, headers=HEADERS).status_code == 200
    assert not storage.exists()


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page_size=0",
        "page_size=101",
        "page=bad",
        "severity=info",
        "sort=bad",
    ],
)
def test_http_invalid_filters_are_422(api, query):
    client, _, _, _, _ = api
    assert (
        client.get(
            "/imports/synthetic/issues?" + query,
            headers=HEADERS,
        ).status_code
        == 422
    )


def test_csv_response_is_attachment_and_closes_request_resource(api):
    client, repository, _, _, _ = api
    response = client.get("/imports/synthetic/issues/export", headers=HEADERS)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="import-issues.csv"'
    )
    assert response.headers["cache-control"] == "no-store"
    assert repository.closed


def test_openapi_describes_safe_dto_nullable_locations_and_csv():
    schema = create_app().openapi()
    issue = schema["components"]["schemas"]["ImportIssue"]
    assert set(issue["properties"]) == set(CSV_FIELDS)
    assert {"type": "null"} in issue["properties"]["row_number"]["anyOf"]
    for path in ("issues", "issues/export"):
        operation = schema["paths"][f"/imports/{{execution_id}}/{path}"]["get"]
        assert {"401", "403", "404", "422", "503"} <= set(operation["responses"])
    export = schema["paths"]["/imports/{execution_id}/issues/export"]["get"]
    assert set(export["responses"]["200"]["content"]) == {"text/csv"}
