from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app import pipeline
from app.business_rules import RULE_CATALOG
from app.execution import PIPELINE_VERSION, import_fingerprint, validate_transition
from app.imports import get_repository
from app.main import app


class MemoryRepository:
    def __init__(self) -> None:
        self.executions: dict[str, dict] = {}
        self.hashes: dict[str, str] = {}
        self.normalized_records: dict[str, list[dict]] = {}
        self.files: dict[str, list[dict]] = {}
        self.next_file_id = 1
        self.processing_claims: dict[str, str] = {}
        self.inspections: dict[str, list[dict]] = {}

    def start(
        self,
        execution_id: str,
        source: str,
        actor_type: str,
        actor: str,
        pipeline_version: str = PIPELINE_VERSION,
        rule_catalog_version: str = RULE_CATALOG["version"],
    ) -> None:
        self.executions[execution_id] = {
            "execution_id": execution_id,
            "status": "pending",
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
            "pipeline_version": pipeline_version,
            "rule_catalog_version": rule_catalog_version,
            "state_version": 0,
        }
        self.files[execution_id] = []
        self.inspections[execution_id] = []

    def record_inspection(self, execution_id: str, source: str, result) -> int:
        inspection_id = sum(len(items) for items in self.inspections.values()) + 1
        self.inspections[execution_id].append(
            {
                "inspection_id": inspection_id,
                "source": source,
                "original_file_name": result.original_name,
                "extension": result.extension.lstrip(".") or None,
                "declared_media_type": result.declared_media_type or None,
                "detected_media_type": result.detected_media_type,
                "size_bytes": result.size_bytes,
                "sha256": result.sha256,
                "decision": result.decision.value,
                "reason_code": result.reason_code,
                "analyzed_at": result.analyzed_at,
                "retained_until": result.retained_until,
                "discarded_at": result.discarded_at,
                "internal_name": result.internal_name,
            }
        )
        return inspection_id

    def list_inspections(self, execution_id: str) -> list[dict]:
        return self.inspections.get(execution_id, [])

    def mark_inspections_discarded(self, internal_stems: list[str]) -> None:
        for inspections in self.inspections.values():
            for inspection in inspections:
                if inspection["internal_name"].split(".", 1)[0] in internal_stems:
                    inspection["discarded_at"] = datetime.now(UTC)

    def list_expired_inspection_stems(self) -> list[str]:
        now = datetime.now(UTC)
        return [
            inspection["internal_name"].split(".", 1)[0]
            for inspections in self.inspections.values()
            for inspection in inspections
            if inspection["decision"] == "rejected"
            and inspection["discarded_at"] is None
            and inspection["retained_until"] <= now
        ]

    def claim_file(
        self, execution_id: str, **metadata
    ) -> tuple[int | None, str | None]:
        source_file_id = self.next_file_id
        self.next_file_id += 1
        self.files[execution_id].append({"id": source_file_id, **metadata})
        execution = self.executions[execution_id]
        if execution["file_name"] is None:
            execution.update(
                file_name=metadata["file_name"],
                extension=metadata["extension"],
                size_bytes=metadata["size_bytes"],
                sha256=metadata["digest"],
            )
        self.hashes[metadata["digest"]] = execution_id
        return source_file_id, None

    def claim_processing(self, execution_id: str, file_hashes: list[str]) -> str | None:
        execution = self.executions[execution_id]
        request_fingerprint = import_fingerprint(
            file_hashes,
            execution["pipeline_version"],
            execution["rule_catalog_version"],
        )
        duplicate_of = self.processing_claims.get(request_fingerprint)
        if duplicate_of is None:
            self.processing_claims[request_fingerprint] = execution_id
        return duplicate_of

    def release_claim(self, execution_id: str) -> None:
        self.files[execution_id] = []

    def transition_execution(self, execution_id: str, target: str, reason: str) -> None:
        execution = self.executions[execution_id]
        validate_transition(execution["status"], target)
        execution["status"] = target
        execution["state_version"] += 1
        execution["failure_reason"] = (
            reason if target in {"failed", "validation_failed"} else None
        )
        if target in {
            "completed",
            "completed_with_errors",
            "validation_failed",
            "failed",
            "duplicate",
            "cancelled",
        }:
            execution["finished_at"] = datetime.now(UTC)

    def mark_completed(self, execution_id: str) -> None:
        self.transition_execution(execution_id, "completed", "pipeline_completed")

    def mark_validation_failed(self, execution_id: str) -> None:
        self.transition_execution(
            execution_id,
            "validation_failed",
            "validation_failed",
        )

    def save_normalized_records(self, execution_id: str, records: list[dict]) -> None:
        self.normalized_records[execution_id] = records

    def commit_pipeline(self, execution_id: str, result: dict) -> None:
        self.normalized_records[execution_id] = result["normalized_records"]
        self.transition_execution(execution_id, result["status"], result["status"])

    def abort_claim(self, execution_id: str, reason: str) -> None:
        for metadata in self.files[execution_id]:
            self.hashes.pop(metadata["digest"], None)
        self.files[execution_id] = []
        self.transition_execution(execution_id, "failed", reason)

    def finish(
        self,
        execution_id: str,
        state: str,
        reason: str,
        duplicate_of: str | None = None,
    ) -> None:
        self.executions[execution_id]["duplicate_of_execution_id"] = duplicate_of
        self.transition_execution(execution_id, state, reason)

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
    stored = [
        path
        for path in storage.glob(
            f"accepted/n_fp/{body['execution_id']}/*.{filename.rsplit('.', 1)[-1]}"
        )
        if len(path.stem) == 48
    ]
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


