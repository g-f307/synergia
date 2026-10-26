from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID

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
        organization_id: UUID,
        user_id: UUID,
        session_id: UUID,
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

    def organization_code(self, organization_id: UUID) -> str:
        return "org-001"

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
        self.processing_claims = {
            fingerprint: owner
            for fingerprint, owner in self.processing_claims.items()
            if owner != execution_id
        }
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
    assert body["actor_identifier"] == "00000000-0000-0000-0000-000000000001"
    stored = [
        path
        for path in storage.glob(
            f"accepted/n_fp/{body['execution_id']}/*.{filename.rsplit('.', 1)[-1]}"
        )
        if len(path.stem) == 48
    ]
    assert len(stored) == 1
    assert stored[0].read_bytes() == original


def test_exposes_active_upload_policy_per_source(api, monkeypatch) -> None:
    client, _, _ = api
    monkeypatch.setenv("UPLOAD_ALLOWED_EXTENSIONS_N_FP", "csv,xlsx")
    monkeypatch.setenv("UPLOAD_MAX_BYTES_N_FP", "4096")

    response = client.get("/imports/policy")

    assert response.status_code == 200
    body = response.json()
    by_source = {item["source"]: item for item in body["policies"]}
    assert by_source["N-FP"] == {
        "source": "N-FP",
        "allowed_extensions": ["csv", "xlsx"],
        "max_bytes": 4096,
    }
    assert by_source["OWM"]["max_bytes"] == 25 * 1024 * 1024
    assert body["organizations"] == [
        {
            "id": "44444444-4444-4444-8444-444444444444",
            "organization_code": "org-001",
            "display_name": "Organization 001",
        }
    ]


def test_upload_policy_fails_closed_for_an_unsupported_extension(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_ALLOWED_EXTENSIONS_N_FP", "csv,xml")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/imports/policy")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "xml" not in response.text


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


def test_f01_failure_after_reservation_marks_execution_failed(api, monkeypatch) -> None:
    client, repository, storage = api

    def interrupt_after_reservation(*_args, **_kwargs):
        raise RuntimeError("synthetic F01 interruption")

    monkeypatch.setattr("app.imports.purge_quarantined", interrupt_after_reservation)
    response = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("f01.csv", b"workorder\nWO-F01\n", "text/csv")},
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "preparation_error"
    execution_id = response.json()["error"]["details"]["execution_id"]
    assert repository.get(execution_id)["status"] == "failed"
    assert repository.files[execution_id] == []
    assert not list(storage.glob("accepted/**/*.*"))


def test_f02_failure_during_validation_does_not_publish_pipeline(
    api, monkeypatch
) -> None:
    client, repository, storage = api

    def interrupt_validation(*_args, **_kwargs):
        raise RuntimeError("synthetic F02 interruption")

    monkeypatch.setattr("app.pipeline.validate_tables", interrupt_validation)
    response = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("f02.csv", b"workorder\nWO-F02\n", "text/csv")},
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "pipeline_error"
    execution_id = response.json()["error"]["details"]["execution_id"]
    assert repository.get(execution_id)["status"] == "failed"
    assert execution_id not in repository.normalized_records
    assert not list((storage / "accepted" / "n_fp" / execution_id).glob("*.json"))


def test_f04_failure_before_commit_does_not_publish_pipeline(api, monkeypatch) -> None:
    client, repository, _ = api

    def interrupt_before_commit(*_args, **_kwargs):
        raise RuntimeError("synthetic F04 pre-commit interruption")

    monkeypatch.setattr(repository, "commit_pipeline", interrupt_before_commit)
    response = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("f04.csv", b"workorder\nWO-F04\n", "text/csv")},
    )

    assert response.status_code == 500
    execution_id = response.json()["error"]["details"]["execution_id"]
    assert repository.get(execution_id)["status"] == "failed"
    assert execution_id not in repository.normalized_records


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
    invalid_request = client.post(
        "/imports",
        data={},
        files={"file": ("entry.json", b"{}", "application/json")},
    )
    assert invalid_request.status_code == 422
    assert invalid_request.json()["error"]["code"] == "request_validation_error"
    not_found = client.get("/imports/unknown")
    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "not_found"


