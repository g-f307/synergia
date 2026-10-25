from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SMTP_SECRET_KEYS = {"EMAIL_SMTP_PASSWORD", "EMAIL_SMTP_PASSWORD_FILE"}
SENDERS = {"email-worker"}


def _load(name: str) -> dict[str, Any]:
    # safe_load resolves the YAML anchors and merge keys the Compose file uses.
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def _environment(service: dict[str, Any]) -> dict[str, Any]:
    environment = service.get("environment") or {}
    if isinstance(environment, list):
        return dict(item.partition("=")[::2] for item in environment)
    return environment


@pytest.fixture(scope="module")
def base() -> dict[str, Any]:
    return _load("docker-compose.yml")


@pytest.fixture(scope="module")
def overlay() -> dict[str, Any]:
    return _load("docker-compose.smtp.yml")


def test_only_the_services_that_transmit_receive_the_smtp_secret(base) -> None:
    for name, service in base["services"].items():
        leaked = SMTP_SECRET_KEYS & set(_environment(service))
        if name in SENDERS:
            assert leaked == SMTP_SECRET_KEYS, name
        else:
            assert leaked == set(), f"{name} must not receive the SMTP secret"


def test_the_api_keeps_the_public_email_settings_it_reports(base) -> None:
    backend = _environment(base["services"]["backend"])

    for key in ("EMAIL_DELIVERY_ENABLED", "EMAIL_PROVIDER", "EMAIL_SMTP_HOST"):
        assert key in backend


def test_the_secret_file_overlay_mounts_only_on_the_senders(base, overlay) -> None:
    assert set(overlay["services"]) <= SENDERS
    assert "backend" not in overlay["services"]
    for name, service in overlay["services"].items():
        assert service["secrets"] == ["smtp_password"], name
        assert _environment(service)["EMAIL_SMTP_PASSWORD"] == ""
        assert (
            _environment(service)["EMAIL_SMTP_PASSWORD_FILE"]
            == "/run/secrets/smtp_password"
        )
    assert set(overlay["secrets"]) == {"smtp_password"}


def test_no_service_outside_the_senders_mounts_any_secret(base, overlay) -> None:
    merged: dict[str, list[str]] = {}
    for document in (base, overlay):
        for name, service in document["services"].items():
            merged.setdefault(name, []).extend(service.get("secrets") or [])

    assert {name for name, secrets in merged.items() if secrets} <= SENDERS


def test_the_overlay_secret_path_is_required_and_external(overlay) -> None:
    source = overlay["secrets"]["smtp_password"]["file"]

    assert source.startswith("${EMAIL_SMTP_SECRET_PATH:?")
