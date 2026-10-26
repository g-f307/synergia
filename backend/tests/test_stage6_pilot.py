from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_stage6_pilot as pilot  # noqa: E402

DECISION = ROOT / "docs" / "stage-6-pilot-decision.json"
EXPECTED_CRITERIA = 9
JOURNEY = {f"S-{number:02d}" for number in range(1, 13)}


def _record() -> dict:
    return json.loads(DECISION.read_text(encoding="utf-8"))


def _released(outcome: str = "release") -> dict:
    record = _record()
    record["decision"]["pilot"] = outcome
    record["decision"]["reason"] = "Roteiro concluído com os stakeholders."
    for item in record["preconditions"]:
        item["state"] = "ready"
    for value in record["signoffs"].values():
        value["status"] = "approved"
    for item in record["scenarios"]:
        item["stakeholder_execution"] = {
            "status": "passed",
            "evidence": ["docs/stage-6-pilot.md"],
        }
    return record


def test_committed_record_is_valid_and_does_not_claim_a_decision() -> None:
    result = pilot.validate()

    assert result["decision"] == "not_decided"
    assert result["executed"] == 0
    assert result["signoffs_approved"] == 0
    assert result["pending_preconditions"] == 6


def test_record_covers_the_issue_journey_and_acceptance_criteria() -> None:
    record = _record()

    assert {item["id"] for item in record["scenarios"]} == JOURNEY
    assert len(record["acceptance_criteria"]) == EXPECTED_CRITERIA
    optional = [item["id"] for item in record["scenarios"] if not item["required"]]
    assert optional == ["S-12"]


def test_every_dependency_issue_of_the_stage_is_registered() -> None:
    issues = {item["issue"] for item in _record()["dependencies"]}

    assert issues == {137, 138, 139, 140, 141, 142, 143, 144, 145}


def test_a_fully_recorded_pilot_can_be_released() -> None:
    assert pilot.validate(_released())["decision"] == "release"


def test_release_requires_both_signoffs() -> None:
    record = _released()
    record["signoffs"]["technical_owner"]["status"] = "pending"

    with pytest.raises(ValueError, match="approval"):
        pilot.validate(record)


def test_release_requires_every_required_scenario_to_pass() -> None:
    record = _released()
    record["scenarios"][0]["stakeholder_execution"] = {"status": "pending"}

    with pytest.raises(ValueError, match="required scenario not passed: S-01"):
        pilot.validate(record)


def test_an_optional_scenario_may_stay_pending() -> None:
    record = _released()
    record["scenarios"][-1]["stakeholder_execution"] = {"status": "pending"}

    assert pilot.validate(record)["decision"] == "release"


def test_release_requires_every_precondition_ready() -> None:
    record = _released()
    record["preconditions"][0]["state"] = "pending"

    with pytest.raises(ValueError, match="precondition"):
        pilot.validate(record)


@pytest.mark.parametrize("severity", ["critical", "high"])
def test_open_critical_or_high_defects_block_release(severity) -> None:
    record = _released()
    record["defects"] = [{"id": "D-1", "severity": severity, "state": "open"}]

    with pytest.raises(ValueError, match=f"untreated {severity} defect"):
        pilot.validate(record)


def test_treated_defects_need_an_owner() -> None:
    record = _released()
    record["defects"] = [{"id": "D-1", "severity": "high", "state": "treated"}]

    with pytest.raises(ValueError, match="no owner"):
        pilot.validate(record)


def test_release_with_limitations_requires_registered_limitations() -> None:
    with pytest.raises(ValueError, match="requires registered limitations"):
        pilot.validate(_released("release_with_limitations"))

    record = _released("release_with_limitations")
    record["limitations"] = [
        {
            "id": "L-1",
            "state": "open",
            "owner": "platform",
            "deadline": "before_scale_up",
        }
    ]
    assert pilot.validate(record)["decision"] == "release_with_limitations"


def test_plain_release_cannot_carry_limitations() -> None:
    record = _released()
    record["limitations"] = [
        {"id": "L-1", "state": "open", "owner": "platform", "deadline": "d"}
    ]

    with pytest.raises(ValueError, match="own decision"):
        pilot.validate(record)


def test_limitations_need_owner_and_deadline() -> None:
    record = _record()
    record["limitations"] = [{"id": "L-1", "state": "open", "owner": "platform"}]

    with pytest.raises(ValueError, match="owner and deadline"):
        pilot.validate(record)


def test_block_needs_a_reason_but_not_the_signoffs() -> None:
    record = _record()
    record["decision"]["pilot"] = "block"
    record["decision"]["reason"] = ""
    with pytest.raises(ValueError, match="reason"):
        pilot.validate(record)

    record["decision"]["reason"] = "Defeito alto sem tratamento acordado."
    assert pilot.validate(record)["decision"] == "block"


def test_unknown_decision_is_rejected() -> None:
    record = _record()
    record["decision"]["pilot"] = "approved"

    with pytest.raises(ValueError, match="invalid pilot decision"):
        pilot.validate(record)


def test_executed_scenario_needs_existing_evidence() -> None:
    record = _record()
    record["scenarios"][0]["stakeholder_execution"] = {
        "status": "passed",
        "evidence": ["docs/does-not-exist.md"],
    }

    with pytest.raises(ValueError, match="missing evidence"):
        pilot.validate(record)


@pytest.mark.parametrize("path", ["/etc/passwd", "../outside.md"])
def test_evidence_must_stay_inside_the_repository(path) -> None:
    record = _record()
    record["scenarios"][0]["rehearsal_evidence"] = [path]

    with pytest.raises(ValueError, match="missing evidence"):
        pilot.validate(record)


def test_scenarios_without_rehearsal_evidence_are_rejected() -> None:
    record = _record()
    record["scenarios"][0]["rehearsal_evidence"] = []

    with pytest.raises(ValueError, match="no evidence"):
        pilot.validate(record)


def test_duplicate_scenario_ids_are_rejected() -> None:
    record = _record()
    record["scenarios"].append(copy.deepcopy(record["scenarios"][0]))

    with pytest.raises(ValueError, match="unique"):
        pilot.validate(record)


@pytest.mark.parametrize("field", ["password", "token", "email", "secret"])
def test_credential_shaped_fields_are_forbidden(field) -> None:
    record = _record()
    record["preconditions"][0][field] = "x"

    with pytest.raises(ValueError, match="forbidden field"):
        pilot.validate(record)


def test_undelivered_dependency_is_rejected() -> None:
    record = _record()
    record["dependencies"][0]["state"] = "open"

    with pytest.raises(ValueError, match="not delivered"):
        pilot.validate(record)