def test_logs_trace_identifiers_without_file_contents(api, caplog) -> None:
    client, _, _ = api
    confidential_value = b"workorder\nCONFIDENTIAL-WO-VALUE\n"
    telemetry_logger = logging.getLogger("synergia.telemetry")
    telemetry_logger.addHandler(caplog.handler)

    try:
        with caplog.at_level("INFO", logger="synergia.telemetry"):
            response = client.post(
                "/imports",
                data={"source": "OWM", "technical_origin": "synthetic-fixture"},
                files={"file": ("controlled.csv", confidential_value, "text/csv")},
            )
    finally:
        telemetry_logger.removeHandler(caplog.handler)

    assert response.status_code == 201
    fields = [getattr(record, "synergia_fields", {}) for record in caplog.records]
    assert any(
        item.get("execution_id") == response.json()["execution_id"] for item in fields
    )
    assert "CONFIDENTIAL-WO-VALUE" not in str(fields)


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


def _workbook_with_rows(rows: int, *, invalid: bool = False) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["workorder", "status"])
    for index in range(rows):
        sheet.append([None if invalid else f"WO-{index:04d}", "open"])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_capacity_rejection_at_admission_is_structured_and_auditable(
    api, monkeypatch
) -> None:
    client, _, storage = api
    monkeypatch.setenv("INGESTION_MAX_ROWS", "5")

    response = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("grande.xlsx", _workbook_with_rows(20), XLSX_TYPE)},
    )

    assert response.status_code == 413
    error = response.json()["error"]
    assert error["code"] == "workbook_row_limit"
    assert error["details"]["limit"] == 5
    assert error["details"]["observed"] == 21
    assert error["details"]["guidance"]
    execution_id = error["details"]["execution_id"]
    assert client.get(f"/imports/{execution_id}").json()["failure_reason"] == (
        "workbook_row_limit"
    )
    inspection = client.get(f"/imports/{execution_id}/inspections").json()[0]
    assert inspection["decision"] == "rejected"
    assert inspection["reason_code"] == "workbook_row_limit"
    assert not list(storage.glob("accepted/**/*.xlsx"))


def test_capacity_rejection_while_processing_cleans_up_and_allows_a_retry(
    api, monkeypatch
) -> None:
    client, repository, storage = api
    content = _workbook_with_rows(20, invalid=True)
    monkeypatch.setenv("INGESTION_MAX_ISSUES", "5")

    rejected = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("sujo.xlsx", content, XLSX_TYPE)},
    )

    assert rejected.status_code == 422
    error = rejected.json()["error"]
    assert error["code"] == "ingestion_issue_limit"
    assert error["details"]["limit"] == 5
    assert error["details"]["guidance"]
    assert not [path for path in storage.glob("accepted/**/*") if path.is_file()]
    assert all(not records for records in repository.normalized_records.values())

    monkeypatch.delenv("INGESTION_MAX_ISSUES")
    retried = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("sujo.xlsx", content, XLSX_TYPE)},
    )

    assert retried.status_code == 201
    assert retried.json()["execution_id"] != error["details"]["execution_id"]


def test_capacity_rejections_are_counted_by_stable_reason(api, monkeypatch) -> None:
    from app.observability.metrics import INGESTION_REJECTIONS

    client, _, _ = api
    monkeypatch.setenv("INGESTION_MAX_ROWS", "5")
    before = INGESTION_REJECTIONS.labels("workbook_row_limit")._value.get()

    client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("grande.xlsx", _workbook_with_rows(20), XLSX_TYPE)},
    )

    after = INGESTION_REJECTIONS.labels("workbook_row_limit")._value.get()
    assert after == before + 1


@pytest.mark.parametrize("kind", ["xlsx", "csv"])
def test_successful_import_records_duration_rows_and_estimated_memory(
    api, kind
) -> None:
    from app.observability.metrics import (
        INGESTION_DURATION,
        INGESTION_ESTIMATED_MEMORY,
        INGESTION_MEMORY_BUDGET,
        INGESTION_ROWS,
    )

    client, _, _ = api
    processed = INGESTION_ROWS.labels("processed")
    duration = INGESTION_DURATION.labels("completed")
    rows_before = processed._value.get()
    count_before = sum(bucket.get() for bucket in duration._buckets)
    if kind == "xlsx":
        upload = ("ok.xlsx", _workbook_with_rows(7), XLSX_TYPE)
    else:
        lines = "".join(f"WO-{index:04d},open\n" for index in range(7))
        upload = ("ok.csv", f"workorder,status\n{lines}".encode(), "text/csv")

    response = client.post("/imports", data={"source": "N-FP"}, files={"file": upload})

    assert response.status_code == 201
    assert processed._value.get() == rows_before + 7
    assert sum(bucket.get() for bucket in duration._buckets) == count_before + 1
    if kind == "xlsx":
        assert INGESTION_ESTIMATED_MEMORY._value.get() > 0
        assert INGESTION_MEMORY_BUDGET._value.get() > 0
    else:
        assert INGESTION_ESTIMATED_MEMORY._value.get() == 0
        assert INGESTION_MEMORY_BUDGET._value.get() == 0


