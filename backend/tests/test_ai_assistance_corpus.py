"""Validação do corpus sintético congelado de 30 execuções para a #192."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "data" / "synthetic" / "ai-assistance-v1"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


def test_frozen_corpus_manifest_categories_and_hashes():
    from generate_ai_assistance_corpus import verify_corpus

    manifest_path = CORPUS_DIR / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "1.0.0"
    assert manifest["contains_real_data"] is False
    assert manifest["synthetic_only"] is True

    expected_categories = {
        "completed_with_occurrences": 10,
        "completed_without_occurrences": 5,
        "completed_with_errors": 5,
        "terminal_failure": 5,
        "insufficient_or_truncated": 5,
    }
    assert manifest["categories"] == expected_categories
    assert sum(manifest["categories"].values()) == 30

    cases = manifest["cases"]
    assert len(cases) == 30
    assert len({c["case_id"] for c in cases}) == 30
    assert len({c["execution_id"] for c in cases}) == 30
    assert len({c["file"] for c in cases}) == 30

    counted = {key: 0 for key in expected_categories}
    for case in cases:
        counted[case["category"]] += 1
        case_file = CORPUS_DIR / case["file"]
        assert case_file.is_file()
        assert hashlib.sha256(case_file.read_bytes()).hexdigest() == case["sha256"]
    assert counted == expected_categories

    assert len(manifest["organizations"]) == 2
    assert len({c["organization_key"] for c in cases}) == 2
    assert len({c["source"] for c in cases if c["source"]}) >= 4

    coverage = manifest["coverage"]
    case_ids = {c["case_id"] for c in cases}
    for key in (
        "negations",
        "instruction_like_text",
        "control_characters",
        "missing_references",
        "high_volume",
    ):
        assert coverage[key]
        assert set(coverage[key]).issubset(case_ids)

    verify_corpus(CORPUS_DIR)


def test_frozen_corpus_builds_valid_contexts_within_contract():
    from generate_ai_assistance_corpus import build_case_context

    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    insufficient_or_truncated = [
        c for c in manifest["cases"] if c["category"] == "insufficient_or_truncated"
    ]
    assert len(insufficient_or_truncated) == 5

    insufficient_count = 0
    truncated_count = 0
    for case in manifest["cases"]:
        context = build_case_context(CORPUS_DIR / case["file"])
        assert context.contract_version == "1.0.0"
        if context.sufficiency == "insufficient":
            insufficient_count += 1
        if context.truncated_sections:
            truncated_count += 1

    assert insufficient_count >= 2
    assert truncated_count >= 2


def test_verify_corpus_rejects_tampering_and_path_escapes(tmp_path):
    import pytest
    from generate_ai_assistance_corpus import generate_corpus, verify_corpus

    corpus = tmp_path / "corpus"
    generate_corpus(corpus)
    verify_corpus(corpus)

    # Path traversal in manifest
    manifest_path = corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered = dict(manifest)
    tampered["cases"] = [dict(c) for c in manifest["cases"]]
    tampered["cases"][0]["file"] = "../escape.json"
    manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="fora do corpus"):
        verify_corpus(corpus)

    # Category count tampering
    tampered2 = dict(manifest)
    tampered2["categories"] = {
        **manifest["categories"],
        "completed_with_occurrences": 9,
        "completed_without_occurrences": 6,
    }
    manifest_path.write_text(json.dumps(tampered2), encoding="utf-8")
    with pytest.raises(ValueError, match="categorias"):
        verify_corpus(corpus)

    # Case file tampering
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    case0 = corpus / manifest["cases"][0]["file"]
    case0.write_text(case0.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="Hash divergente"):
        verify_corpus(corpus)
