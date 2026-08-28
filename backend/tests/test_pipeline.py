from pathlib import Path

import pytest
from openpyxl import Workbook

from app.pipeline import read_source, run_pipeline


class RecordingRepository:
    def __init__(self) -> None:
        self.commits: list[tuple[str, dict]] = []

    def commit_pipeline(self, execution_id: str, result: dict) -> None:
        self.commits.append((execution_id, result))


def run_csv(
    tmp_path: Path,
    content: str,
    *,
    source: str = "N-FP",
    organizations: set[str] | None = None,
) -> tuple[dict, RecordingRepository]:
    path = tmp_path / "input.csv"
    path.write_text(content, encoding="utf-8")
    repository = RecordingRepository()
    tables, read_issues = read_source(path, ".csv", source)
    result = run_pipeline(
        execution_id="exec-pipeline",
        file_name="input.csv",
        source=source,
        repository=repository,
        tables=tables,
        read_issues=read_issues,
        classified_at="2026-08-28T12:00:00+00:00",
        known_organizations=organizations,
    )
    return result, repository


def test_valid_file_runs_all_stages_and_preserves_traceability(tmp_path) -> None:
    result, repository = run_csv(
        tmp_path,
        "workorder,serial,planned_date,planned_quantity\n"
        "0000123,0000456,27/08/2026,10\n",
    )

    assert result["status"] == "completed"
    assert result["summary"] == {
        "rows_read": 1,
        "valid_records": 1,
        "rejected_records": 0,
        "normalized_records": 1,
        "errors": 0,
        "warnings": 0,
    }
    imported = result["imported_records"][0]
    normalized = result["normalized_records"][0]
    assert (imported["sheet"], imported["row"]) == (
        normalized["sheet"],
        normalized["row"],
    )
    assert normalized["values"]["workorder_number"] == "0000123"
    assert normalized["values"]["serial_number"] == "0000456"
    assert normalized["original_values"]["planned_date"] == "27/08/2026"
    assert normalized["values"]["planned_date"] == "2026-08-27"
    assert normalized["execution_id"] == "exec-pipeline"
    assert result["processing"]["summary"] == {
        "eligible_normalized_records": 1,
        "consolidated_workorders": 1,
        "consolidated_lots": 0,
        "consolidated_serials": 1,
        "consolidated_organizations": 0,
        "consolidation_issues": 1,
        "failed_workorders": 0,
        "classifications": 0,
        "active_pending_items": 0,
        "classifications_by_rule": {},
        "consolidated_quantities": {
            "planned_quantity": {"known_workorders": 1, "total": 10},
            "produced_quantity": {"known_workorders": 0, "total": None},
            "received_quantity": {"known_workorders": 0, "total": None},
            "released_quantity": {"known_workorders": 0, "total": None},
            "pending_quantity": {"known_workorders": 0, "total": None},
            "retained_quantity": {"known_workorders": 0, "total": None},
        },
    }
    assert len(repository.commits) == 1


def test_record_error_rejects_only_affected_line(tmp_path) -> None:
    result, _ = run_csv(
        tmp_path,
        "workorder,planned_quantity,planned_date\n"
        "WO-OK,10,2026-08-27\n"
        "WO-BAD,invalid,not-a-date\n"
        "WO-ALSO-OK,2,28/08/2026\n",
    )

    assert result["status"] == "completed"
    assert result["blocking"] is False
    assert result["summary"]["valid_records"] == 2
    assert result["summary"]["rejected_records"] == 1
    assert [record["row"] for record in result["normalized_records"]] == [2, 4]
    assert {
        item["workorder_number"]
        for item in result["processing"]["consolidation"]["workorders"]
    } == {"WO-OK", "WO-ALSO-OK"}
    assert {issue["scope"] for issue in result["issues"]} == {"record"}


@pytest.mark.parametrize(
    "content",
    ["status\nopen\n", "workorder\n", ""],
)
def test_structural_error_blocks_the_file(tmp_path, content) -> None:
    result, _ = run_csv(tmp_path, content)

    assert result["status"] == "validation_failed"
    assert result["blocking"] is True
    assert result["summary"]["normalized_records"] == 0
    assert any(issue["scope"] == "structure" for issue in result["issues"])


def test_required_field_and_unknown_organization_are_row_errors(tmp_path) -> None:
    result, _ = run_csv(
        tmp_path,
        "workorder,organization\n,KNOWN\nWO-2,UNKNOWN\nWO-3,KNOWN\n",
        organizations={"KNOWN"},
    )

    assert result["summary"]["rejected_records"] == 2
    assert result["summary"]["normalized_records"] == 1
    assert {issue["code"] for issue in result["issues"]} == {
        "required_field",
        "unknown_organization",
    }


def test_unknown_state_and_oqc_flag_are_non_blocking_warnings(tmp_path) -> None:
    result, _ = run_csv(
        tmp_path,
        "workorder,status,oqc_flag\nWO-1,new-state,perhaps\n",
        source="GMES/OQC",
    )

    assert result["summary"]["normalized_records"] == 1
    assert result["summary"]["warnings"] == 2
    assert all(issue["severity"] == "warning" for issue in result["issues"])


def test_unexpected_normalization_failure_does_not_commit(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "input.csv"
    path.write_text("workorder\nWO-1\n", encoding="utf-8")
    repository = RecordingRepository()
    tables, read_issues = read_source(path, ".csv", "N-FP")

    def fail_normalization(*_args, **_kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr("app.pipeline.normalize_tables", fail_normalization)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        run_pipeline(
            execution_id="exec-failure",
            file_name="input.csv",
            source="N-FP",
            repository=repository,
            tables=tables,
            read_issues=read_issues,
            classified_at="2026-08-28T12:00:00+00:00",
        )

    assert repository.commits == []


def test_artifact_failure_does_not_commit_pipeline(tmp_path) -> None:
    path = tmp_path / "input.csv"
    path.write_text("workorder\nWO-1\n", encoding="utf-8")
    tables, read_issues = read_source(path, ".csv", "N-FP")
    repository = RecordingRepository()

    def fail_artifacts(_result: dict) -> None:
        raise OSError("synthetic artifact failure")

    with pytest.raises(OSError, match="synthetic artifact failure"):
        run_pipeline(
            execution_id="exec-artifact-failure",
            file_name="input.csv",
            source="N-FP",
            repository=repository,
            tables=tables,
            read_issues=read_issues,
            classified_at="2026-08-28T12:00:00+00:00",
            prepare_commit=fail_artifacts,
        )

    assert repository.commits == []


def test_reads_xlsx_from_temporary_path_without_xlsx_suffix(tmp_path) -> None:
    path = tmp_path / "upload.upload"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["workorder", "status"])
    worksheet.append(["WO-1", "open"])
    workbook.save(path)
    workbook.close()

    tables, read_issues = read_source(path, ".xlsx", "N-FP")

    assert read_issues == []
    assert tables == [("Sheet", ["workorder", "status"], [["WO-1", "open"]])]
