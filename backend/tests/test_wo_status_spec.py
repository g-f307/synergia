from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.wo_status_spec import (
    COMPOSITE_SOURCE,
    AdapterSpecError,
    column_index,
    load_spec,
)

CONTRACT = (
    Path(__file__).resolve().parents[2] / "docs" / "real-workbook-contracts-v1.json"
)


def _contract_sheets() -> dict[str, dict]:
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return {
        sheet["name"]: sheet
        for sheet in document["workbooks"][0]["sheets"]
        if "columns" in sheet
    }


def test_spec_is_versioned_and_loads() -> None:
    spec = load_spec()

    assert spec.source == COMPOSITE_SOURCE
    assert re.fullmatch(r"\d+\.\d+\.\d+", spec.adapter_version)
    assert spec.label == f"wo_status@{spec.adapter_version}"
    assert {sheet.name for sheet in spec.sheets} == {
        "NFP",
        "OWM SN",
        "LOT PENDING_OQC",
        "CTNR STATUS",
    }


def test_every_contract_source_sheet_has_an_adapter_and_nothing_else() -> None:
    contract = _contract_sheets()
    spec = load_spec()

    assert {sheet.name for sheet in spec.sheets} == set(contract)


def test_adapter_columns_match_the_versioned_contract() -> None:
    contract = _contract_sheets()
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    spec = load_spec()

    assert spec.contract_version == document["contract_version"]
    for sheet in spec.sheets:
        reference = contract[sheet.name]
        assert sheet.header_row == reference["header_rows"][0]
        assert sheet.data_start_row == reference["data_start_row"]
        assert {c.letter for c in sheet.columns} == set(reference["columns"])
        for column in sheet.columns:
            declared = reference["columns"][column.letter]
            assert column.header == declared["header"]
            assert column.contract_target == declared["target"]
            assert declared["cell_policy"] == "literal_only"


def test_denied_columns_are_never_mapped() -> None:
    contract = _contract_sheets()

    for sheet in load_spec().sheets:
        denied = {item["column"] for item in contract[sheet.name]["denied_columns"]}
        assert denied.isdisjoint({column.letter for column in sheet.columns})


def test_blocked_sheet_follows_the_contract_decision() -> None:
    contract = _contract_sheets()
    spec = load_spec()

    for sheet in spec.sheets:
        decision = contract[sheet.name]["decision"]
        assert (sheet.blocked is not None) == decision.endswith("_blocked")
    assert spec.sheet("lot pending_oqc").blocked


def test_column_letters_resolve_to_indexes() -> None:
    assert [column_index(x) for x in ("A", "Z", "AA", "AM", "HY", "JV")] == [
        1,
        26,
        27,
        39,
        233,
        282,
    ]


def test_invalid_spec_is_rejected(tmp_path, monkeypatch) -> None:
    from app import wo_status_spec

    document = json.loads(wo_status_spec.SPEC_PATH.read_text(encoding="utf-8"))
    document["sheets"]["NFP"]["columns"][0]["kind"] = "desconhecido"
    broken = tmp_path / "spec.json"
    broken.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(wo_status_spec, "SPEC_PATH", broken)
    wo_status_spec.load_spec.cache_clear()
    try:
        with pytest.raises(AdapterSpecError):
            wo_status_spec.load_spec()
    finally:
        monkeypatch.undo()
        wo_status_spec.load_spec.cache_clear()
