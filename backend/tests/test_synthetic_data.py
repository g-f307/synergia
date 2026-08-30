from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_synthetic_data import (  # noqa: E402
    CANONICAL_FORMATS,
    PROFILES,
    SOURCES,
    build_dataset,
    generate_bundle,
    validate_manifest,
)

from app.execution import validate_transition  # noqa: E402
from app.pipeline import read_source, run_pipeline_batch  # noqa: E402
from app.validation import validate_tables  # noqa: E402

FIXTURES = ROOT / "data" / "synthetic" / "fixtures"


class RecordingRepository:
    def __init__(self) -> None:
        self.state = "pending"
        self.result: dict | None = None

    def transition_execution(self, execution_id: str, target: str, reason: str) -> None:
        validate_transition(self.state, target)
        self.state = target

    def commit_pipeline(self, execution_id: str, result: dict) -> None:
        self.result = result
        self.transition_execution(execution_id, result["status"], result["status"])


def _file_map(directory: Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def _pipeline_from_bundle(directory: Path) -> tuple[dict, dict]:
    manifest = validate_manifest(directory / "manifest.json")
    files = {
        item["source"]: item
        for item in manifest["files"]
        if item["format"] == CANONICAL_FORMATS[item["source"]]
    }
    inputs = []
    for source_file_id, source in enumerate(SOURCES, 1):
        item = files[source]
        path = directory / item["file"]
        tables, read_issues = read_source(path, path.suffix, source)
        inputs.append(
            {
                "file_name": path.name,
                "source": source,
                "source_file_id": source_file_id,
                "tables": tables,
                "read_issues": read_issues,
            }
        )
    repository = RecordingRepository()
    result = run_pipeline_batch(
        execution_id="exec-synthetic",
        inputs=inputs,
        repository=repository,
        classified_at="2026-08-30T12:00:00+00:00",
        known_organizations=set(manifest["expectations"]["known_organizations"]),
    )
    assert repository.result is result
    return result, manifest


def test_same_seed_produces_identical_logical_and_physical_bundle(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_manifest = generate_bundle(
        output=first,
        profile_name="minimal",
        seed=271828,
        scenario="valid",
    )
    second_manifest = generate_bundle(
        output=second,
        profile_name="minimal",
        seed=271828,
        scenario="valid",
    )

    assert first_manifest == second_manifest
    assert _file_map(first) == _file_map(second)


def test_different_seeds_change_the_logical_dataset(tmp_path) -> None:
    first = generate_bundle(
        output=tmp_path / "seed-1",
        profile_name="minimal",
        seed=1,
        scenario="valid",
    )
    second = generate_bundle(
        output=tmp_path / "seed-2",
        profile_name="minimal",
        seed=2,
        scenario="valid",
    )

    assert first["logical_digest"] != second["logical_digest"]


def test_manifest_totals_and_all_formats_are_verifiable(tmp_path) -> None:
    manifest = generate_bundle(
        output=tmp_path / "all-formats",
        profile_name="minimal",
        seed=20260830,
        scenario="valid",
        formats="all",
    )

    assert len(manifest["files"]) == len(SOURCES) * 3
    assert {item["format"] for item in manifest["files"]} == {
        "csv",
        "json",
        "xlsx",
    }
    for source in SOURCES:
        source_files = [item for item in manifest["files"] if item["source"] == source]
        assert {item["records"] for item in source_files} == {
            manifest["sources"][source]["records"]
        }
    assert validate_manifest(tmp_path / "all-formats" / "manifest.json") == manifest


@pytest.mark.parametrize("profile_name", PROFILES)
def test_hierarchical_relations_are_consistent(profile_name) -> None:
    records, metadata = build_dataset(
        profile_name=profile_name,
        seed=314159,
        scenario="valid",
    )
    plans = {row["workorder_number"]: row for row in records["N-FP"]}
    serials = set()
    for row in records["OWM"]:
        plan = plans[row["workorder_number"]]
        assert row["demand_id"] == plan["demand_id"]
        assert row["lot_number"] == plan["lot_number"]
        assert row["model"] == plan["model"]
        serials.add(row["serial_number"])
    for row in records["GMES/OQC"]:
        plan = plans[row["workorder_number"]]
        assert row["demand_id"] == plan["demand_id"]
        assert row["lot_number"] == plan["lot_number"]
        assert row["model"] == plan["model"]
    for row in records["TMS"]:
        plan = plans[row["workorder_number"]]
        assert row["demand_id"] == plan["demand_id"]
        assert row["lot_number"] == plan["lot_number"]
    assert len(plans) == metadata["entities"]["workorders"]
    assert len(serials) == metadata["entities"]["serials"]


def test_committed_small_fixture_imports_and_runs_end_to_end() -> None:
    result, manifest = _pipeline_from_bundle(FIXTURES / "minimal-valid")
    expected = manifest["expectations"]["valid_pipeline"]

    assert result["status"] == "completed"
    assert result["summary"] == {
        key: expected[key]
        for key in (
            "rows_read",
            "valid_records",
            "rejected_records",
            "normalized_records",
        )
    } | {"errors": 0, "warnings": 0}
    processing = result["processing"]
    assert (
        processing["summary"]["consolidated_workorders"]
        == expected["consolidated_workorders"]
    )
    assert processing["summary"]["consolidated_lots"] == expected["consolidated_lots"]
    assert (
        processing["summary"]["consolidated_serials"]
        == expected["consolidated_serials"]
    )
    assert all(
        item["status"] == "complete"
        for item in processing["consolidation"]["workorders"]
    )


def test_comprehensive_fixture_exposes_manifested_errors_and_scenarios() -> None:
    directory = FIXTURES / "minimal-comprehensive"
    manifest = validate_manifest(directory / "manifest.json")
    actual_codes: Counter[str] = Counter()
    for item in manifest["files"]:
        path = directory / item["file"]
        tables, read_issues = read_source(path, path.suffix, item["source"])
        report = validate_tables(
            tables,
            item["source"],
            set(manifest["expectations"]["known_organizations"]),
            read_issues,
        )
        actual_codes.update(issue["code"] for issue in report["issues"])
    for code, count in manifest["expectations"]["validation_issue_codes"].items():
        assert actual_codes[code] >= count

    result, _ = _pipeline_from_bundle(directory)
    processing_codes = Counter(
        issue["code"] for issue in result["processing"]["consolidation"]["issues"]
    )
    for code, count in manifest["expectations"]["processing_issue_codes"].items():
        assert processing_codes[code] >= count
    actual_rules = set(result["processing"]["summary"]["classifications_by_rule"])
    assert set(manifest["expectations"]["classification_rule_ids"]) <= actual_rules
    assert result["status"] == "completed_with_errors"


def test_reference_profile_generates_6800_workorders_and_88000_serials(
    tmp_path,
) -> None:
    manifest = generate_bundle(
        output=tmp_path / "reference",
        profile_name="reference",
        seed=20260830,
        scenario="valid",
    )

    assert manifest["entities"]["workorders"] == 6_800
    assert manifest["entities"]["lots"] == 6_800
    assert manifest["entities"]["serials"] == 88_000
    assert manifest["sources"]["N-FP"]["records"] == 6_800
    assert manifest["sources"]["OWM"]["records"] == 88_000
    assert manifest["sources"]["GMES/OQC"]["records"] == 88_000
    assert validate_manifest(tmp_path / "reference" / "manifest.json") == manifest


def test_manifest_contains_only_recognizably_synthetic_identifiers() -> None:
    records, _ = build_dataset(profile_name="small", seed=20260830, scenario="valid")

    identifiers = {
        str(value)
        for rows in records.values()
        for row in rows
        for field, value in row.items()
        if field.endswith("_number") or field.endswith("_id") or field.endswith("_code")
    }
    assert identifiers
    assert all(value.startswith("SYN-") for value in identifiers)