def test_rejection_is_auditable_without_exposing_internal_paths(api) -> None:
    client, _, storage = api
    response = client.post(
        "/imports",
        data={"source": "N-FP", "imported_by": "security-test"},
        files={"file": ("report.csv", b"<script>alert(1)</script>", "text/csv")},
    )

    assert response.status_code == 415
    execution_id = response.json()["error"]["details"]["execution_id"]
    inspections = client.get(f"/imports/{execution_id}/inspections")
    assert inspections.status_code == 200
    record = inspections.json()[0]
    assert record["decision"] == "rejected"
    assert record["reason_code"] == "disguised_active_content"
    assert record["original_file_name"] == "report.csv"
    assert record["sha256"]
    assert "path" not in record
    assert "internal_name" not in record
    assert not list((storage / "accepted").glob("**/*"))
    assert list((storage / "quarantine" / execution_id).glob("*.upload"))


@pytest.mark.parametrize(
    ("filename", "content", "reason", "http_status"),
    [
        ("empty.csv", b"", "empty_file", 422),
        ("bad.json", b"{invalid", "corrupted_file", 422),
        ("bad.xlsx", b"not-a-workbook", "content_signature_mismatch", 415),
    ],
)
def test_rejects_empty_and_invalid_files(
    api, filename, content, reason, http_status
) -> None:
    client, _, _ = api
    response = client.post(
        "/imports",
        data={"source": "TMS", "imported_by": "test-user"},
        files={"file": (filename, content)},
    )

    assert response.status_code == http_status
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
    assert not (storage / "accepted" / "owm" / detail["execution_id"]).exists()
    assert len(list(storage.glob("accepted/**/**/*.csv"))) == 1


def test_storage_failure_releases_hash_claim_and_removes_artifacts(
    api, monkeypatch
) -> None:
    client, repository, storage = api

    def fail_move(*_args, **_kwargs) -> None:
        raise OSError("synthetic storage failure")

    monkeypatch.setattr("app.imports.release_to_accepted", fail_move)
    response = client.post(
        "/imports",
        data={"source": "OWM", "technical_origin": "fixture"},
        files={"file": ("entry.csv", b"id\n1\n", "text/csv")},
    )

    assert response.status_code == 500
    execution_id = response.json()["error"]["details"]["execution_id"]
    assert repository.get(execution_id)["status"] == "failed"
    assert repository.hashes == {}
    assert not list(storage.glob("accepted/**/*.csv"))
    assert not list(storage.glob("quarantine/**/*.upload"))


def test_second_file_claim_failure_rolls_back_prepared_batch(api, monkeypatch) -> None:
    client, repository, storage = api
    original_claim = repository.claim_file
    claim_count = 0

    def fail_second_claim(execution_id: str, **metadata):
        nonlocal claim_count
        claim_count += 1
        if claim_count == 2:
            raise RuntimeError("synthetic second claim failure")
        return original_claim(execution_id, **metadata)

    monkeypatch.setattr(repository, "claim_file", fail_second_claim)
    response = client.post(
        "/imports",
        data={"source": ["N-FP", "OWM"], "imported_by": "test-user"},
        files=[
            (
                "file",
                ("plan.csv", b"workorder\nWO-1\n", "text/csv"),
            ),
            (
                "file",
                ("receiving.csv", b"workorder\nWO-1\n", "text/csv"),
            ),
        ],
    )

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "preparation_error"
    execution_id = error["details"]["execution_id"]
    assert repository.get(execution_id)["status"] == "failed"
    assert repository.get(execution_id)["failure_reason"] == "preparation_error"
    assert repository.files[execution_id] == []
    assert repository.hashes == {}
    assert not list(storage.glob("accepted/**/*.*"))


