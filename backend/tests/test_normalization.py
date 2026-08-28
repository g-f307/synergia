from __future__ import annotations

from decimal import Decimal

from app.normalization import (
    RULES_PATH,
    load_normalization_rules,
    normalize_column_name,
    normalize_file,
    normalize_identifier,
)


def write_csv(tmp_path, content: str):
    path = tmp_path / "normalization.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_normalizes_business_fields_and_preserves_originals(tmp_path):
    path = write_csv(
        tmp_path,
        "Work Order,Demand ID,Serial,Lote,Modelo,Organiza\u00e7\u00e3o,Container,"
        "planned_date,Estado,OQC\n"
        " wo - 001 ,000000000000000000123,SER - 9, lot 7 , model x ,"
        " org-001 ,0000456,27/08/2026,Aberto,Sim\n",
    )

    result = normalize_file(path, ".csv", "N-FP")
    record = result["records"][0]

    assert record["values"] == {
        "workorder_number": "WO-001",
        "demand_id": "000000000000000000123",
        "serial_number": "SER-9",
        "lot_number": "LOT7",
        "model": "MODELX",
        "organization_code": "ORG-001",
        "container_number": "0000456",
        "planned_date": "2026-08-27",
        "status": "open",
        "oqc_flag": True,
    }
    assert record["original_values"]["workorder_number"] == " wo - 001 "
    assert record["original_values"]["demand_id"] == "000000000000000000123"
    assert len(record["transformations"]) == 10
    assert all(item["source_column"] for item in record["transformations"])


def test_long_identifiers_remain_text_without_scientific_notation():
    assert normalize_identifier(123456789012345678901234567890) == (
        "123456789012345678901234567890"
    )
    assert normalize_identifier(Decimal("1.234567890123456789E+20")) == (
        "123456789012345678900"
    )
    assert normalize_identifier("1.234567890123456789E+20") == ("123456789012345678900")


def test_unknown_state_and_oqc_flag_are_signaled(tmp_path):
    result = normalize_file(
        write_csv(
            tmp_path,
            "workorder_number,status,oqc_flag\nWO-1,Waiting External,Maybe\n",
        ),
        ".csv",
        "OWM",
    )

    assert result["records"][0]["values"]["status"] == "waiting_external"
    assert result["records"][0]["values"]["oqc_flag"] is None
    assert {issue["code"] for issue in result["issues"]} == {
        "unknown_state",
        "unknown_oqc_flag",
    }


def test_column_mapping_and_result_are_reproducible(tmp_path):
    assert normalize_column_name("  Identificador da Demanda ") == "demand_id"
    assert normalize_column_name("Tipo de Workorder") == "workorder_type"
    path = write_csv(tmp_path, "Work Order,Estado\nWO-1,Pendente\n")
    first = normalize_file(path, ".csv", "TMS")
    second = normalize_file(path, ".csv", "TMS")
    assert first == second


def test_normalizes_explicit_business_rule_flags(tmp_path):
    path = write_csv(
        tmp_path,
        "workorder_number,hold_flag,rework_flag,ship_block_flag,ativo\n"
        "WO-1,Sim,Não,true,false\n",
    )

    result = normalize_file(path, ".csv", "OWM")

    assert result["records"][0]["values"] == {
        "workorder_number": "WO-1",
        "hold_flag": True,
        "rework_flag": False,
        "ship_block_flag": True,
        "active": False,
    }


def test_declarative_rules_are_loaded_from_json():
    rules = load_normalization_rules()

    assert RULES_PATH.name == "normalization_rules.json"
    assert rules["column_aliases"]["work_order"] == "workorder_number"
    assert rules["state_map"]["aberto"] == "open"
    assert rules["oqc_flag_map"]["sim"] is True


def test_invalid_rule_file_fails_explicitly(tmp_path):
    invalid = tmp_path / "invalid-rules.json"
    invalid.write_text('{"column_aliases": {}}', encoding="utf-8")

    try:
        load_normalization_rules(invalid)
    except ValueError as exc:
        assert "identifier_fields" in str(exc)
    else:
        raise AssertionError("Configuração incompleta deveria falhar")


def test_duplicate_rule_key_fails_explicitly(tmp_path):
    duplicate = tmp_path / "duplicate-rules.json"
    duplicate.write_text(
        '{"column_aliases": {}, "column_aliases": {}}', encoding="utf-8"
    )

    try:
        load_normalization_rules(duplicate)
    except ValueError as exc:
        assert "Chave duplicada" in str(exc)
    else:
        raise AssertionError("Chave duplicada deveria falhar")
