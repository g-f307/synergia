from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.business_rules import (
    REQUIRED_RULES,
    BusinessRuleError,
    classify,
    load_rule_catalog,
)

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_PATH = ROOT / "data" / "synthetic" / "rules_scenarios.json"
CLASSIFIED_AT = "2026-08-27T12:00:00+00:00"


@pytest.fixture
def scenarios() -> dict:
    return json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def result(scenarios) -> dict:
    return classify(scenarios, run_id="rules-run-1", classified_at=CLASSIFIED_AT)


def events(result: dict, rule_id: str) -> list[dict]:
    return [
        event
        for event in result["current_classifications"]
        if event["rule_id"] == rule_id
    ]


def test_catalog_is_versioned_and_contains_every_required_rule() -> None:
    catalog = load_rule_catalog()

    assert catalog["version"] == "1.0.0"
    assert REQUIRED_RULES <= catalog["rules"].keys()


def test_rejects_incomplete_rule_catalog(tmp_path) -> None:
    path = tmp_path / "incomplete-rules.json"
    path.write_text(
        json.dumps({"version": "invalid", "thresholds": {}, "rules": {}}),
        encoding="utf-8",
    )

    with pytest.raises(BusinessRuleError, match="Regras obrigatórias ausentes"):
        load_rule_catalog(path)


@pytest.mark.parametrize("rule_id", sorted(REQUIRED_RULES))
def test_each_catalog_rule_has_an_automated_synthetic_scenario(
    result, rule_id: str
) -> None:
    assert events(result, rule_id), f"Regra sem cenário automatizado: {rule_id}"


def test_hold_long_term_rework_and_ship_block_remain_distinct(result) -> None:
    serial_rules = {
        event["entity_id"]: set()
        for event in result["current_classifications"]
        if event["entity_type"] == "serial"
    }
    for event in result["current_classifications"]:
        if event["entity_type"] == "serial":
            serial_rules[event["entity_id"]].add(event["rule_id"])

    assert {"oqc_hold", "long_term_hold"} <= serial_rules["SER-HOLD"]
    assert "rework" in serial_rules["SER-REWORK"]
    assert "ship_block" in serial_rules["SER-BLOCK"]
    assert "rework" not in serial_rules["SER-BLOCK"]
    assert "ship_block" not in serial_rules["SER-REWORK"]


def test_pre_release_pending_and_post_release_hold_remain_distinct(result) -> None:
    pre = events(result, "pre_release_pending")
    post = events(result, "post_release_hold")

    assert any(event["workorder_number"] == "WO-PRE-002" for event in pre)
    assert any(event["entity_id"] == "SER-HOLD" for event in post)
    assert not any(event["workorder_number"] == "WO-PRE-002" for event in post)


def test_uses_release_date_to_distinguish_pre_and_post_release() -> None:
    scenario = {
        "workorders": [
            {
                "workorder_number": "WO-DATES",
                "released_quantity": 1,
                "classification_facts": [
                    {
                        "source": "OWM",
                        "sheet": "Holds",
                        "row": 2,
                        "status": "hold",
                        "reason": "Before release",
                        "created_at": "2026-08-01",
                        "released_at": "2026-08-10",
                    },
                    {
                        "source": "OWM",
                        "sheet": "Holds",
                        "row": 3,
                        "status": "hold",
                        "reason": "After release",
                        "created_at": "2026-08-20",
                    },
                ],
            }
        ]
    }

    result = classify(scenario, run_id="date-run", classified_at=CLASSIFIED_AT)

    assert {event["reason"] for event in events(result, "pre_release_pending")} == {
        "Before release"
    }
    assert {event["reason"] for event in events(result, "post_release_hold")} == {
        "After release"
    }


def test_missing_reason_is_partial_and_partial_release_is_preserved(result) -> None:
    missing = next(
        event
        for event in events(result, "missing_reason")
        if event["entity_id"] == "SER-BLOCK"
    )
    hold = next(
        event
        for event in events(result, "oqc_hold")
        if event["entity_id"] == "SER-HOLD"
    )

    assert missing["data_quality"] == "partial"
    assert missing["reason"] is None
    assert hold["partially_released"] is True
    assert hold["state"] == "active"


