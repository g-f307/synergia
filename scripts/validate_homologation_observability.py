from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

CONTRACT = Path("docs/homologation-observability-contract.json")
ALERTS = Path("observability/prometheus/alerts.yml")
DASHBOARD = Path("observability/grafana/dashboards/synergia-technical.json")

SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "authorization",
        "access_token",
        "refresh_token",
        "token",
        "secret",
        "cell_value",
        "payload",
        "internal_path",
    }
)
REQUIRED_PHASES = ("baseline", "failure", "recovery")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON asset: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"JSON asset must be an object: {path}")
    return document


def validate_contract(root: Path) -> dict[str, Any]:
    contract = _load_json(root / CONTRACT)
    if contract.get("schema_version") != 1:
        raise ValueError("unsupported observability contract version")
    if contract.get("status") != "ready_for_assisted_homologation":
        raise ValueError("homologation contract is not ready")

    allowed = set(contract.get("logging", {}).get("allowed_fields", []))
    unsafe = allowed & SENSITIVE_FIELDS
    if unsafe:
        raise ValueError(f"sensitive field in logging allowlist: {sorted(unsafe)}")

    if contract.get("corporate_destination", {}).get("status") != "pending_external":
        raise ValueError("corporate destination must remain an explicit external gate")
    if contract.get("service_levels", {}).get("status") != "measurement_only":
        raise ValueError("service levels cannot be promoted without observed data")

    correlation = set(contract.get("correlation", {}).get("fields", []))
    if not {"correlation_id", "execution_id"}.issubset(correlation):
        raise ValueError("request and execution correlation fields are required")

    return contract


def _alert_names_and_runbooks(text: str) -> tuple[set[str], set[str]]:
    names = set(re.findall(r"^\s*- alert:\s*([A-Za-z0-9_]+)\s*$", text, re.M))
    runbooks = set(re.findall(r"^\s*runbook:\s*(\S+)\s*$", text, re.M))
    return names, runbooks


def _dashboard_panels(document: dict[str, Any]) -> dict[str, str]:
    panels: dict[str, str] = {}
    for panel in document.get("panels", []):
        expressions = "\n".join(
            target.get("expr", "") for target in panel.get("targets", [])
        )
        panels[str(panel.get("title", ""))] = expressions
    return panels


def validate(root: Path) -> dict[str, Any]:
    contract = validate_contract(root)
    alerts_text = (root / ALERTS).read_text(encoding="utf-8")
    alert_names, runbook_urls = _alert_names_and_runbooks(alerts_text)

    expected_alerts = {item["name"] for item in contract["alerts"]}
    missing_alerts = expected_alerts - alert_names
    if missing_alerts:
        raise ValueError(f"alerts missing from Prometheus rules: {sorted(missing_alerts)}")
    for item in contract["alerts"]:
        runbook = root / item["runbook"]
        if not runbook.is_file():
            raise ValueError(f"missing runbook: {item['runbook']}")
        expected_url_suffix = f"/blob/main/{item['runbook']}"
        if not any(url.endswith(expected_url_suffix) for url in runbook_urls):
            raise ValueError(f"alert has no matching runbook URL: {item['name']}")

    panels = _dashboard_panels(_load_json(root / DASHBOARD))
    dashboard_views: set[str] = set()
    for view, expected in contract["dashboard_views"].items():
        expression = panels.get(expected["panel"])
        if expression is None or expected["metric"] not in expression:
            raise ValueError(f"dashboard view is missing or inconsistent: {view}")
        dashboard_views.add(view)

    return {
        "status": contract["status"],
        "validated_alerts": len(expected_alerts),
        "validated_runbooks": len({item["runbook"] for item in contract["alerts"]}),
        "dashboard_views": dashboard_views,
    }


def evaluate_recovery_drill(
    *, scenario: str, observations: list[dict[str, Any]]
) -> dict[str, Any]:
    phases = [item.get("phase") for item in observations]
    if phases != list(REQUIRED_PHASES):
        raise ValueError("drill must contain baseline, failure and recovery in order")
    expected = (
        ("ok", 200),
        ("unavailable", 503),
        ("ok", 200),
    )
    actual = tuple((item.get("status"), item.get("http_status")) for item in observations)
    if actual != expected:
        raise ValueError("recovery was not proven by the controlled drill")
    return {"scenario": scenario, "result": "recovered", "phases": phases}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = validate(args.root.resolve())
    print(json.dumps({**result, "dashboard_views": sorted(result["dashboard_views"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
