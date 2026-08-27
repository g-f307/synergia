from __future__ import annotations

import csv
from io import BytesIO, StringIO

import pytest
from openpyxl import Workbook

pytest_plugins = ("test_imports",)


def upload(client, content: bytes, *, source: str = "N-FP", name: str = "input.csv"):
    return client.post(
        "/imports",
        data={"source": source, "imported_by": "validation-test"},
        files={"file": (name, content)},
    )


def report(client, response):
    execution_id = response.json()["execution_id"]
    return client.get(f"/imports/{execution_id}/validation-report").json()


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"workorder_number,status\nWO-1,open\n", "missing_column"),
        (b"workorder_number,planned_quantity,status\n", "empty_file"),
        (
            b"workorder_number,planned_quantity,status,planned_date\nWO-1,2,open,31/99/2025\n",
            "invalid_date",
        ),
        (
            b"workorder_number,planned_quantity,status\nWO-1,two,open\n",
            "invalid_quantity",
        ),
        (b"workorder_number,planned_quantity,status\n,2,open\n", "missing_workorder"),
        (
            b"workorder_number,planned_quantity,status,serial_number\nWO-1,2,open,S-1\nWO-2,3,open,S-1\n",
            "duplicate_serial",
        ),
        (
            b"workorder_number,planned_quantity,status\nWO-1,#VALUE!,open\n",
            "invalid_formula",
        ),
        (
            b"workorder_number,planned_quantity,status\nWO-1,#REF!,open\n",
            "broken_reference",
        ),
        (
            b"workorder_number,planned_quantity,status,reference_workorder_number\nWO-1,2,open,WO-404\n",
            "unmatched_key",
        ),
        (b"work_order,planned_quantity,status\nWO-1,2,open\n", "missing_column"),
        (
            b"workorder_number,planned_quantity,status,organization\nWO-1,2,open,UNKNOWN\n",
            "unknown_organization",
        ),
    ],
)
def test_blocking_scenarios_have_explicit_located_errors(api, content, code) -> None:
    client, _, _ = api
    response = upload(client, content)

    assert response.status_code == 201
    assert response.json()["status"] == "blocked"
    validation = report(client, response)
    issue = next(item for item in validation["issues"] if item["code"] == code)
    assert validation["blocking"] is True
    assert issue["file_name"] == "input.csv"
    assert issue["message"]
    assert {"sheet", "row", "column"} <= issue.keys()


def test_empty_rows_and_duplicate_rows_are_warnings_and_do_not_block(api) -> None:
    client, _, _ = api
    content = (
        b"workorder_number,planned_quantity,status\nWO-1,2,open\n,,\nWO-1,2,open\n"
    )
    response = upload(client, content)
    validation = report(client, response)

    assert response.json()["status"] == "completed"
    assert validation["blocking"] is False
    assert {issue["code"] for issue in validation["issues"]} == {
        "empty_row",
        "duplicate_row",
    }
    assert all(issue["severity"] == "warning" for issue in validation["issues"])


def test_xlsx_formula_errors_keep_sheet_row_and_column(api) -> None:
    client, _, _ = api
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Workorders"
    sheet.append(["workorder_number", "planned_quantity", "status"])
    sheet.append(["WO-1", "=#REF!+1", "open"])
    stream = BytesIO()
    workbook.save(stream)

    response = upload(client, stream.getvalue(), name="formula.xlsx")
    issue = next(
        item
        for item in report(client, response)["issues"]
        if item["code"] == "broken_reference"
    )
    assert issue["sheet"] == "Workorders"
    assert issue["row"] == 2
    assert issue["column"] == "planned_quantity"


def test_invalid_serial_is_reported(api) -> None:
    client, _, _ = api
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["workorder_number", "planned_quantity", "status", "serial_number"])
    writer.writerow(["WO-1", 2, "open", "invalid serial!"])
    response = upload(client, output.getvalue().encode())

    assert "invalid_identifier" in {
        item["code"] for item in report(client, response)["issues"]
    }


def test_json_nested_value_is_an_invalid_type(api) -> None:
    client, _, _ = api
    response = upload(
        client,
        b'[{"workorder_number":"WO-1","planned_quantity":2,"status":{"value":"open"}}]',
        name="input.json",
    )
    assert "invalid_type" in {
        item["code"] for item in report(client, response)["issues"]
    }


def test_unknown_report_returns_not_found(api) -> None:
    client, _, _ = api
    assert client.get("/imports/unknown/validation-report").status_code == 404
