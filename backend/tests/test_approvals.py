from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.approvals import get_approval_repository
from app.main import app

REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
ORG_ID = UUID("44444444-4444-4444-8444-444444444444")
USER_ID = UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 9, 9, 20, tzinfo=UTC)


def approval(state="submitted", version=1, assignee=None):
    return {
        "id": REQUEST_ID,
        "pending_item_id": 7,
        "organization_id": ORG_ID,
        "requester_user_id": USER_ID,
        "assignee_user_id": assignee,
        "review_group": "gestor",
        "policy_key": "pending.standard",
        "policy_version": 1,
        "state": state,
        "version": version,
        "created_at": NOW,
        "submitted_at": NOW,
        "decided_at": NOW if state in {"approved", "rejected"} else None,
        "updated_at": NOW,
        "history": [],
    }


class MemoryApprovalRepository:
    def __init__(self):
        self.item = approval()

    def get_for_pending(self, pending_id, actor, permission="approval.read"):
        return self.item if pending_id == 7 else None

    def create(self, pending_id, justification, actor):
        return self.item if pending_id == 7 else None

    def assign(self, request_id, assignee_id, version, justification, actor):
        self.item = approval("in_review", version + 1, assignee_id)
        return self.item

    def decide(self, request_id, action, version, justification, consent, actor):
        self.item = approval(action, version + 1, actor.user_id)
        return self.item

    def resubmit(self, request_id, version, justification, actor):
        self.item = approval("submitted", version + 1)
        return self.item


def test_submit_get_assign_and_approve_contracts() -> None:
    repository = MemoryApprovalRepository()
    app.dependency_overrides[get_approval_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            created = client.post(
                "/pending-items/7/approval",
                json={"justification": "Analisar divergência"},
            )
            assert created.status_code == 201
            assert created.json()["state"] == "submitted"
            assert client.get("/pending-items/7/approval").status_code == 200
            assigned = client.post(
                f"/approvals/{REQUEST_ID}/assign",
                json={
                    "version": 1,
                    "assignee_user_id": str(USER_ID),
                    "justification": "Responsável disponível",
                },
            )
            assert assigned.json()["state"] == "in_review"
            decided = client.post(
                f"/approvals/{REQUEST_ID}/approve",
                json={
                    "version": 2,
                    "justification": "Evidências conferidas",
                    "consent": True,
                },
            )
            assert decided.json()["state"] == "approved"
    finally:
        app.dependency_overrides.pop(get_approval_repository, None)


def test_payloads_require_explicit_justification_and_consent_field_is_boolean() -> None:
    repository = MemoryApprovalRepository()
    app.dependency_overrides[get_approval_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            assert client.post("/pending-items/7/approval", json={}).status_code == 422
            invalid = client.post(
                f"/approvals/{REQUEST_ID}/approve",
                json={"version": 1, "justification": "ok", "consent": "yes"},
            )
            assert invalid.status_code == 422
            assert client.get("/pending-items/999/approval").status_code == 404
    finally:
        app.dependency_overrides.pop(get_approval_repository, None)
