from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOGS = ROOT / "web/src/app/shared/i18n/catalogs"
DEFAULT_SOURCE = ROOT / "web/src/app"
CATALOG_NAMES = ("pt-BR.json", "en-US.json")
KEY_PATTERN = re.compile(r"['\"]([a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+)['\"]")


def load_catalog(path: Path) -> dict[str, str]:
    content = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in content.items()
    ):
        raise ValueError(f"Catálogo inválido: {path}")
    return content


def validate(catalog_root: Path, source_root: Path) -> list[str]:
    errors: list[str] = []
    catalogs = {
        name.removesuffix(".json"): load_catalog(catalog_root / name)
        for name in CATALOG_NAMES
    }
    reference_keys = set(catalogs["pt-BR"])
    for locale, catalog in catalogs.items():
        keys = set(catalog)
        for key in sorted(reference_keys - keys):
            errors.append(f"{locale}: chave ausente: {key}")
        for key in sorted(keys - reference_keys):
            errors.append(f"{locale}: chave extra: {key}")
        for key, value in sorted(catalog.items()):
            if not value.strip():
                errors.append(f"{locale}: valor vazio: {key}")

    referenced: set[str] = set()
    for path in source_root.rglob("*"):
        if path.suffix not in {".ts", ".html"} or path.name.endswith(".spec.ts"):
            continue
        source = (
            path.read_text(encoding="utf-8")
            .replace("\\'", "'")
            .replace('\\"', '"')
        )
        referenced.update(KEY_PATTERN.findall(source))
    referenced &= reference_keys
    for key in sorted(reference_keys - referenced):
        errors.append(f"chave órfã: {key}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-root", type=Path, default=DEFAULT_CATALOGS)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    errors = validate(args.catalog_root, args.source_root)
    if errors:
        print("\n".join(errors))
        return 1
    key_count = len(load_catalog(args.catalog_root / "pt-BR.json"))
    print(
        f"OK: {key_count} chaves em pt-BR e en-US, "
        "sem ausências ou órfãs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
