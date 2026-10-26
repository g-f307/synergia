from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_homologation_observability as validation  # noqa: E402


def test_homologation_contract_matches_operational_assets():
    result = validation.validate(ROOT)

    assert result["status"] == "ready_for_assisted_homologation"
    assert result["validated_alerts"] >= 10
    assert result["validated_runbooks"] >= 7
    assert result["dashboard_views"] == {
        "business_rejections",
        "system_failures",
        "resource_budget",
    }


def test_contract_keeps_external_decisions_explicit():
    contract = json.loads(
        (ROOT / "docs/homologation-observability-contract.json").read_text(
            encoding="utf-8"
        )
    )

    assert contract["corporate_destination"]["status"] == "pending_external"
    assert contract["service_levels"]["status"] == "measurement_only"
    assert contract["retention"]["logs"]["status"] == "pending_external"


@pytest.mark.parametrize(
    "forbidden",
    [
        "password",
        "authorization",
        "access_token",
        "refresh_token",
        "session_token",
        "id_token",
        "cell_value",
    ],
)
def test_validator_rejects_sensitive_observability_fields(tmp_path, forbidden):
    contract = json.loads(
        (ROOT / "docs/homologation-observability-contract.json").read_text(
            encoding="utf-8"
        )
    )
    contract["logging"]["allowed_fields"].append(forbidden)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "homologation-observability-contract.json").write_text(
        json.dumps(contract), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="sensitive field"):
        validation.validate_contract(tmp_path)


def test_controlled_storage_drill_proves_failure_and_recovery():
    evidence = validation.evaluate_recovery_drill(
        scenario="storage_unavailable",
        observations=[
            {"phase": "baseline", "status": "ok", "http_status": 200},
            {"phase": "failure", "status": "unavailable", "http_status": 503},
            {"phase": "recovery", "status": "ok", "http_status": 200},
        ],
    )

    assert evidence == {
        "scenario": "storage_unavailable",
        "result": "recovered",
        "phases": ["baseline", "failure", "recovery"],
    }


def test_storage_probe_controlled_failure_and_recovery(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.observability.config import ObservabilityConfig
    from app.observability.health import probe_storage

    config = ObservabilityConfig("database", tmp_path / "storage", "x" * 32)
    monkeypatch.setattr(
        "app.observability.routes.ObservabilityConfig.from_env", lambda: config
    )
    monkeypatch.setattr(
        "app.observability.routes.critical_health",
        lambda active: [probe_storage(active)],
    )
    client = TestClient(app)
    baseline = client.get("/health/ready")
    original_write = Path.write_bytes

    def fail_health_write(path: Path, content: bytes) -> int:
        if path.name.startswith(".health-"):
            raise OSError("controlled storage outage")
        return original_write(path, content)

    with monkeypatch.context() as failure:
        failure.setattr(Path, "write_bytes", fail_health_write)
        unavailable = client.get("/health/ready")
    recovered = client.get("/health/ready")

    evidence = validation.evaluate_recovery_drill(
        scenario="storage_unavailable",
        observations=[
            {
                "phase": "baseline",
                "status": "ok" if baseline.json()["status"] == "ready" else "invalid",
                "http_status": baseline.status_code,
            },
            {
                "phase": "failure",
                "status": (
                    "unavailable"
                    if unavailable.json()["status"] == "not_ready"
                    else "invalid"
                ),
                "http_status": unavailable.status_code,
            },
            {
                "phase": "recovery",
                "status": "ok" if recovered.json()["status"] == "ready" else "invalid",
                "http_status": recovered.status_code,
            },
        ],
    )

    assert evidence["result"] == "recovered"


def test_controlled_drill_rejects_false_recovery():
    with pytest.raises(ValueError, match="recovery was not proven"):
        validation.evaluate_recovery_drill(
            scenario="storage_unavailable",
            observations=[
                {"phase": "baseline", "status": "ok", "http_status": 200},
                {"phase": "failure", "status": "unavailable", "http_status": 503},
                {"phase": "recovery", "status": "unavailable", "http_status": 503},
            ],
        )


def test_ingestion_metric_compares_estimate_with_the_same_configured_budget():
    from app.observability import metrics

    estimate = metrics.observe_ingestion(
        outcome="completed",
        duration_seconds=2,
        rows_processed=10,
        rows_rejected=0,
        estimated_memory_bytes=640_000_000,
        memory_budget_bytes=1_000_000_000,
    )

    assert estimate == 640_000_000
    assert metrics.INGESTION_ESTIMATED_MEMORY._value.get() == 640_000_000
    assert metrics.INGESTION_MEMORY_BUDGET._value.get() == 1_000_000_000


def test_alert_runbook_mapping_is_bound_to_each_alert():
    alerts = (ROOT / "observability/prometheus/alerts.yml").read_text(encoding="utf-8")

    mapping = validation._alert_runbooks(alerts)

    assert mapping["SynergiaIngestionMemoryBudgetExceeded"].endswith(
        "/docs/runbooks/ingestion-memory-budget.md"
    )


def test_validator_rejects_runbook_borrowed_from_another_alert():
    contract = json.loads(
        (ROOT / "docs/homologation-observability-contract.json").read_text(
            encoding="utf-8"
        )
    )
    alerts = (ROOT / "observability/prometheus/alerts.yml").read_text(encoding="utf-8")
    alerts = alerts.replace(
        "/docs/runbooks/ingestion-memory-budget.md",
        "/docs/runbooks/processing-interrupted.md",
    )

    with pytest.raises(ValueError, match="SynergiaIngestionMemoryBudgetExceeded"):
        validation.validate_alerts(ROOT, contract, alerts)
