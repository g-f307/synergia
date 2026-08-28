from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.imports import get_repository
from app.main import app


class MemoryRepository:
    def __init__(self) -> None:
        self.executions: dict[str, dict] = {}
        self.hashes: dict[str, str] = {}
        self.normalized_records: dict[str, list[dict]] = {}

    def start(
        self, execution_id: str, source: str, actor_type: str, actor: str
    ) -> None:
        self.executions[execution_id] = {
            "execution_id": execution_id,
            "status": "running",
            "source": source,
            "file_name": None,
            "extension": None,
            "size_bytes": None,
            "sha256": None,
            "actor_type": actor_type,
            "actor_identifier": actor,
            "started_at": datetime.now(UTC),
            "finished_at": None,
            "failure_reason": None,
            "duplicate_of_execution_id": None,
        }

    def claim_file(self, execution_id: str, **metadata) -> str | None:
        duplicate_of = self.hashes.get(metadata["digest"])
        if duplicate_of:
            return duplicate_of
        execution = self.executions[execution_id]
        execution.update(
            file_name=metadata["file_name"],
            extension=metadata["extension"],
            size_bytes=metadata["size_bytes"],
            sha256=metadata["digest"],
        )
        self.hashes[metadata["digest"]] = execution_id
        return None

    def mark_completed(self, execution_id: str) -> None:
        self.executions[execution_id].update(
            status="completed", finished_at=datetime.now(UTC)
        )

    def mark_validation_failed(self, execution_id: str) -> None:
        self.executions[execution_id].update(
            status="validation_failed",
            failure_reason="validation_failed",
            finished_at=datetime.now(UTC),
        )

    def save_normalized_records(self, execution_id: str, records: list[dict]) -> None:
        self.normalized_records[execution_id] = records

    def commit_pipeline(self, execution_id: str, result: dict) -> None:
        self.normalized_records[execution_id] = result["normalized_records"]
        self.executions[execution_id].update(
            status=result["status"],
            failure_reason=(
                "validation_failed" if result["blocking"] else None
            ),
            finished_at=datetime.now(UTC),
        )

    def abort_claim(self, execution_id: str, reason: str) -> None:
        execution = self.executions[execution_id]
        if execution["sha256"]:
            self.hashes.pop(execution["sha256"], None)
        execution.update(
            status="failed", failure_reason=reason, finished_at=datetime.now(UTC)
        )

    def finish(
        self,
        execution_id: str,
        state: str,
        reason: str,
        duplicate_of: str | None = None,
    ) -> None:
        self.executions[execution_id].update(
            status=state,
            failure_reason=reason,
            duplicate_of_execution_id=duplicate_of,
            finished_at=datetime.now(UTC),
        )

    def get(self, execution_id: str) -> dict | None:
        return self.executions.get(execution_id)


@pytest.fixture
def api(tmp_path, monkeypatch):
    repository = MemoryRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    monkeypatch.setenv("IMPORT_STORAGE_DIR", str(tmp_path))
    with TestClient(app) as client:
        yield client, repository, tmp_path
    app.dependency_overrides.clear()


