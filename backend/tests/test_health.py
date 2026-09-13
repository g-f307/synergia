from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.observability.config import ObservabilityConfig
from app.observability.health import ComponentStatus

client = TestClient(app)


def test_health_returns_service_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.observability.routes.ObservabilityConfig.from_env",
        lambda: ObservabilityConfig("database", Path("storage"), "x" * 32),
    )
    monkeypatch.setattr(
        "app.observability.routes.complete_health",
        lambda _config: [
            ComponentStatus("postgresql", "healthy", True, 1),
            ComponentStatus("storage", "healthy", True, 1),
            ComponentStatus("email_worker", "disabled", False, 0),
        ],
    )
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["service"] == "synergia-api"


def test_liveness_does_not_probe_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.observability.routes.critical_health",
        lambda _config: (_ for _ in ()).throw(AssertionError("dependency probed")),
    )
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_readiness_rejects_critical_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.observability.routes.ObservabilityConfig.from_env",
        lambda: ObservabilityConfig("database", Path("storage"), "x" * 32),
    )
    monkeypatch.setattr(
        "app.observability.routes.critical_health",
        lambda _config: [
            ComponentStatus("postgresql", "unavailable", True, 1, "probe_failed")
        ],
    )
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
