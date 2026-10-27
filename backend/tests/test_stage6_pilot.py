from __future__ import annotations

import copy
import json
import shutil
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


def _execution_evidence(scenario_id: str, status: str) -> dict:
    return {
        "scenario_id": scenario_id,
        "status": status,
        "sanitized": True,
        "executed_at": "2026-10-26T12:00:00-04:00",
        "environment": "homologation",
        "responsible_role": "stakeholder",
        "counts": {"records": 3},
        "codes": ["PILOT_OK"],
        "observations": ["synthetic test fixture only"],
    }


def _synthetic_release_record(root: Path, outcome: str = "release") -> dict:
    record = _record()
    record["decision"]["pilot"] = outcome
    record["decision"]["reason"] = "Roteiro concluído com os stakeholders."
    for item in record["preconditions"]:
        item["state"] = "ready"
    for value in record["signoffs"].values():
        value["status"] = "approved"
    for item in record["scenarios"]:
        evidence_path = Path("docs/evidence/stage-6") / f"{item['id']}.json"
        evidence_file = root / evidence_path
        evidence_file.parent.mkdir(parents=True, exist_ok=True)
        evidence_file.write_text(
            json.dumps(_execution_evidence(item["id"], "passed")),
            encoding="utf-8",
        )
        item["stakeholder_execution"] = {
            "status": "passed",
            "scenario_id": item["id"],
            "sanitized": True,
            "evidence": [evidence_path.as_posix()],
        }
    for criterion in record["acceptance_criteria"]:
        criterion["status"] = "ci_gate" if criterion["id"] == "AC-08" else "accepted"
    return record


@pytest.fixture
def release_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    record = _record()
    references = {
        path
        for group, field in (
            ("dependencies", "evidence"),
            ("scenarios", "rehearsal_evidence"),
        )
        for item in record[group]
        for path in item[field]
    }
    for relative in references:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return root


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


def test_synthetic_fixture_with_all_gates_can_be_released(release_root: Path) -> None:
    result = pilot.validate(_synthetic_release_record(release_root), root=release_root)
    assert result["decision"] == "release"


