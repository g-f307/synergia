from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ALLOWED_SUFFIXES = {".csv", ".json", ".log", ".md", ".xml"}
SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "auth_jwt_signing_key",
    "cookie",
    "database_url",
    "password",
    "rate_limit_key_secret",
    "refresh_token",
}
SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._~-]{20,}"),
    re.compile(r"(?i)postgres(?:ql)?://[^\s:/]+:[^\s@]+@"),
    re.compile(
        r"(?i)(?:access_token|refresh_token|password|authorization)"
        r"\s*[:=]\s*[\"']?[^\s,\"']+"
    ),
)
REQUIRED_CATEGORIES = {
    "manifest",
    "migration_comparison",
    "postgres_plan_after",
    "postgres_plan_before",
    "reference_run",
    "rupture_run",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sanitize_value(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if key.lower() in SENSITIVE_KEYS
                else _sanitize_value(item, replacements)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(item, replacements) for item in value]
    if isinstance(value, str):
        for source, replacement in replacements.items():
            value = value.replace(source, replacement)
    return value


def _assert_sanitized(text: str, source: Path) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"Possível segredo em {source}: {pattern.pattern}")


def _render(source: Path, replacements: dict[str, str]) -> bytes:
    if source.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"Formato não publicável: {source}")
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        rendered = json.dumps(
            _sanitize_value(payload, replacements),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ) + "\n"
    else:
        rendered = source.read_text(encoding="utf-8")
        for original, replacement in replacements.items():
            rendered = rendered.replace(original, replacement)
    _assert_sanitized(rendered, source)
    return rendered.encode("utf-8")


def _sources(root: Path, entry: dict[str, Any]) -> list[Path]:
    source = (root / entry["source"]).resolve(strict=True)
    if not source.is_relative_to(root):
        raise ValueError(f"Fonte fora do workspace: {source}")
    if source.is_file():
        return [source]
    patterns = entry.get("include", ["*"])
    files = [
        path
        for path in source.rglob("*")
        if path.is_file()
        and any(fnmatch.fnmatch(str(path.relative_to(source)), pattern) for pattern in patterns)
    ]
    if not files:
        raise ValueError(f"Entrada sem arquivos: {entry['source']}")
    return sorted(files)


def publish(spec_path: Path) -> dict[str, Any]:
    root = Path.cwd().resolve()
    spec_path = spec_path.resolve(strict=True)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    output = (root / spec["output"]).resolve()
    if not output.is_relative_to(root):
        raise ValueError("Destino fora do workspace")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Destino não está vazio: {output}")
    output.mkdir(parents=True, exist_ok=True)
    replacements = {
        str(root): "${WORKSPACE}",
        str(Path.home()): "${HOME}",
    }
    categories = {entry["category"] for entry in spec["entries"]}
    missing_categories = sorted(REQUIRED_CATEGORIES - categories)
    if missing_categories:
        raise ValueError(f"Categorias obrigatórias ausentes: {missing_categories}")

    indexed: list[dict[str, Any]] = []
    targets: set[str] = set()
    for entry in spec["entries"]:
        source_root = (root / entry["source"]).resolve(strict=True)
        for source in _sources(root, entry):
            relative = source.name if source_root.is_file() else source.relative_to(source_root)
            target = Path(entry["target"]) / relative
            target_text = target.as_posix()
            if target_text in targets or target.is_absolute() or ".." in target.parts:
                raise ValueError(f"Destino inválido ou repetido: {target}")
            targets.add(target_text)
            destination = output / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(_render(source, replacements))
            indexed.append(
                {
                    "category": entry["category"],
                    "path": target_text,
                    "source": str(source.relative_to(root)),
                    "bytes": destination.stat().st_size,
                    "sha256": _sha256(destination),
                }
            )

    index = {
        "schema_version": "1.0",
        "published_at": spec["published_at"],
        "sanitization": {
            "absolute_workspace_paths": "${WORKSPACE}",
            "absolute_home_paths": "${HOME}",
            "sensitive_keys": "[REDACTED]",
            "secret_pattern_scan": "passed",
        },
        "scope": spec.get("scope", {}),
        "claims": spec["claims"],
        "summary": {
            "files": len(indexed),
            "bytes": sum(item["bytes"] for item in indexed),
            "categories": {
                category: sum(item["category"] == category for item in indexed)
                for category in sorted(categories)
            },
        },
        "files": sorted(indexed, key=lambda item: item["path"]),
    }
    index_path = output / "index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    checksum_paths = sorted([*output.rglob("*"), index_path])
    checksum_paths = sorted({path for path in checksum_paths if path.is_file()})
    checksums = "".join(
        f"{_sha256(path)}  {path.relative_to(output).as_posix()}\n"
        for path in checksum_paths
    )
    (output / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    return index


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publica evidências de desempenho sanitizadas e indexadas"
    )
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    result = publish(args.spec)
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
