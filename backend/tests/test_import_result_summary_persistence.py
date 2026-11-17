"""Real PostgreSQL, authorization and artifact independence for #194, block 1."""

import csv
import hashlib
import json
import os
import subprocess
import sys
from io import BytesIO, StringIO
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from psycopg import sql
from psycopg.conninfo import make_conninfo

from app.auth.config import AuthConfig
from app.auth.security import TokenCodec
from app.execution import ExecutionState
from app.import_issues import open_import_issue_csv, read_import_issues
from app.import_result_summary import read_import_result_summary
from app.imports import PostgresImportRepository
from app.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.real_authorization]


@pytest.fixture(scope="module")
def dataset():
    parent = os.environ["DATABASE_URL"]
    name = "synergia_194_" + uuid4().hex
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
        with psycopg.connect(url) as connection:
            for organization, label in ((org_a, "a"), (org_b, "b")):
                connection.execute(
                    "INSERT INTO synergia.iam_organizations "
                    "(id,organization_code,display_name) VALUES (%s,%s,%s)",
                    (organization, "syn194-" + label, "Synthetic 194 " + label),
                )
            for identifier, organization, status, reason in [
                ("ready", org_a, "completed_with_errors", None),
                ("zero", org_a, "completed", None),
                ("prior-a", org_a, "completed", None),
                ("prior-b", org_b, "completed", None),
                ("no-iam", None, "completed", None),
                ("rejected", org_a, "failed", "macro_or_active_content"),
                ("preparation", org_a, "failed", "preparation_error"),
                ("artifact-only", org_a, "completed", None),
                ("unsafe", org_a, "completed_with_errors", None),
                ("duplicate-a", org_a, "duplicate", None),
                ("duplicate-b", org_a, "duplicate", None),
                ("duplicate-no-iam", org_a, "duplicate", None),
                *[(state.value, org_a, state.value, None) for state in ExecutionState],
            ]:
                connection.execute(
                    "INSERT INTO synergia.executions "
                    "(id,organization_id,status,source,failure_reason,"
                    "actor_type,actor_identifier) "
                    "VALUES (%s,%s,%s,'N-FP',%s,'technical','synthetic-194')",
                    (identifier, organization, status, reason),
                )
            for identifier, previous in [
                ("duplicate-a", "prior-a"),
                ("duplicate-b", "prior-b"),
                ("duplicate-no-iam", "no-iam"),
            ]:
                connection.execute(
                    "UPDATE synergia.executions SET duplicate_of_execution_id=%s "
                    "WHERE id=%s",
                    (previous, identifier),
                )
            for identifier in ("ready", "zero"):
                source_file = connection.execute(
                    "INSERT INTO synergia.source_files "
                    "(execution_id,file_name,content_hash,extension,source) "
                    "VALUES (%s,'synthetic.csv',%s,'csv','N-FP') RETURNING id",
                    (identifier, uuid4().hex * 2),
                ).fetchone()[0]
                rows, valid, rejected, errors, warnings = (
                    (55, 35, 20, 20, 35) if identifier == "ready" else (0, 0, 0, 0, 0)
                )
                connection.execute(
                    "INSERT INTO synergia.pipeline_summaries "
                    "(execution_id,source_file_id,rows_read,valid_records,rejected_records,"
                    "normalized_records,error_count,warning_count) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        identifier,
                        source_file,
                        rows,
                        valid,
                        rejected,
                        valid,
                        errors,
                        warnings,
                    ),
                )
                if identifier == "ready":
                    for index in range(55):
                        connection.execute(
                            "INSERT INTO synergia.pipeline_issues "
                            "(execution_id,source_file_id,scope,severity,code,reason,"
                            "details,sheet_name,row_number,column_name) "
                            "VALUES (%s,%s,'record',%s,'required_field',%s,%s::jsonb,"
                            "'CSV',%s,'A')",
                            (
                                identifier,
                                source_file,
                                "error" if index < 20 else "warning",
                                "Synthetic private value must not appear",
                                json.dumps(
                                    {
                                        "value": "synthetic-sensitive-cell",
                                        "workorder_number": "WO-SYN-194",
                                    }
                                ),
                                index + 2,
                            ),
                        )
            outside_file = connection.execute(
                "INSERT INTO synergia.source_files "
                "(execution_id,file_name,content_hash,extension) "
                "VALUES ('prior-b','private-outside-file.csv',%s,'csv') RETURNING id",
                (uuid4().hex * 2,),
            ).fetchone()[0]
            for identifier, source_file in (
                ("prior-b", outside_file),
                ("unsafe", outside_file),
            ):
                connection.execute(
                    "INSERT INTO synergia.pipeline_issues "
                    "(execution_id,source_file_id,scope,severity,code,reason,"
                    "sheet_name,column_name,details) VALUES "
                    "(%s,%s,'record','error','password=synthetic','private-cell',"
                    "'person@example.invalid','/private/path',%s::jsonb)",
                    (identifier, source_file, json.dumps({"value": "private-value"})),
                )
            connection.execute(
                "INSERT INTO synergia.file_inspections "
                "(execution_id,source,original_file_name,internal_name,size_bytes,"
                "content_hash,decision,reason_code,analyzed_at,retained_until) "
                "VALUES ('rejected','N-FP','synthetic.xlsx',%s,10,%s,'rejected',"
                "'macro_or_active_content',now(),now()+interval '1 hour')",
                (uuid4().hex + uuid4().hex[:16], uuid4().hex * 2),
            )
        yield url, org_a, org_b
    finally:
        with psycopg.connect(parent, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture
def api(dataset, monkeypatch, tmp_path):
    url, org_a, org_b = dataset
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv(
        "AUTH_JWT_SIGNING_KEY", "synthetic-194-signing-key-at-least-32-bytes"
    )
    monkeypatch.setenv("AUTH_JWT_ISSUER", "synergia-194-test")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "synergia-api-test")
    storage = tmp_path / "missing-storage"
    monkeypatch.setenv("IMPORT_STORAGE_DIR", str(storage))
    config = AuthConfig.from_env()

    def headers(grants):
        user, session = uuid4(), uuid4()
        with psycopg.connect(url) as connection:
            connection.execute(
                "INSERT INTO synergia.identity_users (id,status,display_name) "
                "VALUES (%s,'active','Synthetic 194')",
                (user,),
            )
            connection.execute(
                "INSERT INTO synergia.identity_sessions "
                "(id,user_id,status,idle_expires_at,absolute_expires_at,"
                "authentication_method) "
                "VALUES (%s,%s,'active',now()+interval '1 hour',"
                "now()+interval '2 hours','synthetic')",
                (session, user),
            )
            for permission, organizations in grants.items():
                for organization in organizations:
                    connection.execute(
                        "INSERT INTO synergia.user_permission_assignments "
                        "(user_id,permission_id,organization_id) "
                        "SELECT %s,id,%s FROM synergia.permissions "
                        "WHERE normalized_key=%s",
                        (user, organization, permission),
                    )
        return {
            "Authorization": "Bearer "
            + TokenCodec(config).issue_access(user, session)[0]
        }

    with TestClient(create_app()) as client:
        yield client, headers, org_a, org_b, storage


