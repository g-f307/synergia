from __future__ import annotations

import pytest
from openpyxl import Workbook

from app.validation import validate_file


def write_csv(tmp_path, content: str):
    path = tmp_path / "input.csv"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("content", "source", "codes"),
    [
        ("status\nopen\n", "N-FP", {"missing_column"}),
        ("workorder_number,planned_date\nWO-1,31/02/2026\n", "N-FP", {"invalid_date"}),
        ("workorder_number,planned_quantity\nWO-1,dez\n", "N-FP", {"invalid_quantity"}),
        ("workorder_number\n", "N-FP", {"empty_file"}),
        ("workorder_number\n\nWO-2\n", "N-FP", {"empty_row"}),
        ("workorder_number,status\n,open\n", "GMES/OQC", {"required_field"}),
        (
            "workorder_number,serial_number\nWO-1,SER-1\nWO-2,SER-1\n",
            "OWM",
            {"duplicate_serial"},
        ),
        ("workorder_number,serial_number\nWO-1,SER@1\n", "OWM", {"invalid_identifier"}),
        ("workorder_number,status\nWO-1,#VALUE!\n", "N-FP", {"invalid_formula"}),
        ("workorder_number,status\nWO-1,#REF!\n", "N-FP", {"broken_reference"}),
        ("workorder_number,workorder_reference\nWO-1,WO-9\n", "TMS", {"unmatched_key"}),
        ("work-order-changed\nWO-1\n", "N-FP", {"missing_column"}),
        (
            "workorder_number,organization_code\nWO-1,UNKNOWN\n",
            "OWM",
            {"unknown_organization"},
        ),
        ("workorder_number\nWO-1\nWO-1\n", "N-FP", {"duplicate_row"}),
    ],
)
def test_minimum_validation_scenarios(tmp_path, content, source, codes):
    known_organizations = {"OWM"} if "unknown_organization" in codes else None
    report = validate_file(
        write_csv(tmp_path, content),
        ".csv",
        source,
        known_organizations,
    )
    actual = {issue["code"] for issue in report["issues"]}
    assert codes <= actual
    assert all(
        {"severity", "sheet", "row", "column", "reason"} <= issue.keys()
        for issue in report["issues"]
    )


def test_xlsx_formula_errors_are_preserved(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Production"
    sheet.append(["workorder_number", "planned_quantity"])
    sheet.append(["WO-1", "=#VALUE!"])
    path = tmp_path / "formula.xlsx"
    workbook.save(path)

    report = validate_file(path, ".xlsx", "N-FP")

    issue = next(item for item in report["issues"] if item["code"] == "invalid_formula")
    assert issue["sheet"] == "Production"
    assert issue["row"] == 2
    assert issue["column"] == "B"
    assert report["blocking"] is True


def test_warning_does_not_block_valid_rows(tmp_path):
    report = validate_file(
        write_csv(tmp_path, "workorder_number\nWO-1\n\n"), ".csv", "N-FP"
    )
    assert report["warning_count"] == 1
    assert report["error_count"] == 0
    assert report["blocking"] is False


def test_equivalent_identifier_spacing_is_accepted_before_normalization(tmp_path):
    report = validate_file(
        write_csv(
            tmp_path,
            "workorder_number,serial_number\n wo - 0001 , SER - 1 \n",
        ),
        ".csv",
        "OWM",
    )

    assert report["valid"] is True
    assert not any(issue["code"] == "invalid_identifier" for issue in report["issues"])


def test_malformed_csv_after_header_becomes_blocking_read_error(tmp_path):
    report = validate_file(
        write_csv(tmp_path, 'workorder_number,status\nWO-1,"unterminated\n'),
        ".csv",
        "N-FP",
    )

    assert report["blocking"] is True
    assert report["issues"] == [
        {
            "severity": "error",
            "code": "read_error",
            "sheet": "CSV",
            "row": 2,
            "column": None,
            "reason": "CSV malformado durante a leitura",
        }
    ]


def test_configured_business_organization_is_valid(tmp_path):
    report = validate_file(
        write_csv(
            tmp_path,
            "workorder_number,organization_code\nWO-1,ORG-001\n",
        ),
        ".csv",
        "OWM",
        {"ORG-001", "LG"},
    )

    assert report["valid"] is True
    assert not any(
        issue["code"] == "unknown_organization" for issue in report["issues"]
    )
