#!/usr/bin/env python3
"""Validate the Stage 6 pilot record without inventing stakeholder acceptance."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
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
EVIDENCE_FIELDS = {
    "scenario_id",
    "status",
    "sanitized",
    "executed_at",
    "environment",
    "responsible_role",
    "counts",
    "codes",
    "observations",
}
EVIDENCE_ROLES = {
    "stakeholder",
    "product_owner",
    "technical_owner",
    "facilitator",
    "platform",
    "identity",
}
EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
CREDENTIAL_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|token|authorization)\s*[:=]\s*\S+"
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_evidence(
    paths: Any, subject: str, root: Path, *, execution: bool = False
) -> None:
    if not isinstance(paths, list) or not paths:
        raise ValueError(f"{subject} has no evidence")
    for relative in paths:
        pure = PurePosixPath(str(relative))
        if execution and (
            len(pure.parts) < 3 or pure.parts[:2] != ("docs", "evidence")
        ):
            raise ValueError(
                f"{subject} execution evidence must be under docs/evidence/: {relative}"
            )
        if pure.is_absolute() or ".." in pure.parts or not (root / pure).is_file():
            raise ValueError(f"{subject} references missing evidence: {relative}")


def _check_execution_evidence(
    paths: Any, scenario_id: str, state: str, root: Path
) -> None:
    subject = f"scenario {scenario_id} execution"
    _check_evidence(paths, subject, root, execution=True)
    if len(paths) != 1:
        raise ValueError(f"{subject} must reference one dedicated execution record")
    expected = PurePosixPath("docs/evidence/stage-6") / f"{scenario_id}.json"
    if PurePosixPath(str(paths[0])) != expected:
        raise ValueError(f"{subject} must reference its dedicated record: {expected}")
    try:
        evidence = _load(root / expected)
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError(f"{subject} evidence must be a valid JSON record") from error
    if not isinstance(evidence, Mapping) or set(evidence) != EVIDENCE_FIELDS:
        raise ValueError(f"{subject} evidence has an invalid record structure")
    _reject_forbidden_keys(evidence)
    try:
        executed_at = datetime.fromisoformat(evidence["executed_at"])
    except (TypeError, ValueError) as error:
        raise ValueError(f"{subject} evidence needs an ISO-8601 execution time") from error
    if executed_at.tzinfo is None or executed_at.utcoffset() is None:
        raise ValueError(f"{subject} evidence execution time needs a timezone")
    if evidence["environment"] != "homologation":
        raise ValueError(f"{subject} evidence environment must be homologation")
    if evidence["responsible_role"] not in EVIDENCE_ROLES:
        raise ValueError(f"{subject} evidence needs an approved responsible role")
    counts = evidence["counts"]
    codes = evidence["codes"]
    observations = evidence["observations"]
    if not isinstance(counts, Mapping) or any(
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        for count in counts.values()
    ):
        raise ValueError(f"{subject} evidence counts must be non-negative integers")
    if not isinstance(codes, list) or any(
        not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_.-]{1,64}", code)
        for code in codes
    ):
        raise ValueError(f"{subject} evidence codes must be sanitized code labels")
    if not isinstance(observations, list) or any(
        not isinstance(observation, str)
        or EMAIL_PATTERN.search(observation)
        or CREDENTIAL_PATTERN.search(observation)
        for observation in observations
    ):
        raise ValueError(f"{subject} evidence observations must be sanitized text")
    if (
        evidence.get("scenario_id") != scenario_id
        or evidence.get("status") != state
        or evidence.get("sanitized") is not True
    ):
        raise ValueError(f"{subject} evidence does not match its scenario execution")


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
    dependencies = document.get("dependencies", [])
    dependency_issues = {item.get("issue") for item in dependencies}
    if dependency_issues != EXPECTED_DEPENDENCIES:
        raise ValueError("dependencies must contain exactly issues #137 through #145")
    _unique(dependencies, "issue", "dependency")
    scenario_ids = {item.get("id") for item in document.get("scenarios", [])}
    if scenario_ids != EXPECTED_SCENARIOS:
        raise ValueError("scenarios must contain exactly S-01 through S-12")
    criteria = document.get("acceptance_criteria", [])
    criterion_ids = {item.get("id") for item in criteria}
    if criterion_ids != EXPECTED_CRITERIA:
        raise ValueError("acceptance criteria must contain exactly AC-01 through AC-09")
    _unique(criteria, "id", "acceptance criterion")

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
            _check_execution_evidence(
                execution.get("evidence"), item["id"], state, root
            )

    pc06 = next(item for item in document["preconditions"] if item["id"] == "PC-06")
    smtp_decision = pc06.get("smtp")
    if smtp_decision not in {"included", "excluded"}:
        raise ValueError("PC-06 must record smtp as included or excluded")
    smtp_scenario = next(item for item in scenarios if item["id"] == "S-12")
    if smtp_scenario.get("required") != (smtp_decision == "included"):
        raise ValueError("S-12 required flag must match the PC-06 SMTP decision")
    if any(
        item.get("required") is not True
        for item in scenarios
        if item["id"] != "S-12"
    ):
        raise ValueError("scenarios S-01 through S-11 must remain required")

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
        smtp_exception = (
            item["id"] == "S-12"
            and item["required"]
            and state == "failed"
            and outcome == "release_with_limitations"
        )
        if item["required"] and state != "passed" and not smtp_exception:
            raise ValueError(f"required scenario not passed: {item['id']}")
    invalid_criteria = [
        item["id"]
        for item in document["acceptance_criteria"]
        if item["status"]
        != ("ci_gate" if item["id"] == "AC-08" else "accepted")
    ]
    if invalid_criteria:
        raise ValueError(
            "release requires AC-01–AC-07 and AC-09 accepted and AC-08 ci_gate"
        )
    failed = [
        item["id"]
        for item in document["scenarios"]
        if item["stakeholder_execution"]["status"] == "failed"
    ]
    smtp_included = next(
        item["smtp"] == "included"
        for item in document["preconditions"]
        if item["id"] == "PC-06"
    )
    if failed and not (
        failed == ["S-12"]
        and smtp_included
        and outcome == "release_with_limitations"
    ):
        raise ValueError(
            "only failed included SMTP scenario S-12 may be accepted with limitations"
        )
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
