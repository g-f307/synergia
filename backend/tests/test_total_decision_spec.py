import json
import sys
from pathlib import Path

import pytest

from app.total_decision_spec import load_spec

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.generate_total_decision_fixture import build_workbook  # noqa: E402


def test_spec_matches_contract_and_minimizes_restricted_fields():
    document = json.loads((ROOT / "docs/real-workbook-contracts-v1.json").read_text())
    sheet = document["workbooks"][1]["sheets"][0]
    spec = load_spec()
    assert spec.contract_version == document["contract_version"]
    assert spec.label == "total_decision@1.0.0"
    assert spec.sheet.logical_source == "GMES/OQC"
    assert {c.letter for c in spec.sheet.columns} == set(sheet["columns"])
    for column in spec.sheet.columns:
        declared = sheet["columns"][column.letter]
        assert column.header_path == tuple(declared["header_path"])
        assert column.contract_target == declared["target"]
    restricted = {c.letter for c in spec.sheet.columns if c.kind == "restricted"}
    assert restricted == {"AM", "AN", "AR"}
    assert "organization_code" not in {c.field for c in spec.sheet.columns}
    assert "lot_number" not in {c.field for c in spec.sheet.columns}


def test_synthetic_workbook_is_reproducible():
    assert build_workbook(edge=True) == build_workbook(edge=True)
    # Also compare with bytes generated in another process/session, so wall-clock
    # metadata cannot silently invalidate hashes across machines or CI runs.
    assert (
        build_workbook()
        == (ROOT / "data/synthetic/total-decision_minimal.xlsx").read_bytes()
    )


def test_invalid_spec_is_rejected(tmp_path, monkeypatch):
    from app import total_decision_spec

    raw = json.loads(total_decision_spec.SPEC_PATH.read_text())
    raw["columns"][0]["kind"] = "arbitrary"
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw))
    monkeypatch.setattr(total_decision_spec, "SPEC_PATH", path)
    load_spec.cache_clear()
    try:
        with pytest.raises(ValueError):
            load_spec()
    finally:
        load_spec.cache_clear()
