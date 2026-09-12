from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.authorization import (
    ActorContext,
    get_actor_context,
    get_authorization_repository,
)
from app.errors import ApiError
from app.main import app
from app.reports import CreateReportRequest, get_report_repository

pytestmark = pytest.mark.security

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)
ORG_ID = UUID("44444444-4444-4444-8444-444444444444")
USER_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_ORG_ID = UUID("66666666-6666-4666-8666-666666666666")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
TOKEN_ID = UUID("33333333-3333-4333-8333-333333333333")
CORRELATION_ID = UUID("55555555-5555-4555-8555-555555555555")


def _actor(organization_id=ORG_ID, *, permissions=None) -> ActorContext:
    return ActorContext(
        user_id=USER_ID,
        session_id=SESSION_ID,
        token_id=TOKEN_ID,
        permissions=permissions
        if permissions is not None
        else {
            "report.generate": frozenset({organization_id}),
            "report.read": frozenset({organization_id}),
            "report.cancel": frozenset({organization_id}),
            "report.export": frozenset({organization_id}),
        },
        correlation_id=CORRELATION_ID,
    )


class MemoryReportRepository:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def generate(self, payload, actor, report_id=None):
        versions = [row for row in self.items if row["report_id"] == report_id]
        if versions and (
            versions[0]["organization_id"] != payload.organization_id
            or versions[0]["report_type"] != payload.report_type
        ):
            raise ApiError(404, "resource_not_found", "Recurso não encontrado")
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
            "requested_by_display_name": "Synthetic User",
            "reference_at": payload.reference_at,
            "filters": payload.filters.model_dump(mode="json", exclude_none=True),
            "schema_version": "1.1.0",
            "created_at": NOW,
            "completed_at": NOW,
            "failure_code": None,
            "failure_message": None,
            "cancellation_reason": None,
            "data": {
                "kind": payload.report_type,
                "workorders": [{"planned_quantity": None, "produced_quantity": 0}],
            },
        }
        self.items.append(row)
        return deepcopy(row)

    def list_reports(
        self, organization_ids, report_type, state, execution_id, sort, page, page_size
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
        rows.sort(
            key=lambda row: (
                row["report_type"] if sort == "type" else row["created_at"],
                str(row["report_id"]),
            ),
            reverse=sort == "newest",
        )
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

    def cancel(self, report_id, version, actor, reason):
        rows = [
            row
            for row in self._visible(actor.scope_filter("report.cancel"))
            if row["report_id"] == report_id and row["version"] == version
        ]
        if not rows:
            return None
        if rows[0]["state"] != "generating":
            raise ApiError(
                409,
                "report_not_generating",
                "Somente uma geração em andamento pode ser cancelada",
            )
        rows[0]["state"] = "cancelled"
        rows[0]["cancellation_reason"] = reason
        rows[0]["completed_at"] = NOW
        return deepcopy(rows[0])

    def export_version(self, report_id, version, actor, export_format):
        rows = [
            row
            for row in self._visible(actor.scope_filter("report.export"))
            if row["report_id"] == report_id and row["version"] == version
        ]
        if not rows:
            return None
        if rows[0]["state"] != "succeeded":
            raise ApiError(
                409,
                "report_not_exportable",
                "Somente relatórios concluídos podem ser exportados",
            )
        return deepcopy(rows[0])

    def version_organization(self, report_id, version):
        rows = [
            row
            for row in self.items
            if row["report_id"] == report_id and row["version"] == version
        ]
        return rows[0]["organization_id"] if rows else None

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


def test_report_http_denies_missing_permissions_and_hides_other_organization() -> None:
    repository = MemoryReportRepository()
    other = repository.generate(
        CreateReportRequest(
            report_type="workorder_consolidated",
            execution_id="exec-other",
            organization_id=OTHER_ORG_ID,
            reference_at=NOW,
        ),
        _actor(OTHER_ORG_ID),
    )
    previous_actor = app.dependency_overrides.get(get_actor_context)
    app.dependency_overrides[get_report_repository] = lambda: repository
    try:
        app.dependency_overrides[get_actor_context] = lambda: _actor(permissions={})
        with TestClient(app) as client:
            assert client.get("/reports").status_code == 403
            assert (
                client.post(
                    "/reports",
                    json={
                        "report_type": "workorder_consolidated",
                        "execution_id": "exec-1",
                        "organization_id": str(ORG_ID),
                        "reference_at": NOW.isoformat(),
                    },
                ).status_code
                == 403
            )

        app.dependency_overrides[get_actor_context] = lambda: _actor()
        with TestClient(app) as client:
            assert client.get(f"/reports/{other['report_id']}").status_code == 404
            cross_version = client.post(
                f"/reports/{other['report_id']}/versions",
                json={
                    "report_type": "workorder_consolidated",
                    "execution_id": "exec-1",
                    "organization_id": str(ORG_ID),
                    "reference_at": NOW.isoformat(),
                },
            )
            assert cross_version.status_code == 404
            assert cross_version.json()["error"]["code"] == "resource_not_found"
    finally:
        app.dependency_overrides.pop(get_report_repository, None)
        if previous_actor is None:
            app.dependency_overrides.pop(get_actor_context, None)
        else:
            app.dependency_overrides[get_actor_context] = previous_actor


def test_cancel_report_generation_through_http() -> None:
    repository = MemoryReportRepository()
    pending = repository.generate(
        CreateReportRequest(
            report_type="workorder_consolidated",
            execution_id="exec-1",
            organization_id=ORG_ID,
            reference_at=NOW,
        ),
        _actor(),
    )
    repository.items[0]["state"] = "generating"
    repository.items[0]["completed_at"] = None
    previous_actor = app.dependency_overrides.get(get_actor_context)
    app.dependency_overrides[get_actor_context] = lambda: _actor()
    app.dependency_overrides[get_report_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/reports/{pending['report_id']}/versions/1/cancel",
                json={"reason": "Solicitação substituída"},
            )
            assert response.status_code == 200
            assert response.json()["state"] == "cancelled"
            assert response.json()["cancellation_reason"] == "Solicitação substituída"
            assert (
                client.post(
                    f"/reports/{pending['report_id']}/versions/1/cancel",
                    json={"reason": "Segunda tentativa"},
                ).status_code
                == 409
            )
    finally:
        app.dependency_overrides.pop(get_report_repository, None)
        if previous_actor is None:
            app.dependency_overrides.pop(get_actor_context, None)
        else:
            app.dependency_overrides[get_actor_context] = previous_actor


def test_report_policy_supports_global_generation_scope() -> None:
    previous_actor = app.dependency_overrides.get(get_actor_context)
    app.dependency_overrides[get_actor_context] = lambda: _actor(
        permissions={
            "report.read": frozenset({None}),
            "report.generate": frozenset({None}),
        }
    )
    try:
        with TestClient(app) as client:
            response = client.get("/reports/policy")
        assert response.status_code == 200
        assert response.json()["export_formats"] == ["csv", "json"]
        assert response.json()["generation_organizations"] == [
            {
                "id": str(ORG_ID),
                "organization_code": "org-001",
                "display_name": "Organization 001",
            }
        ]
        assert response.json()["stale_after_seconds"] == 900
    finally:
        if previous_actor is None:
            app.dependency_overrides.pop(get_actor_context, None)
        else:
            app.dependency_overrides[get_actor_context] = previous_actor


def test_report_catalog_exposes_validated_sort() -> None:
    repository = MemoryReportRepository()
    repository.generate(
        CreateReportRequest(
            report_type="workorder_consolidated",
            execution_id="exec-1",
            organization_id=ORG_ID,
            reference_at=NOW,
        ),
        _actor(),
    )
    app.dependency_overrides[get_report_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.get("/reports?sort=oldest")
            invalid = client.get("/reports?sort=unsupported")
        assert response.status_code == 200
        assert response.json()["sort"] == "oldest"
        assert invalid.status_code == 422
    finally:
        app.dependency_overrides.pop(get_report_repository, None)


def test_export_csv_neutralizes_formula_strings_and_preserves_numbers() -> None:
    repository = MemoryReportRepository()
    report = repository.generate(
        CreateReportRequest(
            report_type="workorder_consolidated",
            execution_id="exec-1",
            organization_id=ORG_ID,
            reference_at=NOW,
        ),
        _actor(),
    )
    repository.items[0]["data"]["workorders"] = [
        {
            "workorder_number": '  =HYPERLINK("https://invalid")',
            "produced_quantity": -7,
            "organization_code": "ORG-001",
        }
    ]
    app.dependency_overrides[get_report_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/reports/{report['report_id']}/versions/1/export?format=csv"
            )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert str(report["report_id"]) in response.headers["content-disposition"]
        assert "'  =HYPERLINK" in response.text
        assert ",-7," in response.text
    finally:
        app.dependency_overrides.pop(get_report_repository, None)


def test_export_json_is_exact_version_and_requires_exportable_state() -> None:
    repository = MemoryReportRepository()
    report = repository.generate(
        CreateReportRequest(
            report_type="oqc_summary",
            execution_id="exec-1",
            organization_id=ORG_ID,
            reference_at=NOW,
        ),
        _actor(),
    )
    app.dependency_overrides[get_report_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            exported = client.get(
                f"/reports/{report['report_id']}/versions/1/export?format=json"
            )
            assert exported.status_code == 200
            assert exported.json()["version"] == 1

            repository.items[0]["state"] = "failed"
            blocked = client.get(
                f"/reports/{report['report_id']}/versions/1/export?format=json"
            )
            assert blocked.status_code == 409
            assert blocked.json()["error"]["code"] == "report_not_exportable"
    finally:
        app.dependency_overrides.pop(get_report_repository, None)


def test_export_hides_and_audits_report_outside_organization_scope() -> None:
    repository = MemoryReportRepository()
    report = repository.generate(
        CreateReportRequest(
            report_type="workorder_consolidated",
            execution_id="exec-other",
            organization_id=OTHER_ORG_ID,
            reference_at=NOW,
        ),
        _actor(OTHER_ORG_ID),
    )
    denials: list[tuple[tuple, dict]] = []

    class RecordingAuthorizationRepository:
        def audit_denial(self, *args, **kwargs) -> None:
            denials.append((args, kwargs))

    previous_actor = app.dependency_overrides.get(get_actor_context)
    previous_authorization = app.dependency_overrides.get(get_authorization_repository)

    def actor_context(request: Request) -> ActorContext:
        base = _actor()
        return ActorContext(
            user_id=base.user_id,
            session_id=base.session_id,
            token_id=base.token_id,
            permissions=base.permissions,
            correlation_id=request.state.correlation_id,
        )

    app.dependency_overrides[get_actor_context] = actor_context
    app.dependency_overrides[get_authorization_repository] = (
        RecordingAuthorizationRepository
    )
    app.dependency_overrides[get_report_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/reports/{report['report_id']}/versions/1/export?format=csv"
            )
        assert response.status_code == 404
        assert response.json() == {
            "error": {
                "code": "resource_not_found",
                "message": "Recurso não encontrado",
                "details": {},
            }
        }
        response_correlation = UUID(response.headers["x-correlation-id"])
        assert len(denials) == 1
        args, kwargs = denials[0]
        assert args[0].user_id == USER_ID
        assert args[0].session_id == SESSION_ID
        assert args[0].correlation_id == response_correlation
        assert args[1] == "report.export"
        assert args[2].scope["route"].path.endswith("/export")
        assert kwargs == {"organization_id": OTHER_ORG_ID}
    finally:
        app.dependency_overrides.pop(get_report_repository, None)
        if previous_actor is None:
            app.dependency_overrides.pop(get_actor_context, None)
        else:
            app.dependency_overrides[get_actor_context] = previous_actor
        if previous_authorization is None:
            app.dependency_overrides.pop(get_authorization_repository, None)
        else:
            app.dependency_overrides[get_authorization_repository] = (
                previous_authorization
            )