def test_release_requires_both_signoffs(release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["signoffs"]["technical_owner"]["status"] = "pending"

    with pytest.raises(ValueError, match="approval"):
        pilot.validate(record, root=release_root)


def test_release_requires_every_required_scenario_to_pass(release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["scenarios"][0]["stakeholder_execution"] = {"status": "pending"}

    with pytest.raises(ValueError, match="required scenario not passed: S-01"):
        pilot.validate(record, root=release_root)


def test_an_optional_scenario_may_stay_pending(release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["scenarios"][-1]["stakeholder_execution"] = {"status": "pending"}

    assert pilot.validate(record, root=release_root)["decision"] == "release"


def test_required_scenario_cannot_be_removed(release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["scenarios"].pop()

    with pytest.raises(ValueError, match="exactly S-01 through S-12"):
        pilot.validate(record, root=release_root)


def test_core_scenario_cannot_be_made_optional(release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["scenarios"][0]["required"] = False

    with pytest.raises(ValueError, match="S-01 through S-11 must remain required"):
        pilot.validate(record, root=release_root)


def test_included_smtp_failure_requires_limited_release(release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["preconditions"][-1]["smtp"] = "included"
    record["scenarios"][-1]["required"] = True
    record["scenarios"][-1]["stakeholder_execution"]["status"] = "failed"
    execution_path = release_root / "docs/evidence/stage-6/S-12.json"
    execution_path.write_text(
        json.dumps(_execution_evidence("S-12", "failed")), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="required scenario not passed"):
        pilot.validate(record, root=release_root)

    record["decision"]["pilot"] = "release_with_limitations"
    record["limitations"] = [
        {
            "id": "L-1",
            "state": "accepted",
            "owner": "product",
            "deadline": "before-scale-up",
            "scenarios": ["S-12"],
        }
    ]
    result = pilot.validate(record, root=release_root)
    assert result["decision"] == "release_with_limitations"


def test_non_smtp_required_failure_cannot_be_accepted_as_limitation(
    release_root: Path,
) -> None:
    record = _synthetic_release_record(release_root, "release_with_limitations")
    record["limitations"] = [
        {"id": "L-1", "state": "accepted", "owner": "product", "deadline": "x"}
    ]
    record["scenarios"][0]["stakeholder_execution"]["status"] = "failed"
    execution = release_root / "docs/evidence/stage-6/S-01.json"
    execution.write_text(
        json.dumps(_execution_evidence("S-01", "failed")), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="S-01"):
        pilot.validate(record, root=release_root)


def test_release_rejects_pending_acceptance_criteria(release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["acceptance_criteria"][0]["status"] = "pending"

    with pytest.raises(ValueError, match="AC-01–AC-07 and AC-09 accepted"):
        pilot.validate(record, root=release_root)


@pytest.mark.parametrize("status", ["blocked", "rehearsed", "pending"])
def test_release_rejects_unaccepted_criteria(status: str, release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["acceptance_criteria"][0]["status"] = status

    with pytest.raises(ValueError, match="AC-01–AC-07 and AC-09 accepted"):
        pilot.validate(record, root=release_root)


@pytest.mark.parametrize(
    ("criterion_id", "status"),
    [("AC-08", "accepted"), ("AC-01", "ci_gate")],
)
def test_release_requires_criterion_specific_statuses(
    criterion_id: str, status: str, release_root: Path
) -> None:
    record = _synthetic_release_record(release_root)
    criterion = next(
        item for item in record["acceptance_criteria"] if item["id"] == criterion_id
    )
    criterion["status"] = status

    with pytest.raises(ValueError, match="AC-01–AC-07 and AC-09 accepted"):
        pilot.validate(record, root=release_root)


def test_release_requires_every_precondition_ready(release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["preconditions"][0]["state"] = "pending"

    with pytest.raises(ValueError, match="precondition"):
        pilot.validate(record, root=release_root)


@pytest.mark.parametrize("severity", ["critical", "high"])
def test_open_critical_or_high_defects_block_release(
    severity, release_root: Path
) -> None:
    record = _synthetic_release_record(release_root)
    record["defects"] = [{"id": "D-1", "severity": severity, "state": "open"}]

    with pytest.raises(ValueError, match=f"untreated {severity} defect"):
        pilot.validate(record, root=release_root)


def test_treated_defects_need_an_owner(release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["defects"] = [{"id": "D-1", "severity": "high", "state": "treated"}]

    with pytest.raises(ValueError, match="no owner"):
        pilot.validate(record, root=release_root)


def test_release_with_limitations_requires_registered_limitations(
    release_root: Path,
) -> None:
    with pytest.raises(ValueError, match="requires registered limitations"):
        pilot.validate(
            _synthetic_release_record(release_root, "release_with_limitations"),
            root=release_root,
        )

    record = _synthetic_release_record(release_root, "release_with_limitations")
    record["limitations"] = [
        {
            "id": "L-1",
            "state": "open",
            "owner": "platform",
            "deadline": "before_scale_up",
        }
    ]
    result = pilot.validate(record, root=release_root)
    assert result["decision"] == "release_with_limitations"


def test_plain_release_cannot_carry_limitations(release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["limitations"] = [
        {"id": "L-1", "state": "open", "owner": "platform", "deadline": "d"}
    ]

    with pytest.raises(ValueError, match="own decision"):
        pilot.validate(record, root=release_root)


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
        "scenario_id": "S-01",
        "sanitized": True,
        "evidence": ["docs/evidence/stage-6/S-01.json"],
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


@pytest.mark.parametrize(
    "field",
    [
        "password",
        "token",
        "email",
        "secret",
        "smtp_password",
        "access_token",
        "refresh_token",
        "user_email",
    ],
)
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


def test_duplicate_dependencies_are_rejected() -> None:
    record = _record()
    record["dependencies"].append(copy.deepcopy(record["dependencies"][0]))

    with pytest.raises(
        ValueError, match="dependency identifiers must be present and unique"
    ):
        pilot.validate(record)


def test_duplicate_acceptance_criteria_are_rejected() -> None:
    record = _record()
    record["acceptance_criteria"].append(
        copy.deepcopy(record["acceptance_criteria"][0])
    )

    with pytest.raises(
        ValueError, match="acceptance criterion identifiers must be present and unique"
    ):
        pilot.validate(record)


def test_execution_evidence_must_match_and_belong_to_scenario(
    release_root: Path,
) -> None:
    record = _synthetic_release_record(release_root)
    other_evidence = release_root / "docs/evidence/stage-6/S-02.json"
    other_evidence.write_text(
        json.dumps(_execution_evidence("S-02", "passed")),
        encoding="utf-8",
    )
    record["scenarios"][0]["stakeholder_execution"]["evidence"] = [
        "docs/evidence/stage-6/S-02.json"
    ]

    with pytest.raises(ValueError, match="dedicated record"):
        pilot.validate(record, root=release_root)


@pytest.mark.parametrize(
    "observation",
    ["Contact user@example.test", "password=example"],
)
def test_execution_evidence_rejects_unsanitized_observations(
    observation: str, release_root: Path
) -> None:
    record = _synthetic_release_record(release_root)
    evidence_path = release_root / "docs/evidence/stage-6/S-01.json"
    evidence = _execution_evidence("S-01", "passed")
    evidence["observations"] = [observation]
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ValueError, match="observations must be sanitized"):
        pilot.validate(record, root=release_root)


def test_execution_evidence_must_be_in_evidence_directory(release_root: Path) -> None:
    record = _synthetic_release_record(release_root)
    record["scenarios"][0]["stakeholder_execution"]["evidence"] = ["README.md"]

    with pytest.raises(ValueError, match="under docs/evidence"):
        pilot.validate(record, root=release_root)


@pytest.mark.parametrize(
    "collection", ["preconditions", "dependencies", "scenarios", "acceptance_criteria"]
)
@pytest.mark.parametrize("mutation", ["empty", "missing", "duplicate", "unknown"])
def test_review_collection_contract(collection, mutation, release_root):
    record = _synthetic_release_record(release_root)
    items = record[collection]
    if mutation == "empty":
        items.clear()
    elif mutation == "missing":
        items.pop()
    elif mutation == "duplicate":
        items.append(copy.deepcopy(items[0]))
    else:
        key = "issue" if collection == "dependencies" else "id"
        items[0][key] = 999 if key == "issue" else "UNKNOWN"
    with pytest.raises(ValueError):
        pilot.validate(record, root=release_root)


@pytest.mark.parametrize("scenario_index", range(11))
def test_every_core_scenario_remains_required(scenario_index, release_root):
    record = _synthetic_release_record(release_root)
    record["scenarios"][scenario_index]["required"] = False
    with pytest.raises(ValueError, match="must remain required"):
        pilot.validate(record, root=release_root)


@pytest.mark.parametrize("outcome", ["release", "release_with_limitations"])
@pytest.mark.parametrize("scenario_index", range(11))
def test_core_failure_blocks_both_release_decisions(
    outcome, scenario_index, release_root
):
    record = _synthetic_release_record(release_root, outcome)
    record["limitations"] = [
        {"id": "L-1", "state": "accepted", "owner": "platform", "deadline": "later"}
    ]
    scenario = record["scenarios"][scenario_index]
    scenario["stakeholder_execution"]["status"] = "failed"
    path = release_root / scenario["stakeholder_execution"]["evidence"][0]
    path.write_text(json.dumps(_execution_evidence(scenario["id"], "failed")))
    with pytest.raises(ValueError, match="required scenario not passed"):
        pilot.validate(record, root=release_root)


@pytest.mark.parametrize("criterion_index", range(9))
@pytest.mark.parametrize("state", ["pending", "blocked", "rehearsed"])
def test_every_unresolved_criterion_blocks_release(
    criterion_index, state, release_root
):
    record = _synthetic_release_record(release_root)
    record["acceptance_criteria"][criterion_index]["status"] = state
    with pytest.raises(ValueError, match="AC-01"):
        pilot.validate(record, root=release_root)


@pytest.mark.parametrize(
    "field",
    [
        "preconditions",
        "dependencies",
        "scenarios",
        "acceptance_criteria",
        "defects",
        "limitations",
        "signoffs",
        "decision",
    ],
)
@pytest.mark.parametrize("value", [None, "invalid", 1, True])
def test_malformed_collections_are_rejected_clearly(field, value):
    record = _record()
    record[field] = value
    with pytest.raises(ValueError):
        pilot.validate(record)


@pytest.mark.parametrize(
    "field",
    [
        "preconditions",
        "dependencies",
        "scenarios",
        "acceptance_criteria",
        "defects",
        "limitations",
    ],
)
def test_malformed_collection_members_are_rejected_clearly(field):
    record = _record()
    record[field] = [None]
    with pytest.raises(ValueError):
        pilot.validate(record)


@pytest.mark.parametrize("state", ["pending", "rejected"])
@pytest.mark.parametrize("role", ["product_owner", "technical_owner"])
def test_each_signoff_is_required(role, state, release_root):
    record = _synthetic_release_record(release_root)
    record["signoffs"][role]["status"] = state
    with pytest.raises(ValueError, match="approval"):
        pilot.validate(record, root=release_root)


@pytest.mark.parametrize("smtp", ["included", "excluded"])
@pytest.mark.parametrize("state", ["pending", "passed", "failed"])
@pytest.mark.parametrize("outcome", ["release", "release_with_limitations"])
def test_smtp_release_matrix(smtp, state, outcome, release_root):
    record = _synthetic_release_record(release_root, outcome)
    record["preconditions"][-1]["smtp"] = smtp
    scenario = record["scenarios"][-1]
    scenario["required"] = smtp == "included"
    scenario["stakeholder_execution"]["status"] = state
    if state != "pending":
        path = release_root / scenario["stakeholder_execution"]["evidence"][0]
        path.write_text(json.dumps(_execution_evidence("S-12", state)))
    if outcome == "release_with_limitations":
        record["limitations"] = [
            {
                "id": "L-1",
                "state": "accepted",
                "owner": "platform",
                "deadline": "before-scale-up",
                "scenarios": ["S-12"],
            }
        ]
    allowed = (state != "failed" if smtp == "excluded" else state == "passed") or (
        smtp == "included"
        and state == "failed"
        and outcome == "release_with_limitations"
    )
    if allowed:
        assert pilot.validate(record, root=release_root)["decision"] == outcome
    else:
        with pytest.raises(ValueError):
            pilot.validate(record, root=release_root)


@pytest.mark.parametrize("limitation_state", ["open", "accepted"])
@pytest.mark.parametrize("linked_scenarios", [[], ["S-01"], ["S-12"]])
def test_smtp_exception_needs_accepted_related_limitation(
    limitation_state, linked_scenarios, release_root
):
    record = _synthetic_release_record(release_root, "release_with_limitations")
    record["preconditions"][-1]["smtp"] = "included"
    scenario = record["scenarios"][-1]
    scenario["required"] = True
    scenario["stakeholder_execution"]["status"] = "failed"
    path = release_root / scenario["stakeholder_execution"]["evidence"][0]
    path.write_text(json.dumps(_execution_evidence("S-12", "failed")))
    record["limitations"] = [
        {
            "id": "L-1",
            "state": limitation_state,
            "scenarios": linked_scenarios,
            "owner": "platform",
            "deadline": "before-scale-up",
        }
    ]
    if limitation_state == "accepted" and linked_scenarios == ["S-12"]:
        assert (
            pilot.validate(record, root=release_root)["decision"]
            == "release_with_limitations"
        )
    else:
        with pytest.raises(ValueError, match="accepted limitation linked to S-12"):
            pilot.validate(record, root=release_root)
