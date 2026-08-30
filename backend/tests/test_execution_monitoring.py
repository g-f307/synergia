from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.execution_monitoring import get_monitoring_repository
from app.main import app

NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


class MemoryMonitoringRepository:
    def execution_exists(self, execution_id: str) -> bool:
        return execution_id == "exec-1"

    def divergences(self, execution_id: str, **filters):
        items = [
            {
                "id": 2,
                "source": "OWM",
                "severity": "warning",
                "code": "quantity_mismatch",
                "scope": "record",
                "workorder_number": "WO-1",
                "sheet_name": "Data",
                "row_number": 3,
                "column_name": "quantity",
                "reason": "Divergência sintética",
                "details": {"expected": 10, "observed": 9},
                "occurred_at": NOW,
            }
        ]
        if filters["severity"] and filters["severity"] != "warning":
            return [], 0
        return items, len(items)

    def classifications(self, execution_id: str):
        return [
            {
                "classification_id": "class-1",
                "workorder_number": "WO-1",
                "lot_number": None,
                "serial_number": None,
                "rule_id": "oqc_pending",
                "rule_catalog_version": "1.0.0",
                "state": "active",
                "entity_type": "workorder",
                "entity_id": "WO-1",
                "justification": "Aguardando OQC",
                "reason": None,
                "data_quality": "complete",
                "priority": "high",
                "priority_score": 80,
                "responsible_area": "Qualidade",
                "classified_at": NOW,
                "evidence": {"source": "synthetic"},
            }
        ]

    def pending(self, execution_id: str):
        return [
            {
                "id": 1,
                "workorder_number": "WO-1",
                "lot_number": None,
                "serial_number": None,
                "category": "oqc_pending",
                "reason": "Aguardando OQC",
                "status": "open",
                "rule_id": "oqc_pending",
                "rule_catalog_version": "1.0.0",
                "priority": "high",
                "priority_score": 80,
                "responsible_area": "Qualidade",
                "evidence": {},
                "created_at": NOW,
                "updated_at": NOW,
            }
        ]

    def evidences(self, execution_id: str):
        return [
            {
                "evidence_id": 7,
                "safe_name": "evidence-7.csv",
                "media_type": "text/csv",
                "size_bytes": 42,
                "sha256": "a" * 64,
                "available": True,
            }
        ]

    def evidence_file(self, execution_id: str, evidence_id: int):
        if evidence_id == 8:
            return {
                "id": None,
                "storage_key": None,
                "extension": "csv",
                "media_type": "text/csv",
                "decision": "rejected",
            }
        return None


@pytest.fixture
def api():
    app.dependency_overrides[get_monitoring_repository] = MemoryMonitoringRepository
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_lists_monitoring_resources_with_deterministic_contract(api) -> None:
    page = api.get("/executions/exec-1/divergences?page=1&page_size=20").json()
    assert page["pagination"] == {"page": 1, "page_size": 20, "total": 1, "pages": 1}
    assert page["items"][0]["workorder_number"] == "WO-1"
    assert (
        api.get("/executions/exec-1/classifications").json()[0]["rule_id"]
        == "oqc_pending"
    )
    assert api.get("/executions/exec-1/pending-items").json()[0]["status"] == "open"
    evidence = api.get("/executions/exec-1/evidences").json()[0]
    assert evidence["safe_name"] == "evidence-7.csv"
    assert "storage_key" not in evidence


def test_standardizes_not_found_period_and_quarantine_errors(api) -> None:
    missing = api.get("/executions/missing/divergences")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "execution_not_found"
    invalid = api.get(
        "/executions/exec-1/divergences?date_from=2026-08-31T00:00:00Z&date_to=2026-08-30T00:00:00Z"
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_period"
    blocked = api.get("/executions/exec-1/evidences/8/download")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "evidence_not_allowed"
    assert "/tmp/" not in blocked.text