def test_ready_without_artifact_and_counts_reconcile_to_database(api):
    client, headers, org_a, _, storage = api
    auth = headers({"import.read": [org_a]})
    result = client.get("/imports/ready/result-summary", headers=auth)
    assert result.status_code == 200
    data = result.json()
    assert data["summary_status"] == "ready"
    assert data["execution_status"] == "completed_with_errors"
    assert (
        data["issues_total"]
        == data["summary"]["errors"] + data["summary"]["warnings"]
        == 55
    )
    assert data["summary"]["rows_read"] == 55
    assert not storage.exists()
    assert "sensitive-cell" not in result.text and "private value" not in result.text
    assert (
        client.get("/imports/ready/pipeline-summary", headers=auth).status_code == 404
    )
    assert not storage.exists()
    assert client.get("/executions/ready", headers=auth).status_code == 403
    assert client.get("/executions/ready/divergences", headers=auth).status_code == 403


def test_existing_json_does_not_replace_missing_persisted_counts(api):
    client, headers, org_a, _, storage = api
    auth = headers({"import.read": [org_a]})
    artifact = storage / "accepted" / "n_fp" / "artifact-only" / "pipeline-summary.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps(
            {
                "rows_read": 3,
                "valid_records": 2,
                "rejected_records": 1,
                "normalized_records": 2,
                "errors": 1,
                "warnings": 0,
            }
        )
    )
    assert (
        client.get("/imports/artifact-only/pipeline-summary", headers=auth).status_code
        == 200
    )
    result = client.get("/imports/artifact-only/result-summary", headers=auth).json()
    assert result["summary_status"] == "unavailable"
    assert result["summary"] is None and result["issues_total"] == 0
    assert artifact.is_file()