def test_artifact_failure_does_not_commit_pipeline(api, monkeypatch) -> None:
    client, repository, storage = api
    original_replace = Path.replace

    def fail_summary(self: Path, target: Path) -> Path:
        if Path(target).name == "pipeline-summary.json":
            raise OSError("synthetic artifact failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_summary)
    response = client.post(
        "/imports",
        data={"source": "N-FP", "imported_by": "test-user"},
        files={"file": ("entry.csv", b"workorder\nWO-1\n", "text/csv")},
    )

    assert response.status_code == 500
    execution_id = response.json()["error"]["details"]["execution_id"]
    assert repository.get(execution_id)["status"] == "failed"
    assert execution_id not in repository.normalized_records
    assert not list((storage / "accepted" / "n_fp" / execution_id).glob("*.json"))


def test_original_file_is_interpreted_only_once(api, monkeypatch) -> None:
    client, _, _ = api
    original_read = pipeline.read_tables
    calls = 0

    def counting_read(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_read(*args, **kwargs)

    monkeypatch.setattr("app.pipeline.read_tables", counting_read)
    response = client.post(
        "/imports",
        data={"source": "N-FP", "imported_by": "test-user"},
        files={"file": ("entry.csv", b"workorder\nWO-1\n", "text/csv")},
    )

    assert response.status_code == 201
    assert calls == 1


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
    directory = storage / "accepted" / "n_fp" / execution_id
    assert list(directory.glob("*.csv"))
    assert (directory / "validation-report.json").exists()


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
    directory = storage / "accepted" / "n_fp" / execution_id
    assert list(directory.glob("*.csv"))
    assert (directory / "validation-report.json").exists()


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
    assert normalized["processing"]["execution_id"] == execution_id
    assert normalized["processing"]["rule_catalog_version"] == "1.0.0"
    assert normalized["processing"]["summary"]["consolidated_workorders"] == 1
    provenance = normalized["processing"]["consolidation"]["workorders"][0][
        "provenance"
    ]["workorder_number"][0]
    assert provenance["source_file_id"] == repository.files[execution_id][0]["id"]
    assert (
        storage / "accepted" / "n_fp" / execution_id / "normalized-data.json"
    ).exists()


def test_multisource_upload_consolidates_precedence_and_divergence(
    tmp_path, monkeypatch
) -> None:
    repository = MemoryRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    monkeypatch.setenv("IMPORT_STORAGE_DIR", str(tmp_path))

    async def request() -> tuple[httpx.Response, dict]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/imports",
                data={"source": ["N-FP", "OWM"], "imported_by": "batch"},
                files=[
                    (
                        "file",
                        (
                            "plan.csv",
                            b"workorder,planned_quantity\nWO-MULTI,10\n",
                            "text/csv",
                        ),
                    ),
                    (
                        "file",
                        (
                            "receiving.csv",
                            b"workorder,planned_quantity,received_quantity,"
                            b"released_quantity\nWO-MULTI,12,10,6\n",
                            "text/csv",
                        ),
                    ),
                ],
            )
            execution_id = response.json()["execution_id"]
            normalized = (
                await client.get(f"/imports/{execution_id}/normalized-data")
            ).json()
            return response, normalized

    try:
        response, normalized = asyncio.run(request())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    execution_id = response.json()["execution_id"]
    processing = normalized["processing"]
    workorder = processing["consolidation"]["workorders"][0]
    source_file_ids = {
        origin["source_file_id"]
        for origin in workorder["provenance"]["planned_quantity"]
    }

    assert workorder["planned_quantity"] == 10
    assert workorder["selected_quantity_sources"]["planned_quantity"] == "N-FP"
    assert workorder["partially_released"] is True
    assert len(source_file_ids) == 2
    assert None not in source_file_ids
    assert source_file_ids == {item["id"] for item in repository.files[execution_id]}
    assert processing["summary"]["eligible_normalized_records"] == 2
    assert processing["summary"]["classifications_by_rule"]["source_divergence"] == 1
    assert (
        tmp_path / "accepted" / "n_fp" / execution_id / "normalized-data.json"
    ).exists()
    assert list((tmp_path / "accepted" / "n_fp" / execution_id).glob("*.csv"))
    assert list((tmp_path / "accepted" / "owm" / execution_id).glob("*.csv"))


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