def xlsx_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["workorder", "status"])
    sheet.append(["WO-0001", "open"])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("entrada.csv", b"workorder,status\nWO-0001,open\n", "text/csv"),
        (
            "entrada.json",
            json.dumps([{"workorder": "WO-0001"}]).encode(),
            "application/json",
        ),
        (
            "entrada.xlsx",
            None,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ],
)
def test_accepts_supported_files(api, filename, content, content_type) -> None:
    client, _, storage = api
    original = xlsx_bytes() if content is None else content

    response = client.post(
        "/imports",
        data={"source": "N-FP", "imported_by": "test-user"},
        files={"file": (filename, original, content_type)},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["source"] == "N-FP"
    assert body["actor_identifier"] == "test-user"
    stored = list(storage.glob(f"n_fp/{body['execution_id']}/original.*"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == original


def test_rejects_unsupported_extension_and_keeps_failure_trace(api) -> None:
    client, _, _ = api
    response = client.post(
        "/imports",
        data={"source": "OWM", "technical_origin": "controlled-test"},
        files={"file": ("entrada.txt", b"not accepted", "text/plain")},
    )

    assert response.status_code == 415
    execution_id = response.json()["error"]["details"]["execution_id"]
    status_response = client.get(f"/imports/{execution_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "failed"
    assert status_response.json()["failure_reason"] == "unsupported_extension"


@pytest.mark.parametrize(
    ("filename", "content", "reason"),
    [
        ("empty.csv", b"", "empty_file"),
        ("bad.json", b"{invalid", "invalid_file"),
        ("bad.xlsx", b"not-a-workbook", "invalid_file"),
    ],
)
def test_rejects_empty_and_invalid_files(api, filename, content, reason) -> None:
    client, _, _ = api
    response = client.post(
        "/imports",
        data={"source": "TMS", "imported_by": "test-user"},
        files={"file": (filename, content)},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == reason


def test_identifies_duplicate_by_hash_and_exposes_both_statuses(api) -> None:
    client, _, storage = api
    request = {
        "data": {"source": "GMES/OQC", "imported_by": "test-user"},
        "files": {"file": ("first.csv", b"id\n1\n", "text/csv")},
    }
    first = client.post("/imports", **request)
    second = client.post(
        "/imports",
        data={"source": "OWM", "technical_origin": "fixture"},
        files={"file": ("renamed.csv", b"id\n1\n", "text/csv")},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    detail = second.json()["error"]["details"]
    assert detail["duplicate_of_execution_id"] == first.json()["execution_id"]
    duplicate_status = client.get(f"/imports/{detail['execution_id']}").json()
    assert duplicate_status["status"] == "duplicate"
    assert not (storage / "owm" / detail["execution_id"]).exists()
    assert len(list(storage.glob("**/original.csv"))) == 1


def test_storage_failure_releases_hash_claim_and_removes_artifacts(
    api, monkeypatch
) -> None:
    client, repository, storage = api

    def fail_move(*_args, **_kwargs) -> None:
        raise OSError("synthetic storage failure")

    monkeypatch.setattr("app.imports.shutil.move", fail_move)
    response = client.post(
        "/imports",
        data={"source": "OWM", "technical_origin": "fixture"},
        files={"file": ("entry.csv", b"id\n1\n", "text/csv")},
    )

    assert response.status_code == 500
    execution_id = response.json()["error"]["details"]["execution_id"]
    assert repository.get(execution_id)["status"] == "failed"
    assert repository.hashes == {}
    assert not list(storage.glob("**/original.csv"))


def test_requires_actor_and_returns_not_found(api) -> None:
    client, _, _ = api
    missing_actor = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("entry.json", b"{}", "application/json")},
    )
    assert missing_actor.status_code == 422
    assert missing_actor.json()["error"]["code"] == "missing_actor"
    not_found = client.get("/imports/unknown")
    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "not_found"


def test_logs_trace_identifiers_without_file_contents(api, caplog) -> None:
    client, _, _ = api
    confidential_value = b"workorder\nCONFIDENTIAL-WO-VALUE\n"

    with caplog.at_level("INFO", logger="synergia.imports"):
        response = client.post(
            "/imports",
            data={"source": "OWM", "technical_origin": "synthetic-fixture"},
            files={"file": ("controlled.csv", confidential_value, "text/csv")},
        )

    assert response.status_code == 201
    assert response.json()["execution_id"] in caplog.text
    assert "CONFIDENTIAL-WO-VALUE" not in caplog.text


def test_validation_report_endpoint_and_blocked_execution(api) -> None:
    client, _, storage = api
    response = client.post(
        "/imports",
        data={"source": "N-FP", "imported_by": "validator"},
        files={"file": ("invalid.csv", b"status\nopen\n", "text/csv")},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "validation_failed"
    execution_id = response.json()["execution_id"]
    report_response = client.get(f"/imports/{execution_id}/validation-report")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["blocking"] is True
    assert report["issues"][0]["file_name"] == "invalid.csv"
    assert (storage / "n_fp" / execution_id / "original.csv").exists()
    assert (storage / "n_fp" / execution_id / "validation-report.json").exists()


def test_malformed_csv_finishes_with_persisted_blocking_report(api) -> None:
    client, repository, storage = api
    response = client.post(
        "/imports",
        data={"source": "N-FP", "imported_by": "validator"},
        files={
            "file": (
                "malformed.csv",
                b'workorder_number,status\nWO-1,"unterminated\n',
                "text/csv",
            )
        },
    )

    assert response.status_code == 201
    execution_id = response.json()["execution_id"]
    assert repository.get(execution_id)["status"] == "validation_failed"
    report = client.get(f"/imports/{execution_id}/validation-report").json()
    assert report["blocking"] is True
    assert report["issues"][0]["code"] == "read_error"
    assert report["issues"][0]["row"] == 2
    assert (storage / "n_fp" / execution_id / "original.csv").exists()
    assert (storage / "n_fp" / execution_id / "validation-report.json").exists()


def test_valid_import_persists_and_exposes_normalized_data(api) -> None:
    client, repository, storage = api
    response = client.post(
        "/imports",
        data={"source": "N-FP", "imported_by": "normalizer"},
        files={
            "file": (
                "normalizable.csv",
                b"Work Order,planned_date,status\n wo - 0001 ,27/08/2026,Aberto\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 201
    execution_id = response.json()["execution_id"]
    normalized_response = client.get(f"/imports/{execution_id}/normalized-data")
    assert normalized_response.status_code == 200
    normalized = normalized_response.json()
    assert normalized["records"][0]["values"]["workorder_number"] == "WO-0001"
    assert normalized["records"][0]["values"]["planned_date"] == "2026-08-27"
    assert normalized["records"][0]["values"]["status"] == "open"
    assert (
        normalized["records"][0]["original_values"]["workorder_number"] == " wo - 0001 "
    )
    assert repository.normalized_records[execution_id] == normalized["records"]
    assert (storage / "n_fp" / execution_id / "normalized-data.json").exists()


def test_pipeline_exposes_partial_summary_and_keeps_valid_rows(api) -> None:
    client, _, _ = api
    response = client.post(
        "/imports",
        data={"source": "N-FP", "technical_origin": "pipeline-test"},
        files={
            "file": (
                "partial.csv",
                b"workorder,planned_quantity\nWO-1,10\nWO-2,invalid\nWO-3,2\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 201
    execution_id = response.json()["execution_id"]
    summary = client.get(f"/imports/{execution_id}/pipeline-summary").json()
    assert summary == {
        "rows_read": 3,
        "valid_records": 2,
        "rejected_records": 1,
        "normalized_records": 2,
        "errors": 1,
        "warnings": 0,
    }
    normalized = client.get(f"/imports/{execution_id}/normalized-data").json()
    assert [record["row"] for record in normalized["records"]] == [2, 4]
