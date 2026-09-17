from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "data-retention-policy.json"
ALERTS = ROOT / "observability" / "prometheus" / "alerts.yml"
REQUIRED_GROUPS = {
    "identity_profiles",
    "authorization_configuration",
    "sessions_and_tokens",
    "security_transient",
    "operational_records",
    "accepted_uploads",
    "quarantine",
    "avatars",
    "reports",
    "notifications",
    "email_delivery",
    "email_local_capture",
    "human_approvals",
    "audit_trails",
    "technical_logs",
    "metrics",
    "backup_bundles",
    "ci_evidence",
}
REQUIRED_RUNBOOK_SECTIONS = {
    "## Responsável e escalonamento",
    "## Pré-condições",
    "## Procedimento",
    "## Rollback",
    "## Validação e evidências",
}


def validate_policy() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["status"] == "proposed_for_homologation"
    assert policy["rpo_hours"] > 0 and policy["rto_hours"] > 0
    tolerance = policy["backup_alert_tolerance_seconds"]
    assert tolerance == (policy["rpo_hours"] + 1) * 60 * 60
    assert f"}} > {tolerance}" in ALERTS.read_text(encoding="utf-8")
    groups = {item["id"]: item for item in policy["groups"]}
    assert len(policy["groups"]) == len(REQUIRED_GROUPS)
    assert set(groups) == REQUIRED_GROUPS
    for item in groups.values():
        assert all(
            item.get(field)
            for field in (
                "purpose",
                "sensitivity",
                "stores",
                "retention",
                "disposition",
                "owner",
            )
        )
        assert isinstance(item["automated"], bool)
        assert isinstance(item["backup"], bool)
    assert groups["audit_trails"]["automated"] is False
    assert groups["audit_trails"]["disposition"] == "immutable_no_automatic_purge"
    assert groups["quarantine"]["backup"] is False


def validate_runbooks() -> None:
    alerts = ALERTS.read_text(encoding="utf-8")
    urls = re.findall(r"runbook: (https://\S+)", alerts)
    assert urls, "Alertas sem runbooks versionados"
    prefix = "https://github.com/g-f307/synergia/blob/main/"
    for url in urls:
        assert url.startswith(prefix)
        relative = url.removeprefix(prefix).split("#", 1)[0]
        path = ROOT / relative
        assert path.is_file(), f"Runbook ausente: {relative}"
        content = path.read_text(encoding="utf-8")
        assert REQUIRED_RUNBOOK_SECTIONS <= set(
            re.findall(r"^## .+$", content, re.MULTILINE)
        )


def validate_no_secret_material() -> None:
    public_files = [POLICY, *sorted((ROOT / "docs" / "runbooks").glob("*.md"))]
    forbidden = re.compile(
        r"(postgres(?:ql)?://[^\s:]+:[^\s@]+@|BEGIN (?:RSA |OPENSSH )?PRIVATE KEY)",
        re.IGNORECASE,
    )
    for path in public_files:
        assert not forbidden.search(path.read_text(encoding="utf-8")), path


def main() -> None:
    validate_policy()
    validate_runbooks()
    validate_no_secret_material()
    print(f"Política validada: {len(REQUIRED_GROUPS)} grupos de dados")


if __name__ == "__main__":
    main()
