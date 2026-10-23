from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ingestion_corpus import (  # noqa: E402
    CORPUS,
    corpus_cases,
    digest,
    edited,
    execute,
    golden,
    verify_manifest,
)

from app.upload_security import UnsafeUpload  # noqa: E402

MANIFEST = json.loads((CORPUS / "manifest.json").read_text())


@pytest.mark.parametrize("case", MANIFEST["cases"], ids=lambda c: c["id"])
def test_frozen_case_matches_hashes_semantics_and_reconciliation(case):
    assert digest((CORPUS / case["input"]).read_bytes()) == case["input_sha256"]
    expected_bytes = (CORPUS / case["golden"]).read_bytes()
    assert digest(expected_bytes) == case["golden_sha256"]
    report, result = execute(CORPUS / case["input"], case["source"])
    assert golden(report, result) == json.loads(expected_bytes)
    assert report["balanced"]
    assert {
        row["row"]
        for row in result["normalized_records"]
        if case["source"] == "Total Decision"
    }.isdisjoint({1, 2, 3})
    for sheet in report["sheets"]:
        assert sheet["read"] == sheet["ignored"] + sheet["imported"]
        assert sheet["imported"] == sheet["normalized"] + sheet["rejected"]


def test_regeneration_reproduces_frozen_bytes_and_all_cases():
    manifest = verify_manifest()
    regenerated = {name: digest(content) for name, _, content in corpus_cases()}
    assert set(regenerated) == {c["id"] for c in manifest["cases"]}
    assert regenerated == {c["id"]: c["input_sha256"] for c in manifest["cases"]}


@pytest.mark.parametrize("kind", ["input", "golden"])
def test_accidental_fixture_or_golden_change_is_detected(tmp_path, kind):
    target = tmp_path / "corpus"
    shutil.copytree(CORPUS, target)
    case = MANIFEST["cases"][0]
    path = target / case[kind]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Hash"):
        verify_manifest(target)


def test_public_counts_never_include_private_names_values_or_hashes(tmp_path):
    path = tmp_path / "PRIVATE-CUSTOMER-FILENAME.xlsx"
    path.write_bytes((CORPUS / "td-additional.xlsx").read_bytes())
    report, result = execute(path, "Total Decision")
    text = json.dumps(report)
    for value in (
        path.name,
        "SYNTHETIC-PRIVATE-SHEET",
        "SYN-WO",
        "000000",
        "SYNTHETIC-RESTRICTED-CONTENT",
        "SYNTHETIC-DENIED-CONTENT",
        digest(path.read_bytes()),
    ):
        assert value not in text
    normalized = json.dumps(result["normalized_records"], default=str)
    assert "SYNTHETIC-RESTRICTED-CONTENT" not in normalized
    assert "SYNTHETIC-DENIED-CONTENT" not in normalized


def test_mixed_case_has_known_counts_dates_and_literal_identifiers():
    report, result = execute(CORPUS / "td-mixed.xlsx", "Total Decision")
    sheet = report["sheets"][0]
    assert (
        sheet["read"],
        sheet["ignored"],
        sheet["normalized"],
        sheet["rejected"],
        sheet["duplicated"],
    ) == (6, 1, 4, 1, 1)
    rows = {r["row"]: r["values"] for r in result["normalized_records"]}
    assert rows[4]["oqc_lot_id"] == rows[5]["oqc_lot_id"] == "000000"
    assert rows[7]["production_date"] == "2025-12-09"
    assert rows[8]["inspection_date"] == "2026-10-05"
    assert report["codes"]["invalid_quantity"] == 1
    assert result["imported_records"][-1]["original_values"]["hold_quantity"] == "#REF!"


def test_dangerous_formula_in_unauthorized_sheet_is_still_rejected(tmp_path):
    def danger(book):
        book.create_sheet("PRIVATE-NAME")["A1"] = (
            '=WEBSERVICE("https://example.invalid")'
        )

    path = tmp_path / "danger.xlsx"
    path.write_bytes(edited((CORPUS / "td-clean.xlsx").read_bytes(), action=danger))
    with pytest.raises(UnsafeUpload):
        execute(path, "Total Decision")
