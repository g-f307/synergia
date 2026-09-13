from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.observability.config import ObservabilityConfig
from app.observability.health import probe_email_worker, probe_storage
from app.observability.metrics import observe_http_request, render_metrics
from app.observability.telemetry import SafeJsonFormatter

client = TestClient(app)


def test_metrics_require_dedicated_credential(monkeypatch) -> None:
    config = ObservabilityConfig("", Path("storage"), "t" * 32)
    monkeypatch.setattr(
        "app.observability.routes.ObservabilityConfig.from_env", lambda: config
    )
    monkeypatch.setattr("app.observability.routes.complete_health", lambda _config: [])
    assert client.get("/metrics").status_code == 401
    response = client.get(
        "/metrics", headers={"Authorization": f"Bearer {config.scrape_token}"}
    )
    assert response.status_code == 200
    assert "synergia_http_requests_total" in response.text


def test_storage_probe_fails_and_recovers(tmp_path) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("not a directory", encoding="utf-8")
    failed = probe_storage(ObservabilityConfig("", blocked, ""))
    recovered = probe_storage(ObservabilityConfig("", tmp_path / "storage", ""))
    assert (failed.status, recovered.status) == ("unavailable", "healthy")


def test_enabled_email_worker_reports_unavailable_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "local_capture")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "noreply@example.invalid")
    monkeypatch.setenv("EMAIL_CAPTURE_PATH", str(tmp_path / "email.jsonl"))
    result = probe_email_worker(
        ObservabilityConfig(
            "postgresql://invalid:invalid@127.0.0.1:1/invalid",
            tmp_path,
            "",
            probe_timeout_seconds=1,
        )
    )
    assert (result.status, result.reason) == ("degraded", "state_unavailable")


def test_structured_log_keeps_only_allowlisted_fields() -> None:
    record = logging.LogRecord(
        "test", logging.ERROR, __file__, 1, "import.failed", (), None
    )
    record.synergia_fields = {
        "correlation_id": UUID("11111111-1111-4111-8111-111111111111"),
        "execution_id": UUID("22222222-2222-4222-8222-222222222222"),
        "password": "secret-value",
        "token": "secret-token",
        "file_content": "sensitive-row",
    }
    payload = json.loads(SafeJsonFormatter().format(record))
    assert payload["event"] == "import.failed"
    assert payload["correlation_id"].startswith("11111111")
    assert not {"password", "token", "file_content"} & payload.keys()
    assert "secret" not in json.dumps(payload)


def test_http_metrics_use_bounded_labels_without_identifiers(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    observe_http_request("GET", "/imports/{execution_id}", 500, 0.2)
    metrics = render_metrics().decode()
    assert 'route="/imports/{execution_id}"' in metrics
    for forbidden in ("correlation_id=", "execution_id=", "user_id=", "token="):
        assert forbidden not in metrics


def test_critical_journey_failures_are_exposed_by_stable_route(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    routes = (
        "/imports",
        "/executions/{execution_id}/reprocess",
        "/reports",
        "/notifications",
        "/approvals/{approval_id}/decision",
    )
    for route in routes:
        observe_http_request("POST", route, 500, 0.1)
    metrics = render_metrics().decode()
    for route in routes:
        assert f'route="{route}",status_class="5xx"' in metrics
