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
    assert result["validated_alerts"] >= 15
    assert result["validated_runbooks"] >= 12
    assert {
        "business_rejections",
        "system_failures",
        "resource_budget",
        "ai_control",
        "ai_availability",
        "ai_progress",
        "ai_security",
        "ai_maintenance",
    }.issubset(result["dashboard_views"])


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


@pytest.mark.parametrize(
    "name",
    [
        "Unavailable",
        "Stalled",
        "IntegrityViolation",
        "ExpiredReservationsGrowing",
        "RetentionFailures",
    ],
)
@pytest.mark.parametrize("mutation", ["host", "runbook", "severity", "missing"])
def test_ai_alert_contract_rejects_wrong_link_or_severity(name, mutation):
    contract = json.loads((ROOT / validation.CONTRACT).read_text())
    alerts = (ROOT / validation.ALERTS).read_text()
    name = "SynergiaAiAssistance" + name
    item = next(item for item in contract["alerts"] if item["name"] == name)
    block = validation._alert_blocks(alerts)[name]
    if mutation == "host":
        changed = block.replace("https://github.com/", "https://untrusted.invalid/")
    elif mutation == "runbook":
        changed = block.replace(item["runbook"], "docs/runbooks/ai-assistance.md")
    elif mutation == "severity":
        changed = block.replace("severity: " + item["severity"], "severity: info")
    else:
        changed = "".join(
            line for line in block.splitlines(keepends=True) if "runbook:" not in line
        )
    with pytest.raises(ValueError, match=name):
        validation.validate_alerts(ROOT, contract, alerts.replace(block, changed, 1))


def test_validator_rejects_duplicate_alerts_even_with_valid_runbooks():
    contract = json.loads((ROOT / validation.CONTRACT).read_text())
    alerts = (ROOT / validation.ALERTS).read_text()
    name = "SynergiaAiAssistanceUnavailable"
    block = validation._alert_blocks(alerts)[name]
    with pytest.raises(ValueError, match="duplicate alert: " + name):
        validation.validate_alerts(
            ROOT, contract, alerts + "\n      - alert: " + name + block
        )


def test_validator_rejects_duplicate_contract_alert():
    contract = json.loads((ROOT / validation.CONTRACT).read_text())
    contract["alerts"].append(contract["alerts"][-1])
    with pytest.raises(ValueError, match="duplicate alert in observability contract"):
        validation.validate_alerts(
            ROOT, contract, (ROOT / validation.ALERTS).read_text()
        )


def test_validator_rejects_ai_dashboard_with_a_borrowed_metric(tmp_path):
    from shutil import copytree

    # Only copy observability assets, never private docs/files or secrets.
    (tmp_path / "docs").mkdir()
    (tmp_path / validation.CONTRACT).write_text(
        (ROOT / validation.CONTRACT).read_text()
    )
    copytree(ROOT / "docs/runbooks", tmp_path / "docs/runbooks")
    (tmp_path / validation.ALERTS).parent.mkdir(parents=True)
    (tmp_path / validation.ALERTS).write_text((ROOT / validation.ALERTS).read_text())
    dashboard = json.loads((ROOT / validation.DASHBOARD).read_text())
    for panel in dashboard["panels"]:
        if panel["title"] == "AI maintenance failures":
            panel["targets"][0]["expr"] = "synergia_import_rows_total"
    (tmp_path / validation.DASHBOARD).parent.mkdir(parents=True)
    (tmp_path / validation.DASHBOARD).write_text(json.dumps(dashboard))
    with pytest.raises(ValueError, match="ai_maintenance"):
        validation.validate(tmp_path)


def test_dashboard_promtool_checks_follow_real_queries(tmp_path):
    from shutil import copyfile

    assets = tmp_path / "assets"
    for path in (validation.DASHBOARD, validation.DASHBOARD_CASES):
        (assets / path).parent.mkdir(parents=True, exist_ok=True)
        copyfile(ROOT / path, assets / path)
    dashboard = json.loads((assets / validation.DASHBOARD).read_text())
    panel = next(p for p in dashboard["panels"] if p["title"] == "AI availability")
    # A query regression must reach promtool, rather than an old copied expression.
    panel["targets"][0]["expr"] = "vector(0.75)"
    (assets / validation.DASHBOARD).write_text(json.dumps(dashboard))
    destination = tmp_path / "generated"
    validation.export_dashboard_checks(assets, destination)
    rules = json.loads((destination / "dashboard.rules.yml").read_text())
    assert any(rule["expr"] == "vector(0.75)" for rule in rules["groups"][0]["rules"])
    cases = json.loads((destination / "dashboard.test.yml").read_text())
    query = cases["tests"][0]["promql_expr_test"][0]
    assert query["expr"] == "vector(0.75)"
    assert query["exp_samples"][0]["value"] == 0.25
    assert "panel" not in query and "target" not in query
