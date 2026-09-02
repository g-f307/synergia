from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_i18n import validate  # noqa: E402


def _write_catalogs(root: Path, pt: dict[str, str], en: dict[str, str]) -> None:
    root.mkdir()
    (root / "pt-BR.json").write_text(json.dumps(pt), encoding="utf-8")
    (root / "en-US.json").write_text(json.dumps(en), encoding="utf-8")


def test_i18n_catalogs_match_and_all_keys_are_used(tmp_path: Path) -> None:
    catalogs = tmp_path / "catalogs"
    source = tmp_path / "source"
    source.mkdir()
    _write_catalogs(catalogs, {"page.title": "Título"}, {"page.title": "Title"})
    (source / "component.ts").write_text("i18n.t('page.title')", encoding="utf-8")

    assert validate(catalogs, source) == []


def test_i18n_validator_rejects_missing_and_empty_values(tmp_path: Path) -> None:
    catalogs = tmp_path / "catalogs"
    source = tmp_path / "source"
    source.mkdir()
    _write_catalogs(
        catalogs,
        {"page.title": "Título", "page.empty": ""},
        {"page.title": "Title"},
    )
    (source / "component.html").write_text("'page.title'", encoding="utf-8")

    errors = validate(catalogs, source)
    assert "en-US: chave ausente: page.empty" in errors
    assert "pt-BR: valor vazio: page.empty" in errors


def test_i18n_validator_rejects_orphan_keys(tmp_path: Path) -> None:
    catalogs = tmp_path / "catalogs"
    source = tmp_path / "source"
    source.mkdir()
    _write_catalogs(catalogs, {"page.title": "Título"}, {"page.title": "Title"})
    (source / "component.ts").write_text("export const value = true", encoding="utf-8")

    assert validate(catalogs, source) == ["chave órfã: page.title"]
