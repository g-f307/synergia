from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.email_delivery import (
    EmailConfig,
    EmailDeliveryService,
    EmailMessage,
    LocalCaptureEmailProvider,
    TemporaryEmailError,
)


class FakeRepository:
    def __init__(self, deliveries=None) -> None:
        self.deliveries = deliveries or []
        self.claims = 0
        self.completed = []
        self.failures = []

    def claim(self, *, limit, provider):
        self.claims += 1
        assert limit > 0
        assert provider == "local_capture"
        return self.deliveries

    def complete(self, delivery_id, provider_reference):
        self.completed.append((delivery_id, provider_reference))

    def fail(self, delivery_id, *, code, retry, retry_after):
        self.failures.append((delivery_id, code, retry, retry_after))


class FailingProvider:
    name = "local_capture"

    def send(self, _message):
        raise TemporaryEmailError("credential=must-never-be-logged")


def _delivery(locale="pt-BR", attempts=0):
    return {
        "id": uuid4(),
        "recipient": "verified@example.invalid",
        "subject_template": "Execução {execution_id}",
        "body_template": "Foram encontradas {count} pendências.",
        "parameters": {
            "execution_id": "safe-123",
            "count": 2,
            "password": "must-not-render",
        },
        "locale": locale,
        "correlation_id": uuid4(),
        "attempt_count": attempts,
    }


def test_disabled_mode_does_not_claim_or_attempt_delivery() -> None:
    repository = FakeRepository([_delivery()])
    result = EmailDeliveryService(EmailConfig(), repository).run_once()
    assert result == {
        "status": "disabled",
        "processed": 0,
        "sent": 0,
        "failed": 0,
    }
    assert repository.claims == 0


def test_local_provider_captures_versioned_content_without_network(tmp_path) -> None:
    capture_path = tmp_path / "mail" / "capture.jsonl"
    delivery = _delivery("en-US")
    repository = FakeRepository([delivery])
    config = EmailConfig(
        enabled=True,
        provider="local_capture",
        sender="no-reply@example.invalid",
        capture_path=capture_path,
    )
    result = EmailDeliveryService(
        config, repository, LocalCaptureEmailProvider(capture_path)
    ).run_once()
    assert result["sent"] == 1
    record = json.loads(capture_path.read_text(encoding="utf-8"))
    assert record["recipient"] == "verified@example.invalid"
    assert record["locale"] == "en-US"
    assert "safe-123" in record["subject"]
    assert "must-not-render" not in json.dumps(record)
    assert repository.completed == [
        (delivery["id"], f"local-{delivery['id']}")
    ]


def test_temporary_failure_is_bounded_and_does_not_log_provider_details(
    caplog,
) -> None:
    delivery = _delivery(attempts=1)
    repository = FakeRepository([delivery])
    config = EmailConfig(
        enabled=True,
        provider="local_capture",
        sender="no-reply@example.invalid",
        max_attempts=2,
        retry_seconds=1,
    )
    with caplog.at_level(logging.WARNING):
        result = EmailDeliveryService(config, repository, FailingProvider()).run_once()
    assert result["failed"] == 1
    assert repository.failures[0][1:3] == (
        "provider_temporarily_unavailable",
        False,
    )
    assert "credential" not in caplog.text
    assert "must-never-be-logged" not in caplog.text


def test_environment_configuration_is_explicit_and_bounded(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "local_capture")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "no-reply@example.invalid")
    monkeypatch.setenv("EMAIL_CAPTURE_PATH", str(tmp_path / "capture.jsonl"))
    config = EmailConfig.from_env()
    assert config.enabled is True
    assert config.provider == "local_capture"
    monkeypatch.setenv("EMAIL_MAX_ATTEMPTS", "100")
    with pytest.raises(ValueError, match="EMAIL_MAX_ATTEMPTS"):
        EmailConfig.from_env()


def test_capture_contract_contains_no_credential_fields(tmp_path: Path) -> None:
    capture = tmp_path / "capture.jsonl"
    provider = LocalCaptureEmailProvider(capture)
    provider.send(
        EmailMessage(
            delivery_id=UUID("00000000-0000-4000-8000-000000000080"),
            recipient="person@example.invalid",
            sender="no-reply@example.invalid",
            subject="Assunto",
            body="Corpo mínimo",
            locale="pt-BR",
            correlation_id=None,
        )
    )
    keys = set(json.loads(capture.read_text(encoding="utf-8")))
    assert not keys.intersection({"password", "token", "api_key", "credential"})