def test_upload_fails_closed_when_no_sheet_is_authorized(api, monkeypatch) -> None:
    client, _, storage = api
    monkeypatch.delenv("INGESTION_ALLOWED_SHEETS", raising=False)

    response = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("entrada.xlsx", xlsx_bytes(), XLSX_TYPE)},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "no_authorized_sheet"
    assert "INGESTION_ALLOWED_SHEETS" in error["details"]["guidance"]
    assert not [path for path in storage.glob("accepted/**/*") if path.is_file()]


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        ("ingestion_time_limit", 422),
        ("unreadable_workbook", 422),
        ("workbook_memory_limit", 413),
    ],
)
def test_structured_rejection_from_the_reader_reaches_the_response(
    api, monkeypatch, code, status_code
) -> None:
    from app.ingestion_budget import IngestionLimitError

    client, repository, storage = api

    class RejectingImporter:
        def read(self, path, extension, source):
            raise IngestionLimitError(code, limit=1, observed=2, sheet="Dados")

    monkeypatch.setitem(pipeline.IMPORTERS, "N-FP", RejectingImporter())

    response = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("entrada.xlsx", xlsx_bytes(), XLSX_TYPE)},
    )

    assert response.status_code == status_code
    error = response.json()["error"]
    assert error["code"] == code
    assert error["details"]["limit"] == 1
    assert error["details"]["observed"] == 2
    assert error["details"]["guidance"]
    execution_id = error["details"]["execution_id"]
    assert repository.get(execution_id)["failure_reason"] == code
    assert not [path for path in storage.glob("accepted/**/*") if path.is_file()]


def test_files_accepted_individually_are_budgeted_together(api, monkeypatch) -> None:
    from app.ingestion_budget import CELL_COST_BYTES, ROW_COST_BYTES

    client, repository, storage = api
    # Each file holds 30 normalized records; two of them exceed the limit.
    one_file = 30 * ROW_COST_BYTES + 60 * CELL_COST_BYTES
    monkeypatch.setenv("INGESTION_MAX_MEMORY_BYTES", str(one_file + 1))
    single = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("a.xlsx", _workbook_with_rows(30), XLSX_TYPE)},
    )
    assert single.status_code == 201

    together = client.post(
        "/imports",
        data={"source": ["N-FP", "OWM"]},
        files=[
            ("file", ("b.xlsx", _workbook_with_rows(31), XLSX_TYPE)),
            ("file", ("c.xlsx", _workbook_with_rows(32), XLSX_TYPE)),
        ],
    )

    assert together.status_code == 413
    error = together.json()["error"]
    assert error["code"] == "workbook_memory_limit"
    assert error["details"]["observed"] > error["details"]["limit"]
    assert repository.get(error["details"]["execution_id"])["status"] == "failed"
    assert not [
        path
        for path in storage.glob(f"accepted/**/{error['details']['execution_id']}/*")
        if path.is_file()
    ]


