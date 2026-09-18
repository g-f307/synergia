#!/usr/bin/env python3
"""Validate the Stage 5 technical decision without inventing corporate approval."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "docs" / "stage-5-release-decision.json"
RISKS = ROOT / "docs" / "security-risk-register.json"

TECHNICAL_GATE_IDS = {
    "environment-and-integrated-journey",
    "security-and-supply-chain",
    "abuse-and-recovery",
    "observability",
    "backup-and-restore",
    "reference-volume-integrity",
    "language-accessibility-and-responsive-ui",
    "production-build-and-compose",
}
ALLOWED_SIGNOFF_STATES = {"pending", "approved", "rejected"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_evidence(relative_paths: list[str], subject: str) -> None:
    if not relative_paths:
        raise ValueError(f"{subject} has no evidence")
    for relative in relative_paths:
        path = Path(relative)
        if path.is_absolute() or not (ROOT / path).is_file():
            raise ValueError(f"{subject} references missing evidence: {relative}")


def _all_signoffs_approved(
    signoffs: Mapping[str, Mapping[str, Any]],
) -> bool:
    return all(
        signoff.get("status") == "approved" for signoff in signoffs.values()
    )


def validate() -> dict:
    decision = _load(DECISION)
    if decision.get("schema_version") != 1 or decision.get("stage") != 5:
        raise ValueError("unsupported Stage 5 decision schema")

    outcomes = decision.get("decisions", {})
    if outcomes.get("pre_rpa_homologation") != "technically_ready":
        raise ValueError("pre-RPA technical decision is not ready")
    if outcomes.get("release_candidate") not in {"approved", "not_approved"}:
        raise ValueError("invalid release-candidate decision")
    if outcomes.get("stage_6_entry") not in {"authorized", "not_authorized"}:
        raise ValueError("invalid Stage 6 decision")

    technical = decision.get("technical_gates", [])
    ids = {gate.get("id") for gate in technical}
    if ids != TECHNICAL_GATE_IDS or len(ids) != len(technical):
        raise ValueError("Stage 5 technical gate coverage is incomplete")
    for gate in technical:
        if gate.get("status") != "passed":
            raise ValueError(f"technical gate did not pass: {gate.get('id')}")
        _require_evidence(gate.get("evidence", []), f"gate {gate['id']}")

    risks = {risk["id"]: risk for risk in _load(RISKS).get("risks", [])}
    corporate = decision.get("corporate_gates", [])
    if not corporate:
        raise ValueError("corporate gates are not recorded")
    tracked_risks: set[str] = set()
    for gate in corporate:
        required = {
            "id",
            "status",
            "owner",
            "mitigation",
            "deadline",
            "retest_criterion",
        }
        if not required <= gate.keys() or gate.get("status") not in {
            "pending",
            "blocked",
            "approved",
        }:
            raise ValueError(
                "corporate gate lacks owner, mitigation, deadline or retest"
            )
        related = gate.get("related_risks", [])
        if not related or any(risk_id not in risks for risk_id in related):
            raise ValueError(
                f"corporate gate has invalid risk linkage: {gate.get('id')}"
            )
        tracked_risks.update(related)

    untreated = {
        risk_id
        for risk_id, risk in risks.items()
        if risk.get("residual_severity") in {"high", "critical"}
        and risk.get("disposition")
        not in {"mitigated", "accepted", "blocked", "transferred"}
    }
    if untreated:
        raise ValueError(f"untreated high or critical risks: {sorted(untreated)}")
    governed = {
        risk_id
        for risk_id, risk in risks.items()
        if risk.get("residual_severity") in {"high", "critical"}
        and risk.get("disposition") in {"blocked", "transferred"}
    }
    if missing := governed - tracked_risks:
        raise ValueError(
            f"high corporate risks absent from release decision: {sorted(missing)}"
        )

    signoffs = decision.get("signoffs", {})
    if not isinstance(signoffs, Mapping) or any(
        not isinstance(role, str) or not isinstance(item, Mapping)
        for role, item in signoffs.items()
    ):
        raise ValueError("invalid sign-off structure")
    for role in ("product_owner", "technical_owner"):
        item = signoffs.get(role, {})
        if (
            item.get("status") not in ALLOWED_SIGNOFF_STATES
            or not item.get("record_at")
        ):
            raise ValueError(f"invalid or absent sign-off: {role}")
    fully_signed = _all_signoffs_approved(signoffs)
    technical_approved = all(gate["status"] == "passed" for gate in technical)
    corporate_approved = all(gate["status"] == "approved" for gate in corporate)
    release_prerequisites_met = (
        technical_approved and corporate_approved and fully_signed
    )

    if (
        outcomes["release_candidate"] == "approved"
        and not release_prerequisites_met
    ):
        raise ValueError(
            "release candidate requires approved technical and corporate gates "
            "and both sign-offs"
        )
    if outcomes["stage_6_entry"] == "authorized":
        if outcomes["release_candidate"] != "approved":
            raise ValueError("Stage 6 requires an approved release candidate")
        if not release_prerequisites_met:
            raise ValueError(
                "Stage 6 requires approved technical and corporate gates "
                "and both sign-offs"
            )
    return decision


def main() -> int:
    decision = validate()
    print(
        "OK: Stage 5 technically ready; "
        f"release candidate={decision['decisions']['release_candidate']}; "
        f"Stage 6={decision['decisions']['stage_6_entry']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