def test_every_persisted_state_and_security_preparation_and_zero_cases(api):
    client, headers, org_a, _, _ = api
    auth = headers({"import.read": [org_a]})
    expected = {
        "pending": "processing",
        "validating": "processing",
        "normalizing": "processing",
        "consolidating": "processing",
        "applying_rules": "processing",
        "reprocessing": "processing",
        "completed": "unavailable",
        "completed_with_errors": "unavailable",
        "validation_failed": "unavailable",
        "failed": "unavailable",
        "cancelled": "unavailable",
        "duplicate": "not_applicable",
        "rejected": "not_applicable",
        "preparation": "unavailable",
        "zero": "ready",
    }
    for identifier, status in expected.items():
        response = client.get(f"/imports/{identifier}/result-summary", headers=auth)
        assert response.status_code == 200, identifier
        assert response.json()["summary_status"] == status, identifier
    zero = client.get("/imports/zero/result-summary", headers=auth).json()
    assert zero["summary"]["rows_read"] == zero["issues_total"] == 0
    rejection = client.get("/imports/rejected/result-summary", headers=auth).json()
    assert rejection["inspection_reason_code"] == "macro_or_active_content"
    preparation = client.get("/imports/preparation/result-summary", headers=auth).json()
    assert preparation["reason_code"] == "preparation_error"


def test_real_auth_and_duplicate_links_stay_in_import_permission_scope(api):
    client, headers, org_a, org_b, _ = api
    auth = headers({"import.read": [org_a]})
    assert client.get("/imports/ready/result-summary").status_code == 401
    assert (
        client.get(
            "/imports/ready/result-summary",
            headers=headers({"execution.read": [org_a]}),
        ).status_code
        == 403
    )
    for identifier in ("prior-b", "no-iam", "missing"):
        assert (
            client.get(
                f"/imports/{identifier}/result-summary", headers=auth
            ).status_code
            == 404
        )
    allowed = client.get("/imports/duplicate-a/result-summary", headers=auth).json()
    assert allowed["duplicate_of_execution_id"] == "prior-a"
    denied = client.get("/imports/duplicate-b/result-summary", headers=auth)
    assert denied.json()["duplicate_of_execution_id"] is None
    assert "prior-b" not in denied.text
    global_auth = headers({"import.read": [None]})
    assert (
        client.get("/imports/duplicate-b/result-summary", headers=global_auth).json()[
            "duplicate_of_execution_id"
        ]
        == "prior-b"
    )
    assert (
        client.get("/imports/no-iam/result-summary", headers=global_auth).status_code
        == 404
    )
    assert (
        client.get(
            "/imports/duplicate-no-iam/result-summary", headers=global_auth
        ).json()["duplicate_of_execution_id"]
        is None
    )
    unrelated = headers({"import.read": [org_b]})
    assert (
        client.get("/imports/ready/result-summary", headers=unrelated).status_code
        == 404
    )


def test_repository_reapplies_scope_and_enforces_read_only(dataset):
    url, org_a, org_b = dataset
    repository = PostgresImportRepository(url)
    assert (
        repository.result_summary("prior-b", organization_scopes=frozenset({org_a}))
        is None
    )
    assert repository.result_summary("ready", organization_scopes=frozenset()) is None
    assert repository.result_summary("no-iam", organization_scopes=None) is None
    assert (
        repository.result_summary("prior-b", organization_scopes=frozenset({org_b}))
        is not None
    )
    with psycopg.connect(url) as connection:
        assert (
            read_import_result_summary(connection, "ready", organization_scopes=None)
            is not None
        )
        assert connection.execute("SHOW transaction_read_only").fetchone()[0] == "on"
        assert (
            connection.execute("SHOW transaction_isolation").fetchone()[0]
            == "repeatable read"
        )
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            connection.execute(
                "UPDATE synergia.executions SET source='OWM' WHERE id='ready'"
            )
        connection.rollback()