@pytest.mark.parametrize("order", [("N-FP", "OWM"), ("OWM", "N-FP")])
def test_aggregate_budget_uses_the_most_restrictive_source_in_any_order(
    api, monkeypatch, order
) -> None:
    from app.ingestion_budget import CELL_COST_BYTES, ROW_COST_BYTES

    client, repository, storage = api
    one_file = 30 * ROW_COST_BYTES + 60 * CELL_COST_BYTES
    # N-FP keeps the 1 GiB default; OWM only fits one 30-record file.
    monkeypatch.setenv("INGESTION_MAX_MEMORY_BYTES_OWM", str(one_file + one_file // 10))

    alone = client.post(
        "/imports",
        data={"source": "OWM"},
        files={"file": ("sozinho.xlsx", _workbook_with_rows(30), XLSX_TYPE)},
    )
    assert alone.status_code == 201

    together = client.post(
        "/imports",
        data={"source": list(order)},
        files=[
            ("file", ("um.xlsx", _workbook_with_rows(30), XLSX_TYPE)),
            ("file", ("dois.xlsx", _workbook_with_rows(31), XLSX_TYPE)),
        ],
    )

    assert together.status_code == 413
    error = together.json()["error"]
    assert error["code"] == "workbook_memory_limit"
    assert error["details"]["limit"] == one_file + one_file // 10


def test_request_is_rejected_before_processing_when_it_has_too_many_files(
    api, monkeypatch
) -> None:
    from app.observability.metrics import (
        INGESTION_ESTIMATED_MEMORY,
        INGESTION_MEMORY_BUDGET,
    )

    client, repository, storage = api
    monkeypatch.setenv("INGESTION_MAX_FILES", "2")
    INGESTION_ESTIMATED_MEMORY.set(123)
    INGESTION_MEMORY_BUDGET.set(456)
    files = [
        ("file", (f"f{index}.xlsx", _workbook_with_rows(3), XLSX_TYPE))
        for index in range(3)
    ]
    rejected_before = _outcome_count("rejected")

    response = client.post(
        "/imports", data={"source": ["N-FP", "OWM", "TMS"]}, files=files
    )

    assert response.status_code == 413
    error = response.json()["error"]
    assert error["code"] == "ingestion_file_limit"
    assert error["details"]["limit"] == 2
    assert error["details"]["observed"] == 3
    assert error["details"]["guidance"]
    assert _outcome_count("rejected") == rejected_before + 1
    assert INGESTION_ESTIMATED_MEMORY._value.get() == 0
    assert INGESTION_MEMORY_BUDGET._value.get() == 0
    assert repository.executions == {}
    assert not [path for path in storage.glob("**/*") if path.is_file()]

    accepted = client.post(
        "/imports",
        data={"source": ["N-FP", "OWM"]},
        files=files[:2],
    )
    assert accepted.status_code == 201


def _outcome_count(outcome: str) -> int:
    from app.observability.metrics import INGESTION_DURATION

    return sum(bucket.get() for bucket in INGESTION_DURATION.labels(outcome)._buckets)


def test_admission_rejection_records_duration_and_clears_memory_pair(
    api, monkeypatch
) -> None:
    from app.observability.metrics import (
        INGESTION_ESTIMATED_MEMORY,
        INGESTION_MEMORY_BUDGET,
    )

    client, _, _ = api
    monkeypatch.setenv("INGESTION_MAX_ROWS", "5")
    INGESTION_ESTIMATED_MEMORY.set(123)
    INGESTION_MEMORY_BUDGET.set(456)
    before = _outcome_count("rejected")

    response = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("grande.xlsx", _workbook_with_rows(20), XLSX_TYPE)},
    )

    assert response.status_code == 413
    assert _outcome_count("rejected") == before + 1
    assert INGESTION_ESTIMATED_MEMORY._value.get() == 0
    assert INGESTION_MEMORY_BUDGET._value.get() == 0


def test_consolidation_timeout_is_a_structured_rejection_with_metrics(
    api, monkeypatch
) -> None:
    from app import ingestion_budget, pipeline
    from app.observability.metrics import INGESTION_REJECTIONS

    client, repository, storage = api
    real_process = pipeline.process_normalized_records

    def expire_then_process(records, **kwargs):
        monkeypatch.setattr(ingestion_budget.time, "monotonic", lambda: 10**9)
        return real_process(records, **kwargs)

    monkeypatch.setattr(pipeline, "process_normalized_records", expire_then_process)
    before_count = _outcome_count("rejected")
    before_reason = INGESTION_REJECTIONS.labels("ingestion_time_limit")._value.get()

    response = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("lento.xlsx", _workbook_with_rows(20), XLSX_TYPE)},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ingestion_time_limit"
    assert error["details"]["guidance"]
    assert repository.get(error["details"]["execution_id"])["status"] == "failed"
    assert not [path for path in storage.glob("accepted/**/*") if path.is_file()]
    assert _outcome_count("rejected") == before_count + 1
    after_reason = INGESTION_REJECTIONS.labels("ingestion_time_limit")._value.get()
    assert after_reason == before_reason + 1


def test_unexpected_pipeline_failure_counts_as_failed_once(api, monkeypatch) -> None:
    from app import pipeline

    client, _, _ = api

    def broken(*args, **kwargs):
        raise RuntimeError("falha inesperada")

    monkeypatch.setattr(pipeline, "process_normalized_records", broken)
    before = _outcome_count("failed")

    response = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("quebra.xlsx", _workbook_with_rows(5), XLSX_TYPE)},
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "pipeline_error"
    assert _outcome_count("failed") == before + 1


