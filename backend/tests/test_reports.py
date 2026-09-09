from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.reports import get_report_repository

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)
ORG_ID = UUID("44444444-4444-4444-8444-444444444444")
USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class MemoryReportRepository:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def generate(self, payload, actor, report_id=None):
        versions = [row for row in self.items if row["report_id"] == report_id]
        report_id = report_id or uuid4()
        row = {
            "report_id": report_id,
            "version_id": uuid4(),
            "version": len(versions) + 1,
            "report_type": payload.report_type,
            "state": "succeeded",
            "completeness": "complete",
            "organization_id": payload.organization_id,
            "execution_id": payload.execution_id,
            "requested_by_user_id": actor.user_id,
            "reference_at": payload.reference_at,
            "filters": payload.filters.model_dump(mode="json", exclude_none=True),
            "schema_version": "1.0.0",
            "created_at": NOW,
            "completed_at": NOW,
            "failure_code": None,
            "failure_message": None,
            "data": {
                "kind": payload.report_type,
                "workorders": [{"planned_quantity": None, "produced_quantity": 0}],
            },
        }
        self.items.append(row)
        return deepcopy(row)

    def list_reports(
        self, organization_ids, report_type, state, execution_id, page, page_size
    ):
        rows = self._visible(organization_ids)
        latest = {}
        for row in rows:
            latest[row["report_id"]] = row
        rows = list(latest.values())
        if report_type:
            rows = [row for row in rows if row["report_type"] == report_type]
        if state:
            rows = [row for row in rows if row["state"] == state]
        if execution_id:
            rows = [row for row in rows if row["execution_id"] == execution_id]
        return deepcopy(rows[(page - 1) * page_size : page * page_size]), len(rows)

    def list_versions(self, report_id, organization_ids, page, page_size):
        rows = [
            row
            for row in self._visible(organization_ids)
            if row["report_id"] == report_id
        ]
        rows.sort(key=lambda row: row["version"], reverse=True)
        return deepcopy(rows[(page - 1) * page_size : page * page_size]), len(rows)

    def get_version(self, report_id, version, organization_ids, audit_actor=None):
        rows = [
            row
            for row in self._visible(organization_ids)
            if row["report_id"] == report_id
        ]
        if version is not None:
            rows = [row for row in rows if row["version"] == version]
        return deepcopy(max(rows, key=lambda row: row["version"])) if rows else None

    def _visible(self, organization_ids):
        if organization_ids is None:
            return self.items
        return [row for row in self.items if row["organization_id"] in organization_ids]


def test_generate_version_history_and_preserve_missing_quantity() -> None:
    repository = MemoryReportRepository()
    app.dependency_overrides[get_report_repository] = lambda: repository
    payload = {
        "report_type": "workorder_consolidated",
        "execution_id": "exec-1",
        "organization_id": str(ORG_ID),
        "reference_at": NOW.isoformat(),
        "filters": {"date_from": "2026-09-01", "state": "consolidated"},
    }
    try:
        with TestClient(app) as client:
            first = client.post("/reports", json=payload)
            assert first.status_code == 201
            report_id = first.json()["report_id"]
            assert first.json()["data"]["workorders"][0] == {
                "planned_quantity": None,
                "produced_quantity": 0,
            }

            second = client.post(f"/reports/{report_id}/versions", json=payload)
            assert second.status_code == 201
            assert second.json()["version"] == 2

            history = client.get(f"/reports/{report_id}/versions")
            assert history.status_code == 200
            assert [item["version"] for item in history.json()["items"]] == [2, 1]
            assert client.get(f"/reports/{report_id}/versions/1").json()["version"] == 1
            assert client.get("/reports").json()["pagination"]["total"] == 1
    finally:
        app.dependency_overrides.pop(get_report_repository, None)


def test_report_contract_rejects_invalid_period() -> None:
    repository = MemoryReportRepository()
    app.dependency_overrides[get_report_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.post(
                "/reports",
                json={
                    "report_type": "oqc_summary",
                    "execution_id": "exec-1",
                    "organization_id": str(ORG_ID),
                    "reference_at": NOW.isoformat(),
                    "filters": {
                        "date_from": "2026-09-08",
                        "date_to": "2026-09-01",
                    },
                },
            )
        assert response.status_code == 422
        assert repository.items == []
    finally:
        app.dependency_overrides.pop(get_report_repository, None)
