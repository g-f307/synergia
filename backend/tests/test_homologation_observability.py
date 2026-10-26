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
    assert result["validated_runbooks"] >= 6
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
    ["password", "authorization", "access_token", "refresh_token", "cell_value"],
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
    from app.observability.config import ObservabilityConfig
    from app.observability.health import probe_storage

    config = ObservabilityConfig("database", tmp_path / "storage", "x" * 32)
    baseline = probe_storage(config)
    original_write = Path.write_bytes

    def fail_health_write(path: Path, content: bytes) -> int:
        if path.name.startswith(".health-"):
            raise OSError("controlled storage outage")
        return original_write(path, content)

    with monkeypatch.context() as failure:
        failure.setattr(Path, "write_bytes", fail_health_write)
        unavailable = probe_storage(config)
    recovered = probe_storage(config)

    evidence = validation.evaluate_recovery_drill(
        scenario="storage_unavailable",
        observations=[
            {"phase": "baseline", "status": "ok", "http_status": 200}
            if baseline.status == "healthy"
            else {},
            {"phase": "failure", "status": "unavailable", "http_status": 503}
            if unavailable.status == "unavailable"
            else {},
            {"phase": "recovery", "status": "ok", "http_status": 200}
            if recovered.status == "healthy"
            else {},
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


def test_ingestion_metric_exposes_observed_peak_and_configured_budget(monkeypatch):
    from app.observability import metrics

    monkeypatch.setattr(metrics, "peak_memory_bytes", lambda: 640_000_000)

    peak = metrics.observe_ingestion(
        outcome="completed",
        duration_seconds=2,
        rows_processed=10,
        rows_rejected=0,
        memory_budget_bytes=1_000_000_000,
    )

    assert peak == 640_000_000
    assert metrics.INGESTION_PEAK_MEMORY._value.get() == 640_000_000
    assert metrics.INGESTION_MEMORY_BUDGET._value.get() == 1_000_000_000
