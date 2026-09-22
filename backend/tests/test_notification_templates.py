from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.errors import ApiError
from app.main import app
from app.notification_templates import (
    get_notification_template_repository,
    validate_template_content,
)

REVISION_ID = UUID("77777777-7777-4777-8777-777777777777")
NOW = datetime(2026, 9, 22, 12, tzinfo=UTC)


def revision(**changes):
    result = {
        "id": REVISION_ID,
        "notification_type": "execution.completed",
        "channel": "in_app",
        "locale": "pt-BR",
        "version_number": 2,
        "version_label": "2.0.0",
        "state": "draft",
        "title_template": "Execução concluída",
        "body_template": "A execução {execution_id} foi concluída.",
        "allowed_placeholders": ["execution_id"],
        "row_version": 1,
        "created_by_user_id": UUID("00000000-0000-0000-0000-000000000001"),
        "created_reason": "teste sintético",
        "created_at": NOW,
        "updated_by_user_id": None,
        "updated_reason": None,
        "updated_at": NOW,
        "published_by_user_id": None,
        "published_reason": None,
        "published_at": None,
        "deactivated_by_user_id": None,
        "deactivated_reason": None,
        "deactivated_at": None,
    }
    result.update(changes)
    return result


class MemoryTemplateRepository:
    def __init__(self) -> None:
        self.item = revision()

    def policies(self):
        return [{
            "notification_type": "execution.completed",
            "required_permission": "execution.read",
            "resource_type": "execution",
            "allowed_placeholders": ["execution_id"],
        }]

    def list(self, **_filters):
        return [self.item], 1

    def get(self, revision_id):
        return self.item if revision_id == REVISION_ID else None

    def create(self, payload, _actor):
        self.item = revision(
            notification_type=payload.notification_type,
            channel=payload.channel,
            locale=payload.locale,
            title_template=payload.title_template,
            body_template=payload.body_template,
            created_reason=payload.reason,
        )
        return self.item

    def update(self, revision_id, payload, _actor):
        assert revision_id == REVISION_ID
        self.item = revision(
            title_template=payload.title_template,
            body_template=payload.body_template,
            updated_reason=payload.reason,
            row_version=2,
        )
        return self.item

    def publish(self, revision_id, payload, actor):
        assert revision_id == REVISION_ID
        self.item = revision(
            state="active",
            row_version=2,
            published_by_user_id=actor.user_id,
            published_reason=payload.reason,
            published_at=NOW,
        )
        return self.item

    def deactivate(self, revision_id, payload, actor):
        assert revision_id == REVISION_ID
        self.item = revision(
            state="inactive",
            row_version=2,
            published_by_user_id=actor.user_id,
            published_reason="publicação sintética",
            published_at=NOW,
            deactivated_by_user_id=actor.user_id,
            deactivated_reason=payload.reason,
            deactivated_at=NOW,
        )
        return self.item


def test_rejects_active_content_secrets_and_unknown_placeholders() -> None:
    allowed = {"execution_id"}
    for title, body, expected_code in (
        ("<script>alert(1)</script>", "safe", "template_active_content"),
        ("Safe", "javascript:alert(1)", "template_unsafe_url"),
        ("Safe", "token=abcdefghijk", "template_secret_material"),
        ("Safe", "{user.password}", "template_placeholder_not_allowed"),
        ("Safe", "{unknown}", "template_placeholder_not_allowed"),
    ):
        with pytest.raises(ApiError) as error:
            validate_template_content(title, body, allowed)
        assert error.value.code == expected_code


def test_admin_contract_supports_draft_preview_publish_and_deactivate() -> None:
    repository = MemoryTemplateRepository()
    app.dependency_overrides[get_notification_template_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            policy = client.get("/admin/notification-templates/policy")
            assert policy.status_code == 200
            assert policy.json()["external_delivery_corporate"] is False

            created = client.post(
                "/admin/notification-templates/drafts",
                json={
                    "notification_type": "execution.completed",
                    "channel": "in_app",
                    "locale": "pt-BR",
                    "title_template": "Execução concluída",
                    "body_template": "Execução {execution_id} concluída.",
                    "reason": "novo texto operacional",
                },
            )
            assert created.status_code == 201
            preview = client.post(
                f"/admin/notification-templates/{REVISION_ID}/preview"
            )
            assert preview.status_code == 200
            assert preview.json()["body"] == "Execução EXEC-SYNTHETIC-001 concluída."
            assert preview.json()["synthetic"] is True

            published = client.post(
                f"/admin/notification-templates/{REVISION_ID}/publish",
                json={"row_version": 1, "reason": "publicação homologada"},
            )
            assert published.status_code == 200
            assert published.json()["state"] == "active"
            deactivated = client.post(
                f"/admin/notification-templates/{REVISION_ID}/deactivate",
                json={"row_version": 2, "reason": "retirada controlada"},
            )
            assert deactivated.status_code == 200
            assert deactivated.json()["state"] == "inactive"
    finally:
        app.dependency_overrides.pop(get_notification_template_repository, None)


def test_unknown_revision_is_not_enumerated() -> None:
    app.dependency_overrides[get_notification_template_repository] = (
        MemoryTemplateRepository
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/admin/notification-templates/88888888-8888-4888-8888-888888888888"
            )
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "template_not_found"
    finally:
        app.dependency_overrides.pop(get_notification_template_repository, None)
