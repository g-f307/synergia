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
        self.issues: dict[str, list[dict]] = {}

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

    def save_validation_issues(self, execution_id: str, issues: list[dict]) -> None:
        self.issues[execution_id] = issues

    def get_validation_issues(self, execution_id: str) -> list[dict]:
        return self.issues.get(execution_id, [])

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
    sheet.append(["workorder_number", "planned_quantity", "status"])
    sheet.append(["WO-0001", 10, "open"])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        (
            "entrada.csv",
            b"workorder_number,planned_quantity,status\nWO-0001,10,open\n",
            "text/csv",
        ),
        (
            "entrada.json",
            json.dumps(
                [
                    {
                        "workorder_number": "WO-0001",
                        "planned_quantity": 10,
                        "status": "open",
                    }
                ]
            ).encode(),
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
    execution_id = response.json()["detail"]["execution_id"]
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
    assert response.json()["detail"]["code"] == reason


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
    detail = second.json()["detail"]
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
    execution_id = response.json()["detail"]["execution_id"]
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
    assert client.get("/imports/unknown").status_code == 404


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
