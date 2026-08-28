from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.queries import ReprocessingConflict, get_query_repository

NOW = datetime(2026, 8, 27, 12, tzinfo=UTC)


class MemoryQueryRepository:
    def __init__(self) -> None:
        self.executions = {
            "exec-1": {
                "execution_id": "exec-1",
                "status": "completed",
                "source": "OWM",
                "attempt": 1,
                "reprocessed_from_execution_id": None,
                "actor_type": "technical",
                "actor_identifier": "synthetic-fixture",
                "started_at": NOW,
                "finished_at": NOW,
                "failure_reason": None,
            }
        }
        self.workorder = {
            "execution_id": "exec-1",
            "workorder_number": "WO-SYN-001",
            "organization_code": "ORG-001",
            "processing_status": "consolidated",
            "planned_quantity": 10,
            "produced_quantity": 8,
            "received_quantity": 8,
            "released_quantity": 6,
            "pending_quantity": 4,
            "retained_quantity": 1,
            "partially_released": True,
            "lots": ["LOT-SYN-001"],
            "serials": ["SER-SYN-001"],
            "updated_at": NOW,
        }
        self.lot = {
            "execution_id": "exec-1",
            "workorder_number": "WO-SYN-001",
            "lot_number": "LOT-SYN-001",
            "serials": ["SER-SYN-001"],
            "updated_at": NOW,
        }
        self.serial = {
            "execution_id": "exec-1",
            "workorder_number": "WO-SYN-001",
            "lot_number": "LOT-SYN-001",
            "serial_number": "SER-SYN-001",
            "container_number": "CONT-SYN-001",
            "updated_at": NOW,
        }
        self.pending = [
            {
                "id": 1,
                "execution_id": "exec-1",
                "workorder_number": "WO-SYN-001",
                "lot_number": "LOT-SYN-001",
                "serial_number": "SER-SYN-001",
                "category": "long_term_hold",
                "reason": "Synthetic inspection",
                "status": "open",
                "priority_score": 90,
                "priority": "critical",
                "responsible_area": "Qualidade",
                "created_at": datetime(2026, 7, 1, tzinfo=UTC),
                "updated_at": NOW,
            },
            {
                "id": 2,
                "execution_id": "exec-1",
                "workorder_number": "WO-SYN-001",
                "lot_number": None,
                "serial_number": None,
                "category": "oqc_pending",
                "reason": "Awaiting inspection",
                "status": "open",
                "priority_score": 40,
                "priority": "normal",
                "responsible_area": "Qualidade",
                "created_at": datetime(2026, 8, 20, tzinfo=UTC),
                "updated_at": NOW,
            },
            {
                "id": 3,
                "execution_id": "exec-1",
                "workorder_number": "WO-SYN-001",
                "lot_number": None,
                "serial_number": None,
                "category": "oqc_hold",
                "reason": "Resolved",
                "status": "resolved",
                "priority_score": 80,
                "priority": "high",
                "responsible_area": "Qualidade",
                "created_at": datetime(2026, 6, 1, tzinfo=UTC),
                "updated_at": NOW,
            },
        ]
        self.history = [
            {
                "id": 1,
                "execution_id": "exec-1",
                "entity_type": "workorder",
                "entity_id": "WO-SYN-001",
                "event_type": "consolidated",
                "payload": {"status": "partial"},
                "occurred_at": datetime(2026, 8, 26, tzinfo=UTC),
            },
            {
                "id": 2,
                "execution_id": "exec-1",
                "entity_type": "serial",
                "entity_id": "SER-SYN-001",
                "event_type": "classified",
                "payload": {"rule_id": "long_term_hold"},
                "occurred_at": NOW,
            },
        ]

    def get_execution(self, execution_id: str) -> dict | None:
        return deepcopy(self.executions.get(execution_id))

    def get_workorder(
        self, workorder_number: str, execution_id: str | None = None
    ) -> dict | None:
        if workorder_number != self.workorder["workorder_number"]:
            return None
        if execution_id and execution_id != self.workorder["execution_id"]:
            return None
        return deepcopy(self.workorder)

    def get_lot(
        self, lot_number: str, workorder_number: str | None = None
    ) -> dict | None:
        if lot_number != self.lot["lot_number"]:
            return None
        if workorder_number and workorder_number != self.lot["workorder_number"]:
            return None
        return deepcopy(self.lot)

    def get_serial(self, serial_number: str) -> dict | None:
        return deepcopy(self.serial) if serial_number == "SER-SYN-001" else None

    def list_pending(
        self,
        *,
        status_filter: str | None,
        category: str | None,
        workorder_number: str | None,
        execution_id: str | None,
        page: int,
        page_size: int,
        sort: str,
    ) -> tuple[list[dict], int]:
        items = [
            item
            for item in self.pending
            if (status_filter is None or item["status"] == status_filter)
            and (category is None or item["category"] == category)
            and (
                workorder_number is None
                or item["workorder_number"] == workorder_number
            )
            and (execution_id is None or item["execution_id"] == execution_id)
        ]
        reverse = sort == "newest"
        key = (
            (lambda item: (item["category"], item["created_at"], item["id"]))
            if sort == "category"
            else (lambda item: (item["created_at"], item["id"]))
        )
        items.sort(key=key, reverse=reverse)
        total = len(items)
        offset = (page - 1) * page_size
        return deepcopy(items[offset : offset + page_size]), total

    def get_pending(self, pending_id: int) -> dict | None:
        return next(
            (deepcopy(item) for item in self.pending if item["id"] == pending_id),
            None,
        )

    def list_history(
        self,
        *,
        execution_id: str | None,
        entity_type: str | None,
        entity_id: str | None,
        event_type: str | None,
        page: int,
        page_size: int,
        sort: str,
    ) -> tuple[list[dict], int]:
        items = [
            item
            for item in self.history
            if (execution_id is None or item["execution_id"] == execution_id)
            and (entity_type is None or item["entity_type"] == entity_type)
            and (entity_id is None or item["entity_id"] == entity_id)
            and (event_type is None or item["event_type"] == event_type)
        ]
        items.sort(key=lambda item: item["occurred_at"], reverse=sort == "newest")
        total = len(items)
        offset = (page - 1) * page_size
        return deepcopy(items[offset : offset + page_size]), total

    def get_consolidated(self, workorder_number: str) -> dict | None:
        if workorder_number != "WO-SYN-001":
            return None
        return {
            "workorder": deepcopy(self.workorder),
            "holds": [
                {
                    "id": 1,
                    "status": "active",
                    "reason": "Synthetic inspection",
                    "post_release": True,
                    "serial_number": "SER-SYN-001",
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            ],
            "oqc_decisions": [
                {
                    "id": 1,
                    "decision_state": "partially_approved",
                    "lot_number": "LOT-SYN-001",
                    "serial_number": "SER-SYN-001",
                    "reason": None,
                    "decided_at": NOW,
                    "updated_at": NOW,
                }
            ],
            "pending_items": deepcopy(self.pending),
        }

    def request_reprocessing(
        self, execution_id: str, new_execution_id: str, technical_origin: str
    ) -> dict | None:
        original = self.executions.get(execution_id)
        if original is None:
            return None
        if original["status"] in {"pending", "running"}:
            raise ReprocessingConflict
        root = original["reprocessed_from_execution_id"] or execution_id
        attempt = max(
            (
                item["attempt"]
                for item in self.executions.values()
                if item["execution_id"] == root
                or item["reprocessed_from_execution_id"] == root
            ),
            default=0,
        ) + 1
        self.executions[new_execution_id] = {
            **deepcopy(original),
            "execution_id": new_execution_id,
            "status": "pending",
            "attempt": attempt,
            "reprocessed_from_execution_id": root,
            "actor_identifier": technical_origin,
            "finished_at": None,
        }
        self.history.append(
            {
                "id": len(self.history) + 1,
                "execution_id": new_execution_id,
                "entity_type": "execution",
                "entity_id": new_execution_id,
                "event_type": "reprocessing_requested",
                "payload": {
                    "previous_execution_id": execution_id,
                    "root_execution_id": root,
                    "attempt": attempt,
                },
                "occurred_at": NOW,
            }
        )
        return {
            "execution_id": new_execution_id,
            "status": "pending",
            "attempt": attempt,
            "reprocessed_from_execution_id": root,
            "previous_execution_id": execution_id,
        }

    def indicators(self) -> dict:
        return {
            "executions": {"completed": 1},
            "workorders": {"total": 1, "partially_released": 1},
            "pending_items": {"open": 2, "resolved": 1},
            "quantities": {
                "planned": 10,
                "produced": 8,
                "received": 8,
                "released": 6,
            },
        }


@pytest.fixture
def api():
    repository = MemoryQueryRepository()
    app.dependency_overrides[get_query_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, repository
    app.dependency_overrides.clear()


def test_consults_execution_workorder_lot_and_serial(api) -> None:
    client, _ = api

    assert client.get("/executions/exec-1").json()["attempt"] == 1
    workorder = client.get("/workorders/WO-SYN-001").json()
    assert workorder["partially_released"] is True
    assert workorder["lots"] == ["LOT-SYN-001"]
    assert client.get("/lots/LOT-SYN-001").json()["serials"] == ["SER-SYN-001"]
    assert (
        client.get("/serials/SER-SYN-001").json()["container_number"]
        == "CONT-SYN-001"
    )


def test_lists_active_pending_items_with_filters_pagination_and_sort(api) -> None:
    client, _ = api

    response = client.get("/pending-items?page=1&page_size=1&sort=oldest")
    body = response.json()

    assert response.status_code == 200
    assert body["items"][0]["id"] == 1
    assert body["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total": 2,
        "pages": 2,
    }
    filtered = client.get("/pending-items?category=oqc_pending").json()
    assert [item["id"] for item in filtered["items"]] == [2]
    by_execution = client.get("/pending-items?execution_id=missing").json()
    assert by_execution["pagination"]["total"] == 0


def test_consults_pending_detail_history_and_consolidated_result(api) -> None:
    client, _ = api

    assert client.get("/pending-items/1").json()["priority"] == "critical"
    history = client.get(
        "/history?entity_type=serial&entity_id=SER-SYN-001&page_size=1"
    ).json()
    assert history["pagination"]["total"] == 1
    assert history["items"][0]["event_type"] == "classified"
    consolidated = client.get(
        "/workorders/WO-SYN-001/consolidated-result"
    ).json()
    assert consolidated["workorder"]["released_quantity"] == 6
    assert consolidated["holds"][0]["post_release"] is True


def test_reprocessing_preserves_original_execution(api) -> None:
    client, repository = api
    before = deepcopy(repository.executions["exec-1"])

    response = client.post(
        "/executions/exec-1/reprocess",
        json={"technical_origin": "api-test"},
    )
    body = response.json()

    assert response.status_code == 202
    assert body["attempt"] == 2
    assert body["reprocessed_from_execution_id"] == "exec-1"
    assert body["execution_id"] != "exec-1"
    assert repository.executions["exec-1"] == before
    assert repository.executions[body["execution_id"]]["status"] == "pending"
    assert repository.history[-1]["event_type"] == "reprocessing_requested"
    assert repository.history[-1]["payload"]["previous_execution_id"] == "exec-1"


def test_rejects_reprocessing_while_execution_is_active(api) -> None:
    client, repository = api
    repository.executions["exec-1"]["status"] = "running"

    response = client.post(
        "/executions/exec-1/reprocess",
        json={"technical_origin": "api-test"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "execution_still_active"
    assert len(repository.executions) == 1


def test_rejects_blank_reprocessing_origin(api) -> None:
    client, repository = api

    response = client.post(
        "/executions/exec-1/reprocess",
        json={"technical_origin": "   "},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
    assert len(repository.executions) == 1


def test_returns_basic_indicators(api) -> None:
    client, _ = api

    body = client.get("/indicators").json()

    assert body["workorders"]["partially_released"] == 1
    assert body["pending_items"]["open"] == 2
    assert body["quantities"]["released"] == 6


@pytest.mark.parametrize(
    "path",
    [
        "/executions/missing",
        "/workorders/missing",
        "/lots/missing",
        "/serials/missing",
        "/pending-items/999",
        "/workorders/missing/consolidated-result",
    ],
)
def test_returns_standard_not_found_error(api, path: str) -> None:
    client, _ = api

    response = client.get(path)

    assert response.status_code == 404
    assert set(response.json()) == {"error"}
    assert set(response.json()["error"]) == {"code", "message", "details"}


def test_returns_standard_validation_error(api) -> None:
    client, _ = api

    response = client.get("/pending-items?page=0&page_size=500")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
    assert len(response.json()["error"]["details"]["issues"]) == 2


def test_returns_standard_error_for_unknown_route(api) -> None:
    client, _ = api

    response = client.get("/route-that-does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "not_found",
        "message": "Not Found",
        "details": {},
    }


def test_hides_internal_error_details(api) -> None:
    _, repository = api

    def fail_repository():
        raise RuntimeError("CONFIDENTIAL-INTERNAL-DETAIL")

    app.dependency_overrides[get_query_repository] = fail_repository
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/indicators")
    finally:
        app.dependency_overrides[get_query_repository] = lambda: repository

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "CONFIDENTIAL" not in response.text


def test_openapi_documents_all_public_contracts(api) -> None:
    client, _ = api
    schema = client.get("/openapi.json").json()
    expected = {
        "/imports",
        "/imports/{execution_id}",
        "/imports/{execution_id}/validation-report",
        "/executions/{execution_id}",
        "/workorders/{workorder_number}",
        "/lots/{lot_number}",
        "/serials/{serial_number}",
        "/pending-items",
        "/pending-items/{pending_id}",
        "/history",
        "/workorders/{workorder_number}/consolidated-result",
        "/executions/{execution_id}/reprocess",
        "/indicators",
    }

    assert expected <= schema["paths"].keys()
    assert "ErrorResponse" in schema["components"]["schemas"]
    assert "HoldResponse" in schema["components"]["schemas"]
    assert "OqcDecisionResponse" in schema["components"]["schemas"]
