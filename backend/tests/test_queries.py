from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.authorization import ActorContext, get_actor_context
from app.execution import reprocessing_fingerprint
from app.main import app
from app.queries import ReprocessingConflict, get_query_repository

NOW = datetime(2026, 8, 27, 12, tzinfo=UTC)
ORGANIZATION_ID = UUID("44444444-4444-4444-8444-444444444444")


class MemoryQueryRepository:
    def __init__(self) -> None:
        self.reprocessing_requests: dict[str, dict] = {}
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
                "pipeline_version": "1.0.0",
                "rule_catalog_version": "1.0.0",
                "state_version": 5,
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

    def search_operational(
        self,
        *,
        entity_type,
        query,
        page,
        page_size,
        sort,
        organization_ids=None,
    ):
        self.search_organization_ids = organization_ids
        records = {
            "workorder": [
                {
                    "entity_type": "workorder",
                    "identifier": self.workorder["workorder_number"],
                    "execution_id": self.workorder["execution_id"],
                    "workorder_number": self.workorder["workorder_number"],
                    "lot_number": None,
                    "serial_number": None,
                    "organization_code": self.workorder["organization_code"],
                    "processing_status": self.workorder["processing_status"],
                    "updated_at": self.workorder["updated_at"],
                }
            ],
            "lot": [
                {
                    "entity_type": "lot",
                    "identifier": self.lot["lot_number"],
                    "execution_id": self.lot["execution_id"],
                    "workorder_number": self.lot["workorder_number"],
                    "lot_number": self.lot["lot_number"],
                    "serial_number": None,
                    "organization_code": self.workorder["organization_code"],
                    "processing_status": self.workorder["processing_status"],
                    "updated_at": self.lot["updated_at"],
                }
            ],
            "serial": [
                {
                    "entity_type": "serial",
                    "identifier": self.serial["serial_number"],
                    "execution_id": self.serial["execution_id"],
                    "workorder_number": self.serial["workorder_number"],
                    "lot_number": self.serial["lot_number"],
                    "serial_number": self.serial["serial_number"],
                    "organization_code": self.workorder["organization_code"],
                    "processing_status": self.workorder["processing_status"],
                    "updated_at": self.serial["updated_at"],
                }
            ],
        }[entity_type]
        records = [item for item in records if item["identifier"] == query]
        if organization_ids is not None and ORGANIZATION_ID not in organization_ids:
            records = []
        offset = (page - 1) * page_size
        return deepcopy(records[offset : offset + page_size]), len(records)

    def get_execution(self, execution_id: str) -> dict | None:
        return deepcopy(self.executions.get(execution_id))

    def get_workorder(
        self,
        workorder_number: str,
        execution_id: str | None = None,
        organization_ids=None,
    ) -> dict | None:
        if organization_ids is not None and ORGANIZATION_ID not in organization_ids:
            return None
        if workorder_number != self.workorder["workorder_number"]:
            return None
        if execution_id and execution_id != self.workorder["execution_id"]:
            return None
        return deepcopy(self.workorder)

    def get_lot(
        self,
        lot_number: str,
        workorder_number: str | None = None,
        organization_ids=None,
        execution_id: str | None = None,
    ) -> dict | None:
        if organization_ids is not None and ORGANIZATION_ID not in organization_ids:
            return None
        if lot_number != self.lot["lot_number"]:
            return None
        if workorder_number and workorder_number != self.lot["workorder_number"]:
            return None
        if execution_id and execution_id != self.lot["execution_id"]:
            return None
        return deepcopy(self.lot)

    def get_serial(
        self,
        serial_number: str,
        execution_id: str | None = None,
        organization_ids=None,
    ) -> dict | None:
        if organization_ids is not None and ORGANIZATION_ID not in organization_ids:
            return None
        if execution_id and execution_id != self.serial["execution_id"]:
            return None
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
        organization_ids=None,
    ) -> tuple[list[dict], int]:
        items = [
            item
            for item in self.pending
            if (status_filter is None or item["status"] == status_filter)
            and (category is None or item["category"] == category)
            and (
                workorder_number is None or item["workorder_number"] == workorder_number
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
        organization_ids=None,
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

    def get_consolidated(
        self,
        workorder_number: str,
        execution_id: str | None = None,
        organization_ids=None,
    ) -> dict | None:
        if organization_ids is not None and ORGANIZATION_ID not in organization_ids:
            return None
        if workorder_number != "WO-SYN-001":
            return None
        if execution_id and execution_id != self.workorder["execution_id"]:
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
        self,
        execution_id: str,
        new_execution_id: str,
        technical_origin: str,
        request_key: str,
        pipeline_version: str,
        rule_catalog_version: str,
        actor=None,
    ) -> dict | None:
        original = self.executions.get(execution_id)
        if original is None:
            return None
        if original["status"] not in {
            "completed",
            "completed_with_errors",
            "validation_failed",
            "failed",
        }:
            raise ReprocessingConflict
        fingerprint = reprocessing_fingerprint(
            execution_id, request_key, pipeline_version, rule_catalog_version
        )
        if fingerprint in self.reprocessing_requests:
            return {
                **deepcopy(self.reprocessing_requests[fingerprint]),
                "idempotent_replay": True,
            }
        root = original["reprocessed_from_execution_id"] or execution_id
        attempt = (
            max(
                (
                    item["attempt"]
                    for item in self.executions.values()
                    if item["execution_id"] == root
                    or item["reprocessed_from_execution_id"] == root
                ),
                default=0,
            )
            + 1
        )
        self.executions[new_execution_id] = {
            **deepcopy(original),
            "execution_id": new_execution_id,
            "status": "reprocessing",
            "attempt": attempt,
            "reprocessed_from_execution_id": root,
            "actor_identifier": technical_origin,
            "pipeline_version": pipeline_version,
            "rule_catalog_version": rule_catalog_version,
            "state_version": 0,
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
        result = {
            "execution_id": new_execution_id,
            "status": "reprocessing",
            "attempt": attempt,
            "reprocessed_from_execution_id": root,
            "previous_execution_id": execution_id,
            "pipeline_version": pipeline_version,
            "rule_catalog_version": rule_catalog_version,
            "idempotent_replay": False,
        }
        self.reprocessing_requests[fingerprint] = deepcopy(result)
        return result

    def indicators(self, organization_ids=None, date_from=None, date_to=None) -> dict:
        self.indicator_filters = (organization_ids, date_from, date_to)
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

    def indicator_related(
        self, entity, organization_ids, date_from, date_to, page, page_size
    ):
        self.related_filters = (
            entity,
            organization_ids,
            date_from,
            date_to,
            page,
            page_size,
        )
        return (
            [{"identifier": "exec-1", "status": "completed", "occurred_at": NOW}],
            1,
        )


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
        client.get("/serials/SER-SYN-001").json()["container_number"] == "CONT-SYN-001"
    )


@pytest.mark.parametrize("path", ["/lots/LOT-MISSING", "/serials/SER-MISSING"])
def test_lot_and_serial_details_distinguish_missing_resources(api, path: str) -> None:
    client, _ = api

    response = client.get(path)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


@pytest.mark.parametrize(
    ("entity_type", "identifier"),
    [
        ("workorder", "WO-SYN-001"),
        ("lot", "LOT-SYN-001"),
        ("serial", "SER-SYN-001"),
    ],
)
def test_searches_operational_identifiers_with_context(
    api, entity_type: str, identifier: str
) -> None:
    client, _ = api

    response = client.get(
        "/search",
        params={
            "type": entity_type,
            "query": identifier,
            "page": 1,
            "page_size": 1,
            "sort": "updated_desc",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["identifier"] == identifier
    assert body["items"][0]["execution_id"] == "exec-1"
    assert body["pagination"] == {"page": 1, "page_size": 1, "total": 1, "pages": 1}
    assert body["source"] == "synergia.operational"
    assert body["generated_at"]


def test_operational_search_preserves_text_and_distinguishes_not_found(api) -> None:
    client, _ = api

    missing = client.get("/search", params={"type": "workorder", "query": "000123-A"})

    assert missing.status_code == 200
    assert missing.json()["query"] == "000123-A"
    assert missing.json()["items"] == []
    assert missing.json()["pagination"]["total"] == 0


def test_operational_search_applies_actor_scope_and_keeps_detail_execution(api) -> None:
    client, repository = api

    response = client.get(
        "/search", params={"type": "workorder", "query": "WO-SYN-001"}
    )
    mismatched_detail = client.get(
        "/workorders/WO-SYN-001/consolidated-result",
        params={"execution_id": "different-execution"},
    )

    assert response.status_code == 200
    assert repository.search_organization_ids == frozenset(
        {UUID("44444444-4444-4444-8444-444444444444")}
    )
    assert mismatched_detail.status_code == 404


def test_operational_queries_block_records_outside_actor_scope(api) -> None:
    client, _ = api
    denied_organization = UUID("99999999-9999-4999-8999-999999999999")

    def restricted_actor() -> ActorContext:
        return ActorContext(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            session_id=UUID("22222222-2222-4222-8222-222222222222"),
            token_id=UUID("33333333-3333-4333-8333-333333333333"),
            permissions={"business.read": frozenset({denied_organization})},
            correlation_id=UUID("55555555-5555-4555-8555-555555555555"),
        )

    app.dependency_overrides[get_actor_context] = restricted_actor

    search = client.get("/search", params={"type": "workorder", "query": "WO-SYN-001"})
    assert search.status_code == 200
    assert search.json()["items"] == []
    for path in (
        "/workorders/WO-SYN-001",
        "/lots/LOT-SYN-001",
        "/serials/SER-SYN-001",
        "/workorders/WO-SYN-001/consolidated-result",
    ):
        assert client.get(path).status_code == 404


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
    consolidated = client.get("/workorders/WO-SYN-001/consolidated-result").json()
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
    assert repository.executions[body["execution_id"]]["status"] == "reprocessing"
    assert repository.history[-1]["event_type"] == "reprocessing_requested"
    assert repository.history[-1]["payload"]["previous_execution_id"] == "exec-1"


def test_rejects_reprocessing_while_execution_is_active(api) -> None:
    client, repository = api
    repository.executions["exec-1"]["status"] = "validating"

    response = client.post(
        "/executions/exec-1/reprocess",
        json={"technical_origin": "api-test"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "execution_still_active"
    assert len(repository.executions) == 1


def test_identical_reprocessing_request_is_idempotent(api) -> None:
    client, repository = api
    request = {
        "technical_origin": "api-test",
        "idempotency_key": "stable-request",
    }

    first = client.post("/executions/exec-1/reprocess", json=request)
    second = client.post("/executions/exec-1/reprocess", json=request)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["execution_id"] == first.json()["execution_id"]
    assert first.json()["idempotent_replay"] is False
    assert second.json()["idempotent_replay"] is True
    assert len(repository.executions) == 2


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
    assert body["source"] == "synergia.operational"
    assert body["generated_at"]
    assert body["filters"] == {
        "organization_id": None,
        "date_from": None,
        "date_to": None,
    }


def test_filters_indicators_by_authorized_organization_and_period(api) -> None:
    client, repository = api
    organization_id = client.get("/imports/policy").json()["organizations"][0]["id"]

    response = client.get(
        "/indicators",
        params={
            "organization_id": organization_id,
            "date_from": "2026-08-01",
            "date_to": "2026-08-31",
        },
    )

    assert response.status_code == 200
    assert response.json()["filters"] == {
        "organization_id": organization_id,
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
    }
    assert repository.indicator_filters[1:] == (
        date(2026, 8, 1),
        date(2026, 8, 31),
    )


def test_rejects_invalid_indicator_period(api) -> None:
    client, _ = api
    response = client.get("/indicators?date_from=2026-09-01&date_to=2026-08-01")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_period"


def test_rejects_indicator_organization_outside_scope(api) -> None:
    client, _ = api
    response = client.get(
        "/indicators?organization_id=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "organization_access_denied"


def test_lists_indicator_records_with_the_same_context(api) -> None:
    client, repository = api
    organization_id = client.get("/imports/policy").json()["organizations"][0]["id"]
    response = client.get(
        "/indicators/executions",
        params={
            "organization_id": organization_id,
            "date_from": "2026-08-01",
            "date_to": "2026-08-31",
        },
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["identifier"] == "exec-1"
    assert repository.related_filters[0] == "executions"
    assert repository.related_filters[2:4] == (date(2026, 8, 1), date(2026, 8, 31))


def test_indicator_records_require_the_entity_permission(api) -> None:
    client, _ = api
    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        user_id=UUID("10000000-0000-4000-8000-000000000001"),
        session_id=UUID("20000000-0000-4000-8000-000000000002"),
        token_id=UUID("30000000-0000-4000-8000-000000000003"),
        permissions={"dashboard.read": frozenset({None})},
        correlation_id=UUID("40000000-0000-4000-8000-000000000004"),
    )

    response = client.get("/indicators/workorders")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "access_denied"


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
        "/search",
    }

    assert expected <= schema["paths"].keys()
    assert "ErrorResponse" in schema["components"]["schemas"]
    assert "HoldResponse" in schema["components"]["schemas"]
    assert "OqcDecisionResponse" in schema["components"]["schemas"]