def test_repeated_get_never_changes_business_history_or_creates_artifacts(api, dataset):
    client, headers, org_a, _, storage = api
    url, _, _ = dataset
    auth = headers({"import.read": [org_a]})

    def digest():
        contents = []
        with psycopg.connect(url) as connection:
            for table in (
                "executions",
                "execution_state_transitions",
                "source_files",
                "pipeline_issues",
                "pipeline_summaries",
                "file_inspections",
            ):
                contents.append(
                    connection.execute(
                        sql.SQL(
                            "SELECT to_jsonb(t) FROM synergia.{} t "
                            "ORDER BY to_jsonb(t)::text"
                        ).format(sql.Identifier(table))
                    ).fetchall()
                )
        return hashlib.sha256(json.dumps(contents, sort_keys=True).encode()).hexdigest()

    before = digest()
    for identifier in (
        "ready",
        "zero",
        "preparation",
        "rejected",
        "duplicate-a",
        "pending",
    ):
        for _ in range(2):
            assert (
                client.get(
                    f"/imports/{identifier}/result-summary", headers=auth
                ).status_code
                == 200
            )
            assert (
                client.get(f"/imports/{identifier}/issues", headers=auth).status_code
                == 200
            )
            assert (
                client.get(
                    f"/imports/{identifier}/issues/export", headers=auth
                ).status_code
                == 200
            )
    assert digest() == before
    assert not storage.exists()


def test_issues_pages_reconcile_55_and_filtered_totals_with_stable_order(api):
    client, headers, org_a, _, storage = api
    auth = headers({"import.read": [org_a]})
    pages = [
        client.get(f"/imports/ready/issues?page={page}", headers=auth).json()
        for page in (1, 2, 3, 4)
    ]
    assert [len(page["items"]) for page in pages] == [20, 20, 15, 0]
    assert all(page["pagination"]["total"] == 55 for page in pages)
    assert all(page["pagination"]["pages"] == 3 for page in pages)
    items = [item for page in pages for item in page["items"]]
    ids = [item["id"] for item in items]
    assert len(set(ids)) == 55 and ids == sorted(ids)
    newest = client.get(
        "/imports/ready/issues?page_size=100&sort=newest",
        headers=auth,
    ).json()
    assert [item["id"] for item in newest["items"]] == ids[::-1]
    totals = []
    for severity, expected in (("error", 20), ("warning", 35)):
        filtered = client.get(
            f"/imports/ready/issues?severity={severity}&page_size=100",
            headers=auth,
        ).json()
        totals.append(filtered["pagination"]["total"])
        assert len(filtered["items"]) == expected
        assert all(item["severity"] == severity for item in filtered["items"])
    summary = client.get("/imports/ready/result-summary", headers=auth).json()
    assert sum(totals) == summary["issues_total"] == len(items)
    assert all(
        item["sheet_name"] == "CSV" and item["column_name"] == "A" for item in items
    )
    assert [item["row_number"] for item in items] == list(range(2, 57))
    assert not storage.exists()


def test_csv_exports_all_filtered_rows_with_same_safe_projection_as_json(api):
    client, headers, org_a, _, storage = api
    auth = headers({"import.read": [org_a]})
    for query, expected in (("", 55), ("?severity=warning&sort=newest", 35)):
        response = client.get("/imports/ready/issues/export" + query, headers=auth)
        assert response.status_code == 200
        rows = list(csv.DictReader(StringIO(response.content.decode("utf-8-sig"))))
        page_query = query + ("&" if query else "?") + "page_size=100"
        page = client.get("/imports/ready/issues" + page_query, headers=auth).json()
        assert len(rows) == expected == page["pagination"]["total"]
        assert rows == [
            {key: "" if value is None else str(value) for key, value in item.items()}
            for item in page["items"]
        ]
        assert "private value" not in response.text
        assert "sensitive-cell" not in response.text
    empty = client.get("/imports/zero/issues/export", headers=auth)
    assert empty.status_code == 200
    assert list(csv.DictReader(StringIO(empty.content.decode("utf-8-sig")))) == []
    assert not storage.exists()


