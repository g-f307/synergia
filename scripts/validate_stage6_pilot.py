#!/usr/bin/env python3
"""Validate the Stage 6 pilot record without inventing stakeholder acceptance."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "docs" / "stage-6-pilot-decision.json"

OUTCOMES = {"not_decided", "release", "release_with_limitations", "block"}
SCENARIO_STATES = {"pending", "passed", "failed"}
PRECONDITION_STATES = {"pending", "ready"}
SIGNOFF_STATES = {"pending", "approved", "rejected"}
SEVERITIES = {"critical", "high", "medium", "low"}
DEFECT_STATES = {"open", "treated", "accepted"}
LIMITATION_STATES = {"open", "accepted"}
REQUIRED_SIGNOFFS = {"product_owner", "technical_owner"}
FORBIDDEN_FRAGMENTS = ("password", "secret", "token", "email", "authorization")
EXPECTED_PRECONDITIONS = {f"PC-{number:02d}" for number in range(1, 7)}
EXPECTED_DEPENDENCIES = set(range(137, 146))
EXPECTED_SCENARIOS = {f"S-{number:02d}" for number in range(1, 13)}
EXPECTED_CRITERIA = {f"AC-{number:02d}" for number in range(1, 10)}
CRITERION_STATES = {"pending", "rehearsed", "accepted", "blocked", "ci_gate"}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_evidence(
    paths: Any, subject: str, root: Path, *, execution: bool = False
) -> None:
    if not isinstance(paths, list) or not paths:
        raise ValueError(f"{subject} has no evidence")
    for relative in paths:
        pure = PurePosixPath(str(relative))
        if pure.is_absolute() or ".." in pure.parts or not (root / pure).is_file():
            raise ValueError(f"{subject} references missing evidence: {relative}")
        if execution and (
            len(pure.parts) < 3 or pure.parts[:2] != ("docs", "evidence")
        ):
            raise ValueError(
                f"{subject} execution evidence must be under docs/evidence/: {relative}"
            )


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = "".join(char for char in str(key).lower() if char.isalnum())
            if any(fragment in normalized for fragment in FORBIDDEN_FRAGMENTS):
                raise ValueError(f"forbidden field in pilot record: {key}")
            _reject_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_keys(item)


def _unique(items: list[Mapping[str, Any]], key: str, subject: str) -> set[Any]:
    identifiers = [item.get(key) for item in items]
    if None in identifiers or len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{subject} identifiers must be present and unique")
    return set(identifiers)


def _validate_structure(document: Mapping[str, Any], root: Path) -> None:
    if (
        document.get("schema_version") != 1
        or document.get("stage") != 6
        or document.get("issue") != 146
    ):
        raise ValueError("unsupported Stage 6 pilot schema")
    _reject_forbidden_keys(document)

    precondition_ids = {item.get("id") for item in document.get("preconditions", [])}
    if precondition_ids != EXPECTED_PRECONDITIONS:
        raise ValueError("preconditions must contain exactly PC-01 through PC-06")
    dependency_issues = {item.get("issue") for item in document.get("dependencies", [])}
    if dependency_issues != EXPECTED_DEPENDENCIES:
        raise ValueError("dependencies must contain exactly issues #137 through #145")
    scenario_ids = {item.get("id") for item in document.get("scenarios", [])}
    if scenario_ids != EXPECTED_SCENARIOS:
        raise ValueError("scenarios must contain exactly S-01 through S-12")
    criterion_ids = {
        item.get("id") for item in document.get("acceptance_criteria", [])
    }
    if criterion_ids != EXPECTED_CRITERIA:
        raise ValueError("acceptance criteria must contain exactly AC-01 through AC-09")

    for item in document.get("preconditions", []):
        if item.get("state") not in PRECONDITION_STATES or not item.get("owner"):
            raise ValueError(f"invalid precondition: {item.get('id')}")
    _unique(document.get("preconditions", []), "id", "precondition")

    for item in document.get("dependencies", []):
        if item.get("state") != "delivered":
            raise ValueError(f"dependency not delivered: #{item.get('issue')}")
        _check_evidence(item.get("evidence"), f"dependency #{item.get('issue')}", root)

    scenarios = document.get("scenarios", [])
    _unique(scenarios, "id", "scenario")
    for item in scenarios:
        _check_evidence(
            item.get("rehearsal_evidence"), f"scenario {item['id']} rehearsal", root
        )
        execution = item.get("stakeholder_execution", {})
        state = execution.get("status")
        if state not in SCENARIO_STATES:
            raise ValueError(f"invalid execution state: {item['id']}")
        if state != "pending":
            if (
                execution.get("scenario_id") != item["id"]
                or execution.get("sanitized") is not True
            ):
                raise ValueError(
                    f"scenario {item['id']} execution must identify the scenario "
                    "and be sanitized"
                )
            _check_evidence(
                execution.get("evidence"),
                f"scenario {item['id']} execution",
                root,
                execution=True,
            )

    pc06 = next(item for item in document["preconditions"] if item["id"] == "PC-06")
    smtp_decision = pc06.get("smtp")
    if smtp_decision not in {"included", "excluded"}:
        raise ValueError("PC-06 must record smtp as included or excluded")
    smtp_scenario = next(item for item in scenarios if item["id"] == "S-12")
    if smtp_scenario.get("required") != (smtp_decision == "included"):
        raise ValueError("S-12 required flag must match the PC-06 SMTP decision")

    for item in document.get("defects", []):
        if (
            item.get("severity") not in SEVERITIES
            or item.get("state") not in DEFECT_STATES
        ):
            raise ValueError(f"invalid defect: {item.get('id')}")
        if item["state"] != "open" and not item.get("owner"):
            raise ValueError(f"treated defect has no owner: {item.get('id')}")
    for item in document.get("limitations", []):
        if item.get("state") not in LIMITATION_STATES or not (
            item.get("owner") and item.get("deadline")
        ):
            raise ValueError(f"limitation needs owner and deadline: {item.get('id')}")

    signoffs = document.get("signoffs", {})
    if set(signoffs) != REQUIRED_SIGNOFFS or any(
        value.get("status") not in SIGNOFF_STATES for value in signoffs.values()
    ):
        raise ValueError("invalid sign-off structure")

    known = {item["id"] for item in scenarios}
    for criterion in document.get("acceptance_criteria", []):
        if set(criterion.get("scenarios", [])) - known:
            raise ValueError(
                f"criterion references unknown scenario: {criterion['id']}"
            )
        if criterion.get("status") not in CRITERION_STATES:
            raise ValueError(f"invalid acceptance criterion status: {criterion['id']}")


def _validate_outcome(document: Mapping[str, Any]) -> str:
    decision = document.get("decision", {})
    outcome = decision.get("pilot")
    if outcome not in OUTCOMES or set(decision.get("allowed", [])) != OUTCOMES:
        raise ValueError("invalid pilot decision")
    if outcome == "not_decided":
        return outcome
    if not decision.get("reason"):
        raise ValueError("a pilot decision needs a recorded reason")
    if outcome == "block":
        return outcome

    if any(item["state"] != "ready" for item in document.get("preconditions", [])):
        raise ValueError("release requires every precondition to be ready")
    if any(value["status"] != "approved" for value in document["signoffs"].values()):
        raise ValueError("release requires product owner and technical owner approval")
    for item in document["scenarios"]:
        state = item["stakeholder_execution"]["status"]
        if item["required"] and state != "passed" and not (
            outcome == "release_with_limitations" and state == "failed"
        ):
            raise ValueError(f"required scenario not passed: {item['id']}")
    if any(item["status"] == "pending" for item in document["acceptance_criteria"]):
        raise ValueError("release requires every acceptance criterion to be resolved")
    failed = [
        item["id"]
        for item in document["scenarios"]
        if item["stakeholder_execution"]["status"] == "failed"
    ]
    if failed and outcome != "release_with_limitations":
        raise ValueError("failed scenario requires release_with_limitations")
    for item in document.get("defects", []):
        if item["severity"] in {"critical", "high"} and item["state"] == "open":
            raise ValueError(f"untreated {item['severity']} defect: {item['id']}")
    limitations = document.get("limitations", [])
    if outcome == "release" and limitations:
        raise ValueError("release with limitations must use its own decision")
    if outcome == "release_with_limitations" and not limitations:
        raise ValueError("release with limitations requires registered limitations")
    return outcome


def validate(
    document: Mapping[str, Any] | None = None, root: Path = ROOT
) -> dict[str, Any]:
    document = _load(DECISION) if document is None else document
    _validate_structure(document, root)
    outcome = _validate_outcome(document)
    scenarios = document["scenarios"]
    return {
        "decision": outcome,
        "scenarios": len(scenarios),
        "executed": sum(
            item["stakeholder_execution"]["status"] != "pending" for item in scenarios
        ),
        "pending_preconditions": sum(
            item["state"] == "pending" for item in document["preconditions"]
        ),
        "signoffs_approved": sum(
            value["status"] == "approved" for value in document["signoffs"].values()
        ),
    }


def main() -> int:
    print(json.dumps(validate(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
