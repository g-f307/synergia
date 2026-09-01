from __future__ import annotations

from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.authorization import ActorContext, get_actor_context
from app.main import app
from app.profile import get_profile_repository


def png_bytes(size: tuple[int, int] = (8, 8)) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, color=(165, 0, 52)).save(stream, format="PNG")
    return stream.getvalue()


class FakeProfileRepository:
    def __init__(self) -> None:
        self.profile = {
            "id": uuid4(),
            "status": "active",
            "display_name": "Synthetic User",
            "emails": [
                {
                    "email": "profile@example.invalid",
                    "is_primary": True,
                    "is_verified": True,
                }
            ],
            "locale": "pt-BR",
            "timezone": "America/Manaus",
            "notifications": {"email": True, "in_app": True},
            "avatar": None,
            "permissions": [{"key": "business.read", "organizations": []}],
            "version": 1,
        }
        self.avatar_record = None

    def get(self, _actor):
        return self.profile

    def update(self, _actor, payload):
        for field in ("display_name", "locale", "timezone"):
            value = getattr(payload, field)
            if value is not None:
                self.profile[field] = value
        if payload.notifications:
            self.profile["notifications"] = payload.notifications.model_dump()
        self.profile["version"] += 1
        return self.profile

    def set_avatar(self, _actor, **metadata):
        previous = self.avatar_record["storage_key"] if self.avatar_record else None
        self.avatar_record = metadata
        self.profile["avatar"] = {
            "media_type": metadata["media_type"],
            "size_bytes": metadata["size_bytes"],
            "sha256": metadata["sha256"],
        }
        self.profile["version"] += 1
        return self.profile, previous

    def remove_avatar(self, _actor):
        if not self.avatar_record:
            return self.profile, None
        previous = self.avatar_record["storage_key"]
        self.avatar_record = None
        self.profile["avatar"] = None
        self.profile["version"] += 1
        return self.profile, previous

    def avatar(self, _actor):
        return self.avatar_record


@pytest.fixture
def profile_api(tmp_path, monkeypatch):
    repository = FakeProfileRepository()
    actor = ActorContext(
        user_id=repository.profile["id"],
        session_id=uuid4(),
        token_id=uuid4(),
        permissions={"business.read": frozenset()},
        correlation_id=uuid4(),
    )
    monkeypatch.setenv("PROFILE_AVATAR_STORAGE_ROOT", str(tmp_path))
    app.dependency_overrides[get_actor_context] = lambda: actor
    app.dependency_overrides[get_profile_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            yield client, repository, tmp_path
    finally:
        app.dependency_overrides.clear()


def test_reads_and_updates_own_profile(profile_api) -> None:
    client, _repository, _root = profile_api
    current = client.get("/me")
    assert current.status_code == 200
    assert current.json()["display_name"] == "Synthetic User"
    assert "storage_key" not in current.text

    updated = client.patch(
        "/me",
        json={
            "version": 1,
            "display_name": "Updated User",
            "locale": "en-US",
            "timezone": "UTC",
            "notifications": {"email": False, "in_app": True},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["locale"] == "en-US"
    assert updated.json()["notifications"]["email"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 1, "locale": "fr-FR"},
        {"version": 1, "timezone": "Unknown/Nowhere"},
        {"version": 1, "is_admin": True},
        {"version": 1},
    ],
)
def test_rejects_invalid_or_privileged_profile_fields(profile_api, payload) -> None:
    client, _repository, _root = profile_api
    response = client.patch("/me", json=payload)
    assert response.status_code == 422


def test_uploads_downloads_and_removes_verified_avatar(profile_api) -> None:
    client, repository, root = profile_api
    uploaded = client.post(
        "/me/avatar",
        files={"avatar": ("../../photo.png", png_bytes(), "image/png")},
    )
    assert uploaded.status_code == 201
    storage_key = repository.avatar_record["storage_key"]
    assert "photo" not in storage_key
    assert list(root.rglob(storage_key))

    downloaded = client.get("/me/avatar")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "image/png"
    assert downloaded.content == png_bytes()

    removed = client.delete("/me/avatar")
    assert removed.status_code == 200
    assert removed.json()["avatar"] is None
    assert not list(root.rglob(storage_key))


@pytest.mark.parametrize(
    ("name", "content", "media_type", "code"),
    [
        (
            "avatar.svg",
            b"<svg><script>alert(1)</script></svg>",
            "image/svg+xml",
            "avatar_content_invalid",
        ),
        ("avatar.png", png_bytes(), "image/jpeg", "avatar_media_mismatch"),
        (
            "avatar.png",
            b"<script>alert(1)</script>",
            "image/png",
            "avatar_content_invalid",
        ),
    ],
)
def test_rejects_active_or_mismatched_avatar(
    profile_api, name, content, media_type, code
) -> None:
    client, _repository, root = profile_api
    response = client.post(
        "/me/avatar", files={"avatar": (name, content, media_type)}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code
    assert not list(root.rglob("*.*"))


def test_rejects_excessive_avatar_size_and_dimensions(profile_api) -> None:
    client, _repository, root = profile_api
    oversized = client.post(
        "/me/avatar",
        files={"avatar": ("large.png", b"x" * (2 * 1024 * 1024 + 1), "image/png")},
    )
    assert oversized.status_code == 400
    assert oversized.json()["error"]["code"] == "avatar_size_invalid"

    dimensions = client.post(
        "/me/avatar",
        files={"avatar": ("wide.png", png_bytes((1025, 1)), "image/png")},
    )
    assert dimensions.status_code == 400
    assert dimensions.json()["error"]["code"] == "avatar_dimensions_invalid"
    assert not list(root.rglob("*.*"))