def test_active_queue_is_separate_from_closed_history_and_sorted_by_age(result) -> None:
    active_ids = {
        classification_id
        for item in result["active_items"]
        for classification_id in item["classification_ids"]
    }
    closed_hold = next(
        event
        for event in events(result, "oqc_hold")
        if event["entity_id"] == "SER-CLOSED"
    )
    occurred = [item["occurred_at"] for item in result["active_items"]]
    known_dates = [value for value in occurred if value is not None]

    assert closed_hold["state"] == "closed"
    assert closed_hold["classification_id"] not in active_ids
    assert closed_hold in result["history"]
    assert known_dates == sorted(known_dates)


def test_active_queue_groups_simultaneous_categories_by_entity(result) -> None:
    hold = next(
        item for item in result["active_items"] if item["entity_id"] == "SER-HOLD"
    )

    assert {
        "aging",
        "container_impact",
        "long_term_hold",
        "oqc_hold",
        "post_release_hold",
    } <= set(hold["rule_ids"])
    assert hold["primary_rule_id"] == "long_term_hold"


def test_classifies_workorder_lot_and_serial_hierarchy(result) -> None:
    entities = {
        (item["workorder_number"], item["entity_type"], item["entity_id"]): item
        for item in result["entities"]
    }

    assert entities[("WO-RULES-001", "workorder", "WO-RULES-001")]["state"] == (
        "active"
    )
    assert entities[("WO-RULES-001", "lot", "LOT-001")]["state"] == "active"
    assert entities[("WO-RULES-001", "serial", "SER-PASS")]["state"] == "closed"


def test_identifies_area_organization_priority_and_applied_rule(result) -> None:
    ship_block = next(
        event
        for event in events(result, "ship_block")
        if event["entity_id"] == "SER-BLOCK"
    )
    divergent = next(
        event
        for event in events(result, "source_divergence")
        if event["workorder_number"] == "WO-ORG-003"
    )

    assert ship_block["responsible_area"] == "Logística"
    assert ship_block["responsible_organization"] == "ORG-001"
    assert ship_block["priority"] == "critical"
    assert ship_block["priority_score"] == 105
    assert ship_block["rule_catalog_version"] == "1.0.0"
    assert ship_block["rule_description"]
    assert divergent["responsible_organization"] is None
    assert result["divergence_report"][0]["code"] == "source_divergence"


def test_container_impact_counts_only_affected_serials(result) -> None:
    impact = next(
        event
        for event in events(result, "container_impact")
        if event["entity_id"] == "SER-HOLD"
    )["container_impact"]

    assert impact == {
        "serial_count": 2,
        "affected_serial_count": 1,
        "partially_affected": True,
    }


def test_reprocessing_appends_history_without_mutating_previous_evidence(
    scenarios, result
) -> None:
    prior_history = deepcopy(result["history"])

    reprocessed = classify(
        scenarios,
        run_id="rules-run-2",
        classified_at="2026-08-28T12:00:00+00:00",
        previous_history=prior_history,
    )

    assert prior_history == result["history"]
    assert len(reprocessed["history"]) == len(prior_history) + len(
        reprocessed["current_classifications"]
    )
    assert {item["run_id"] for item in reprocessed["history"]} == {
        "rules-run-1",
        "rules-run-2",
    }
    assert not (
        {item["classification_id"] for item in prior_history}
        & {
            item["classification_id"]
            for item in reprocessed["current_classifications"]
        }
    )


def test_classification_is_deterministic_for_the_same_input(scenarios) -> None:
    first = classify(scenarios, run_id="same-run", classified_at=CLASSIFIED_AT)
    reversed_input = deepcopy(scenarios)
    reversed_input["workorders"].reverse()
    for workorder in reversed_input["workorders"]:
        workorder["classification_facts"].reverse()

    assert first == classify(
        reversed_input,
        run_id="same-run",
        classified_at=CLASSIFIED_AT,
    )
