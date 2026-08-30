from __future__ import annotations

from copy import deepcopy

import pytest

from app.processing import ProcessingError, process_normalized_records

EXECUTION_ID = "exec-processing"
CLASSIFIED_AT = "2026-08-28T12:00:00+00:00"


def record(
    source: str,
    row: int,
    values: dict,
    *,
    execution_id: str = EXECUTION_ID,
) -> dict:
    return {
        "source": source,
        "execution_id": execution_id,
        "source_file_id": row,
        "sheet": source,
        "row": row,
        "values": values,
        "original_values": deepcopy(values),
        "transformations": [],
    }


def process(records: list[dict]) -> dict:
    return process_normalized_records(
        records,
        execution_id=EXECUTION_ID,
        classified_at=CLASSIFIED_AT,
    )


def classifications(result: dict, rule_id: str) -> list[dict]:
    return [
        item
        for item in result["classifications"]["current_classifications"]
        if item["rule_id"] == rule_id
    ]


def test_consolidates_single_source_with_traceable_fields() -> None:
    result = process(
        [
            record(
                "N-FP",
                2,
                {
                    "workorder_number": "WO-1",
                    "lot_number": "LOT-1",
                    "serial_number": "SER-1",
                    "organization_code": "ORG-1",
                    "planned_quantity": 10,
                },
            )
        ]
    )

    workorder = result["consolidation"]["workorders"][0]
    assert result["summary"]["consolidated_workorders"] == 1
    assert result["summary"]["consolidated_lots"] == 1
    assert result["summary"]["consolidated_serials"] == 1
    assert result["summary"]["consolidated_organizations"] == 1
    assert workorder["released_quantity"] is None
    assert workorder["pending_quantity"] is None
    assert workorder["provenance"]["planned_quantity"][0] == {
        "source": "N-FP",
        "execution_id": EXECUTION_ID,
        "source_file_id": 2,
        "sheet": "N-FP",
        "row": 2,
        "field": "planned_quantity",
        "value": 10,
    }


def test_consolidates_concordant_sources_and_preserves_partial_release() -> None:
    result = process(
        [
            record(
                "N-FP",
                2,
                {"workorder_number": "WO-1", "planned_quantity": 10},
            ),
            record(
                "GMES/OQC",
                3,
                {"workorder_number": "WO-1", "planned_quantity": 10},
            ),
            record(
                "OWM",
                4,
                {
                    "workorder_number": "WO-1",
                    "received_quantity": 10,
                    "released_quantity": 6,
                },
            ),
        ]
    )

    workorder = result["consolidation"]["workorders"][0]
    assert workorder["planned_quantity"] == 10
    assert workorder["released_quantity"] == 6
    assert workorder["pending_quantity"] == 4
    assert workorder["partially_released"] is True
    assert not any(
        issue["code"] == "source_divergence"
        for issue in result["consolidation"]["issues"]
    )


def test_divergent_sources_generate_auditable_classification() -> None:
    result = process(
        [
            record("N-FP", 2, {"workorder_number": "WO-1", "planned_quantity": 10}),
            record(
                "GMES/OQC",
                3,
                {"workorder_number": "WO-1", "planned_quantity": 12},
            ),
        ]
    )

    workorder = result["consolidation"]["workorders"][0]
    divergence = classifications(result, "source_divergence")[0]
    assert workorder["planned_quantity"] == 10
    assert workorder["selected_quantity_sources"]["planned_quantity"] == "N-FP"
    assert divergence["rule_catalog_version"] == "1.0.0"
    assert divergence["evidence"]["values_by_source"] == {
        "N-FP": 10,
        "GMES/OQC": 12,
    }


def test_rules_distinguish_hold_before_and_after_release() -> None:
    result = process(
        [
            record(
                "OWM",
                2,
                {
                    "workorder_number": "WO-1",
                    "serial_number": "SER-BEFORE",
                    "status": "hold",
                    "reason": "before",
                    "created_at": "2026-08-01",
                    "released_at": "2026-08-10",
                    "released_quantity": 1,
                    "received_quantity": 2,
                },
            ),
            record(
                "OWM",
                3,
                {
                    "workorder_number": "WO-1",
                    "serial_number": "SER-AFTER",
                    "status": "hold",
                    "reason": "after",
                    "created_at": "2026-08-20",
                },
            ),
        ]
    )

    assert {item["entity_id"] for item in classifications(result, "oqc_hold")} == {
        "SER-AFTER",
        "SER-BEFORE",
    }
    assert {
        item["entity_id"] for item in classifications(result, "pre_release_pending")
    } == {"SER-BEFORE"}
    assert {
        item["entity_id"] for item in classifications(result, "post_release_hold")
    } == {"SER-AFTER"}


def test_unknown_state_records_rule_evaluations_without_inventing_a_result() -> None:
    result = process(
        [record("GMES/OQC", 2, {"workorder_number": "WO-1", "status": "unknown"})]
    )

    assert result["classifications"]["current_classifications"] == []
    evaluations = result["classifications"]["rule_evaluations"]
    assert evaluations
    assert all(item["rule_catalog_version"] == "1.0.0" for item in evaluations)
    assert all(item["result"] == "not_matched" for item in evaluations)


def test_local_failure_does_not_stop_an_independent_workorder() -> None:
    result = process(
        [
            record(
                "N-FP",
                2,
                {"workorder_number": "WO-BAD", "planned_quantity": "1.5"},
            ),
            record(
                "N-FP",
                3,
                {"workorder_number": "WO-GOOD", "planned_quantity": 2},
            ),
        ]
    )

    assert [
        item["workorder_number"] for item in result["consolidation"]["workorders"]
    ] == ["WO-GOOD"]
    assert result["summary"]["failed_workorders"] == 1
    assert (
        result["consolidation"]["failed_workorders"][0]["workorder_number"] == "WO-BAD"
    )


def test_local_rule_failure_does_not_stop_an_independent_workorder() -> None:
    result = process(
        [
            record(
                "GMES/OQC",
                2,
                {
                    "workorder_number": "WO-BAD",
                    "status": "pending",
                    "created_at": "not-a-date",
                },
            ),
            record(
                "GMES/OQC",
                3,
                {
                    "workorder_number": "WO-GOOD",
                    "status": "pending",
                    "created_at": "2026-08-20",
                },
            ),
        ]
    )

    assert [
        item["workorder_number"] for item in result["consolidation"]["workorders"]
    ] == ["WO-GOOD"]
    assert result["summary"]["failed_workorders"] == 1
    assert result["consolidation"]["failed_workorders"][0]["stage"] == (
        "classification"
    )
    assert classifications(result, "oqc_pending")[0]["workorder_number"] == ("WO-GOOD")


def test_processing_is_deterministic_for_same_input_and_catalog() -> None:
    records = [
        record(
            "GMES/OQC",
            2,
            {
                "workorder_number": "WO-1",
                "serial_number": "SER-1",
                "status": "pending",
                "reason": "inspection",
            },
        ),
        record("N-FP", 3, {"workorder_number": "WO-1", "planned_quantity": 1}),
    ]

    assert process(records) == process(list(reversed(records)))


def test_rejects_records_from_another_execution() -> None:
    with pytest.raises(ProcessingError, match="execução atual"):
        process(
            [
                record(
                    "N-FP",
                    2,
                    {"workorder_number": "WO-1"},
                    execution_id="exec-other",
                )
            ]
        )
