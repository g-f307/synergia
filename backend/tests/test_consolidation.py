from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.consolidation import ConsolidationError, compare_with_reference, consolidate

ROOT = Path(__file__).resolve().parents[2]
RECORDS_PATH = ROOT / "data" / "synthetic" / "consolidation_records.json"
REFERENCE_PATH = ROOT / "data" / "synthetic" / "wo-status-reference.csv"


@pytest.fixture
def records() -> list[dict]:
    return json.loads(RECORDS_PATH.read_text(encoding="utf-8"))


def by_workorder(result: dict) -> dict[str, dict]:
    return {row["workorder_number"]: row for row in result["workorders"]}


def test_consolidates_complete_partial_and_missing_matches(records) -> None:
    result = consolidate(records)
    workorders = by_workorder(result)

    assert result["workorder_count"] == 4
    assert len(workorders) == result["workorder_count"]
    assert workorders["WO-NORMAL-001"]["status"] == "complete"
    assert workorders["WO-PQ-002"]["status"] == "incomplete"
    assert workorders["WO-PQ-002"]["missing_sources"] == [
        "GMES/OQC",
        "OWM",
        "TMS",
    ]
    assert workorders["WO-SERIAL-004"]["serial_numbers"] == ["SER-SEM-WO"]
    assert workorders["WO-SERIAL-004"]["status"] == "incomplete"
    assert result["unmatched_record_count"] == 0


def test_preserves_partial_release_holds_relationships_and_provenance(records) -> None:
    workorder = by_workorder(consolidate(records))["WO-PM-003"]

    assert workorder["workorder_types"] == ["PM"]
    assert workorder["planned_quantity"] == 10
    assert workorder["produced_quantity"] == 8
    assert workorder["received_quantity"] == 8
    assert workorder["released_quantity"] == 6
    assert workorder["pending_quantity"] == 4
    assert workorder["retained_quantity"] == 1
    assert workorder["partially_released"] is True
    assert workorder["container_numbers"] == ["CONT-PM-001"]
    assert workorder["serial_numbers"] == ["SER-PM-001", "SER-PM-002"]
    assert workorder["organization_codes"] == ["ORG-001", "ORG-002"]
    assert workorder["selected_quantity_sources"]["released_quantity"] == "OWM"
    assert workorder["calculations"]["pending_quantity"]["inputs"] == {
        "explicit_pending": 0,
        "planned_quantity": 10,
        "released_quantity": 6,
    }
    assert workorder["provenance"]["released_quantity"] == [
        {
            "source": "OWM",
            "execution_id": "exec-receiving",
            "source_file_id": 3,
            "sheet": "Receiving",
            "row": 3,
            "field": "released_quantity",
            "value": 6,
        }
    ]


def test_records_lot_and_organization_divergences(records) -> None:
    issues = consolidate(records)["issues"]

    assert any(
        issue["code"] == "relationship_divergence"
        and issue["field"] == "lot_number"
        and issue["serial_number"] == "SER-PM-001"
        for issue in issues
    )
    assert any(
        issue["code"] == "source_divergence"
        and issue["field"] == "organization_code"
        for issue in issues
    )


def test_result_is_reproducible_independent_of_source_order(records) -> None:
    assert consolidate(records) == consolidate(reversed(records))


def test_ignores_same_normalized_record_without_duplicating_quantities(records) -> None:
    result = consolidate([*records, records[0]])

    assert result["duplicate_record_count"] == 1
    assert by_workorder(result)["WO-NORMAL-001"]["planned_quantity"] == 10
    assert any(
        issue["code"] == "duplicate_record_ignored" for issue in result["issues"]
    )


def test_compares_result_with_wo_status_reference(records) -> None:
    with REFERENCE_PATH.open(encoding="utf-8", newline="") as stream:
        reference = list(csv.DictReader(stream))

    comparison = compare_with_reference(consolidate(records), reference)

    assert comparison == {
        "matches": True,
        "compared_workorder_count": 4,
        "difference_count": 0,
        "differences": [],
    }


def test_rejects_invalid_quantities_with_field_context() -> None:
    records = [
        {
            "source": "N-FP",
            "sheet": "CSV",
            "row": 2,
            "values": {
                "workorder_number": "WO-BAD",
                "planned_quantity": "10.5",
            },
        }
    ]

    with pytest.raises(ConsolidationError, match="planned_quantity"):
        consolidate(records)


def test_registers_record_without_any_resolvable_relationship() -> None:
    result = consolidate(
        [
            {
                "source": "TMS",
                "execution_id": "exec-orphan",
                "source_file_id": 9,
                "sheet": "Shipping",
                "row": 2,
                "values": {"serial_number": "SER-ORPHAN"},
            }
        ]
    )

    assert result["workorder_count"] == 0
    assert result["unmatched_record_count"] == 1
    assert result["issues"][0]["code"] == "unmatched_record"