def test_unreadable_csv_reaching_the_value_error_path_counts_as_rejected(
    api, monkeypatch
) -> None:
    client, _, storage = api

    class BrokenImporter:
        def read(self, path, extension, source):
            raise ValueError("arquivo CSV inválido")

    monkeypatch.setitem(pipeline.IMPORTERS, "N-FP", BrokenImporter())
    before = _outcome_count("rejected")

    response = client.post(
        "/imports",
        data={"source": "N-FP"},
        files={"file": ("entrada.csv", b"workorder,status\nWO-1,open\n", "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_file"
    assert _outcome_count("rejected") == before + 1
    assert not [path for path in storage.glob("accepted/**/*") if path.is_file()]


def _wo_status_bytes(edge: bool = False) -> bytes:
    import sys

    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.generate_wo_status_fixture import build_workbook

    return build_workbook(edge=edge)[0]


def test_total_decision_upload_and_policy_preserve_logical_source(api):
    from scripts.generate_total_decision_fixture import (
        SENSITIVE_SENTINEL,
        build_workbook,
    )

    client, repository, _ = api
    policy = next(
        p
        for p in client.get("/imports/policy").json()["policies"]
        if p["source"] == "Total Decision"
    )
    assert policy["allowed_extensions"] == ["xlsx"]
    content = build_workbook()
    response = client.post(
        "/imports",
        data={"source": "Total Decision"},
        files={"file": ("synthetic.xlsx", content, XLSX_TYPE)},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source"] == "Total Decision"
    assert body["status"] == "completed"
    execution_id = body["execution_id"]
    normalized = client.get(f"/imports/{execution_id}/normalized-data")
    assert normalized.status_code == 200
    assert SENSITIVE_SENTINEL not in normalized.text
    assert repository.normalized_records[execution_id][0]["source"] == "GMES/OQC"
    duplicate = client.post(
        "/imports",
        data={"source": "Total Decision"},
        files={"file": ("synthetic.xlsx", content, XLSX_TYPE)},
    )
    assert duplicate.status_code == 409


def test_total_decision_upload_is_always_xlsx_only(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setenv("UPLOAD_ALLOWED_EXTENSIONS", "csv,json,xlsx")
    response = client.post(
        "/imports",
        data={"source": "Total Decision"},
        files={"file": ("synthetic.csv", b"workorder_number\nSYN-1\n", "text/csv")},
    )
    assert response.status_code == 415


@pytest.mark.parametrize("allowlist", ["*", None])
def test_wo_status_upload_routes_each_sheet_to_its_logical_source(
    api, monkeypatch, allowlist
) -> None:
    client, repository, _ = api
    if allowlist is None:
        # No environment list: the adapter's versioned contract applies.
        monkeypatch.delenv("INGESTION_ALLOWED_SHEETS", raising=False)

    response = client.post(
        "/imports",
        data={"source": "WO Status"},
        files={"file": ("wo-status.xlsx", _wo_status_bytes(), XLSX_TYPE)},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "WO Status"
    assert body["status"] == "completed_with_errors"
    records = repository.normalized_records[body["execution_id"]]
    assert {record["source"] for record in records} == {"N-FP", "OWM", "TMS"}
    assert {record["sheet"] for record in records} == {
        "NFP",
        "OWM SN",
        "CTNR STATUS",
    }
    assert {record["source_file_id"] for record in records} == {
        repository.files[body["execution_id"]][0]["id"]
    }


def test_wo_status_same_workbook_is_not_processed_twice(api) -> None:
    client, _, _ = api
    content = _wo_status_bytes()
    first = client.post(
        "/imports",
        data={"source": "WO Status"},
        files={"file": ("wo-status.xlsx", content, XLSX_TYPE)},
    )
    assert first.status_code == 201

    second = client.post(
        "/imports",
        data={"source": "WO Status"},
        files={"file": ("wo-status.xlsx", content, XLSX_TYPE)},
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_file"


def test_wo_status_requires_an_xlsx_workbook(api) -> None:
    client, _, _ = api

    response = client.post(
        "/imports",
        data={"source": "WO Status"},
        files={"file": ("wo-status.csv", b"workorder\nWO-1\n", "text/csv")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_extension"


def test_upload_policy_lists_the_composite_source_as_xlsx_only(api) -> None:
    client, _, _ = api

    response = client.get("/imports/policy")

    policy = next(p for p in response.json()["policies"] if p["source"] == "WO Status")
    assert policy["allowed_extensions"] == ["xlsx"]


def test_composite_policy_and_upload_ignore_the_global_csv_json_setting(
    api, monkeypatch
) -> None:
    client, _, _ = api
    monkeypatch.setenv("UPLOAD_ALLOWED_EXTENSIONS", "csv,json,xlsx")

    policy = next(
        p
        for p in client.get("/imports/policy").json()["policies"]
        if p["source"] == "WO Status"
    )
    response = client.post(
        "/imports",
        data={"source": "WO Status"},
        files={"file": ("wo.csv", b"workorder\nWO-1\n", "text/csv")},
    )

    assert policy["allowed_extensions"] == ["xlsx"]
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_extension"
