from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from zipfile import BadZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_project_assets as assets  # noqa: E402


@pytest.fixture
def synthetic_root(tmp_path, monkeypatch):
    shutil.copytree(
        ROOT / "data/synthetic/ai-quality-v2", tmp_path / "ai-quality-v2"
    )
    shutil.copytree(
        ROOT / "data/synthetic/ai-operational-v2", tmp_path / "ai-operational-v2"
    )
    monkeypatch.setattr(assets, "SYNTHETIC_DATA", tmp_path)
    return tmp_path


def test_project_assets_accepts_frozen_quality_corpus(synthetic_root, monkeypatch):
    def unexpected_validator(path):
        pytest.fail(f"Quality corpus reached operational validator: {path.name}")

    monkeypatch.setattr(assets, "validate_manifest", unexpected_validator)
    assets.validate_synthetic_data()


def test_project_assets_dispatches_operational_manifest_with_quality_corpus(
    synthetic_root,
):
    assets.validate_synthetic_data()


@pytest.mark.parametrize("change", ["modified", "missing", "gold"])
def test_project_assets_rejects_quality_integrity_failure(synthetic_root, change):
    dataset = synthetic_root / "ai-quality-v2"
    path = dataset / "evaluation/QD2-E12.xlsx"
    if change == "missing":
        path.unlink()
    elif change == "gold":
        (dataset / "scenarios.json").write_text("{}", encoding="utf-8")
    else:
        path.write_bytes(b"unexpected corruption")
    with pytest.raises(ValueError, match="Dataset de diagnóstico inválido"):
        assets.validate_synthetic_data()


def test_unlisted_quality_file_still_receives_generic_validation(synthetic_root):
    (synthetic_root / "ai-quality-v2/extra.xlsx").write_bytes(b"not a workbook")
    with pytest.raises(BadZipFile):
        assets.validate_synthetic_data()


@pytest.mark.parametrize("homologation", [False, True])
def test_other_manifests_keep_existing_dispatch(
    synthetic_root, monkeypatch, homologation
):
    directory = synthetic_root / "other"
    directory.mkdir()
    path = directory / "manifest.json"
    path.write_text(
        json.dumps({"contains_real_data": False} if homologation else {}),
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(assets, "validate_manifest", lambda p: calls.append((p, False)))
    monkeypatch.setattr(
        assets, "validate_homologation_manifest", lambda p: calls.append((p, True))
    )
    assets.validate_synthetic_data()
    assert calls == [(path, homologation)]
