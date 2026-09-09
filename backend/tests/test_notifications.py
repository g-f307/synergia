from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.notifications import get_notification_repository

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
ORG_ID = UUID("44444444-4444-4444-8444-444444444444")
NOTIFICATION_ID = UUID("77777777-7777-4777-8777-777777777777")
NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)


def notification(state="unread", version=1):
    return {
        "id": NOTIFICATION_ID,
        "type": "execution.completed",
        "state": state,
        "title": "Processamento concluído",
        "body": "A execução exec-safe foi concluída.",
        "occurrence_count": 1,
        "organization_id": ORG_ID,
        "resource_type": "execution",
        "resource_url": "/executions/exec-safe",
        "resource_available": True,
        "template_version": "1.0.0",
        "version": version,
        "first_occurred_at": NOW,
        "last_occurred_at": NOW,
        "read_at": NOW if state == "read" else None,
    }


class MemoryNotificationRepository:
    def __init__(self) -> None:
        self.item = notification()

    def list(self, actor, state_filter, sort, page, page_size):
        rows = [self.item] if state_filter in ("all", self.item["state"]) else []
        return rows, len(rows)

    def unread_count(self, actor):
        return int(self.item["state"] == "unread")

    def mark_read(self, notification_id, expected_version, actor):
        if notification_id != NOTIFICATION_ID:
            return None
        self.item = notification("read", expected_version + 1)
        return self.item

    def mark_all_read(self, actor):
        changed = int(self.item["state"] == "unread")
        self.item = notification("read", self.item["version"] + changed)
        return changed

    def notification_organization(self, notification_id):
        return ORG_ID if notification_id == NOTIFICATION_ID else None


def test_list_count_and_persistent_read_contract() -> None:
    repository = MemoryNotificationRepository()
    app.dependency_overrides[get_notification_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            listed = client.get("/notifications?filter=unread&sort=newest")
            assert listed.status_code == 200
            assert listed.json()["pagination"] == {
                "page": 1,
                "page_size": 20,
                "total": 1,
                "pages": 1,
            }
            assert listed.json()["items"][0]["resource_url"] == "/executions/exec-safe"
            assert client.get("/notifications/unread-count").json() == {"count": 1}

            read = client.patch(
                f"/notifications/{NOTIFICATION_ID}/read", json={"version": 1}
            )
            assert read.status_code == 200
            assert read.json()["state"] == "read"
            assert client.get("/notifications/unread-count").json() == {"count": 0}
    finally:
        app.dependency_overrides.pop(get_notification_repository, None)


def test_mark_all_and_unknown_notification_contracts() -> None:
    repository = MemoryNotificationRepository()
    app.dependency_overrides[get_notification_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            assert client.post("/notifications/read-all").json() == {"count": 1}
            missing = client.patch(
                "/notifications/88888888-8888-4888-8888-888888888888/read",
                json={"version": 1},
            )
            assert missing.status_code == 404
            assert missing.json()["error"]["code"] == "notification_not_found"
    finally:
        app.dependency_overrides.pop(get_notification_repository, None)