def test_issue_metadata_privacy_including_cross_execution_file_reference(api):
    client, headers, org_a, _, _ = api
    auth = headers({"import.read": [org_a]})
    response = client.get("/imports/unsafe/issues", headers=auth)
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["safe_file_name"] is item["sheet_name"] is item["column_name"] is None
    assert item["row_number"] is None and item["code"] == "unmapped_issue"
    export = client.get("/imports/unsafe/issues/export", headers=auth)
    assert export.status_code == 200
    for content in (response.text, export.text):
        for forbidden in ("password", "private", "person@", "details", "value"):
            assert forbidden not in content


def test_shared_query_preserves_legacy_evidence_filters_and_permissions(api, dataset):
    client, headers, org_a, _, _ = api
    with psycopg.connect(dataset[0]) as connection:
        occurred_at = connection.execute(
            "SELECT min(created_at) FROM synergia.pipeline_issues "
            "WHERE execution_id='ready'"
        ).fetchone()[0]
    auth = headers({"artifact.read": [org_a]})
    response = client.get(
        "/executions/ready/divergences",
        params={
            "source": "N-FP",
            "severity": "error",
            "code": "required_field",
            "workorder": "WO-SYN-194",
            "date_from": occurred_at.isoformat(),
            "date_to": occurred_at.isoformat(),
            "sort": "newest",
            "page_size": 100,
        },
        headers=auth,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pagination"]["total"] == len(data["items"]) == 20
    assert all(item["workorder_number"] == "WO-SYN-194" for item in data["items"])
    assert all(
        item["details"]["value"] == "synthetic-sensitive-cell" for item in data["items"]
    )
    assert [item["id"] for item in data["items"]] == sorted(
        [item["id"] for item in data["items"]],
        reverse=True,
    )
    assert client.get("/imports/ready/issues", headers=auth).status_code == 403


def test_issues_real_authorization_import_read_only_and_no_permission_bypass(api):
    client, headers, org_a, org_b, _ = api
    for endpoint in ("issues", "issues/export"):
        assert client.get(f"/imports/ready/{endpoint}").status_code == 401
        unrelated = headers({"execution.read": [org_a], "artifact.read": [org_a]})
        assert (
            client.get(
                f"/imports/ready/{endpoint}",
                headers=unrelated,
            ).status_code
            == 403
        )
        auth = headers({"import.read": [org_a], "artifact.read": [org_b]})
        assert client.get(f"/imports/ready/{endpoint}", headers=auth).status_code == 200
        for identifier in ("prior-b", "no-iam", "missing"):
            assert (
                client.get(
                    f"/imports/{identifier}/{endpoint}",
                    headers=auth,
                ).status_code
                == 404
            )
        assert (
            client.get(
                f"/imports/prior-b/{endpoint}",
                headers=headers({"import.read": [None]}),
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/imports/no-iam/{endpoint}",
                headers=headers({"import.read": [None]}),
            ).status_code
            == 404
        )
    auth = headers({"import.read": [org_a]})
    assert client.get("/executions/ready/divergences", headers=auth).status_code == 403
    assert client.get("/executions/ready/evidences", headers=auth).status_code == 403


def test_direct_issues_queries_reapply_root_scope_and_export_is_read_only(dataset):
    url, org_a, org_b = dataset
    repository = PostgresImportRepository(url)
    for identifier, scope in (
        ("prior-b", frozenset({org_a})),
        ("ready", frozenset()),
        ("no-iam", None),
    ):
        assert (
            repository.issues(
                identifier,
                organization_scopes=scope,
                severity=None,
                page=1,
                page_size=20,
                sort="oldest",
            )
            is None
        )
        with repository.issue_csv(
            identifier,
            organization_scopes=scope,
            severity=None,
            sort="oldest",
        ) as chunks:
            assert chunks is None
    with psycopg.connect(url, row_factory=psycopg.rows.dict_row) as connection:
        with open_import_issue_csv(
            connection,
            "ready",
            organization_scopes=frozenset({org_a}),
            severity=None,
            sort="oldest",
        ) as chunks:
            assert (
                connection.execute("SHOW transaction_read_only").fetchone()[
                    "transaction_read_only"
                ]
                == "on"
            )
            assert (
                connection.execute("SHOW transaction_isolation").fetchone()[
                    "transaction_isolation"
                ]
                == "repeatable read"
            )
            content = "".join(chunks).lstrip("\ufeff")
            assert len(list(csv.DictReader(StringIO(content)))) == 55
    with psycopg.connect(url, row_factory=psycopg.rows.dict_row) as connection:
        assert (
            read_import_issues(
                connection,
                "prior-b",
                organization_scopes=frozenset({org_b}),
                severity=None,
                page=1,
                page_size=20,
                sort="oldest",
            ).pagination.total
            == 1
        )


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_real_pipeline_known_row_errors_are_visible_with_only_import_read(
    api,
    extension,
):
    client, headers, org_a, _, _ = api
    rows = [
        ["workorder", "status", "planned_quantity"],
        [None, "open", -1],
        ["WO-SYN194-" + uuid4().hex, "open", 1],
    ]
    if extension == "csv":
        buffer = StringIO(newline="")
        csv.writer(buffer).writerows(rows)
        content = buffer.getvalue().encode()
        media_type = "text/csv"
    else:
        workbook = Workbook()
        workbook.active.title = "Dados"
        for row in rows:
            workbook.active.append(row)
        buffer = BytesIO()
        workbook.save(buffer)
        content = buffer.getvalue()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    uploaded = client.post(
        "/imports",
        data={"source": "N-FP", "organization_id": str(org_a)},
        files={"file": (f"synthetic.{extension}", content, media_type)},
        headers=headers({"import.create": [org_a]}),
    )
    assert uploaded.status_code == 201, uploaded.text
    identifier = uploaded.json()["execution_id"]
    assert uploaded.json()["status"] == "completed_with_errors"
    auth = headers({"import.read": [org_a]})
    result = client.get(f"/imports/{identifier}/result-summary", headers=auth).json()
    assert result["summary"]["rows_read"] == 2
    assert result["summary"]["rejected_records"] == 1
    issues = client.get(f"/imports/{identifier}/issues", headers=auth).json()
    assert issues["pagination"]["total"] == result["issues_total"]
    required = next(
        item for item in issues["items"] if item["code"] == "required_field"
    )
    quantity = next(
        item for item in issues["items"] if item["code"] == "invalid_quantity"
    )
    assert required["row_number"] == quantity["row_number"] == 2
    assert required["column_name"] == "A" and quantity["column_name"] == "C"


def test_legacy_get_and_duplicate_post_hide_previous_without_import_read_scope(
    api,
    dataset,
):
    client, headers, org_a, org_b, _ = api
    auth = headers({"import.read": [org_a]})
    for identifier, previous in (
        ("duplicate-a", "prior-a"),
        ("duplicate-b", None),
        ("duplicate-no-iam", None),
    ):
        response = client.get(f"/imports/{identifier}", headers=auth)
        assert response.status_code == 200
        assert response.json()["duplicate_of_execution_id"] == previous
    content = ("workorder,status\nWO-SYN-" + uuid4().hex + ",open\n").encode()

    def upload(organization, grants):
        return client.post(
            "/imports",
            data={"source": "N-FP", "organization_id": str(organization)},
            files={"file": ("synthetic.csv", content, "text/csv")},
            headers=headers(grants),
        )

    previous = upload(org_b, {"import.create": [org_b]})
    assert previous.status_code == 201, previous.text
    previous_id = previous.json()["execution_id"]
    for grants in (
        {"import.create": [org_a], "import.read": [org_a]},
        {"import.create": [org_b]},
    ):
        duplicate = upload(org_a if "import.read" in grants else org_b, grants)
        assert duplicate.status_code == 409, duplicate.text
        assert duplicate.json()["error"]["details"]["duplicate_of_execution_id"] is None
        assert previous_id not in duplicate.text
        identifier = duplicate.json()["error"]["details"]["execution_id"]
        with psycopg.connect(dataset[0]) as connection:
            assert (
                connection.execute(
                    "SELECT duplicate_of_execution_id FROM synergia.executions "
                    "WHERE id=%s",
                    (identifier,),
                ).fetchone()[0]
                == previous_id
            )
    allowed = upload(org_a, {"import.create": [org_a], "import.read": [org_b]})
    assert allowed.status_code == 409
    assert (
        allowed.json()["error"]["details"]["duplicate_of_execution_id"] == previous_id
    )
