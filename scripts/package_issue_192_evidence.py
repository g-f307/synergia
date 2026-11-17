#!/usr/bin/env python3
"""Empacota evidências locais da #192 em zip único com manifesto e hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

FORBIDDEN_PARTS = {".env", ".git", "__pycache__", ".pytest_cache", "node_modules"}
FORBIDDEN_SUFFIXES = {".gguf", ".safetensors", ".pt", ".onnx", ".ckpt"}
ALLOWED_PATTERNS = (
    "runs/*/ci-fake-report.json",
    "runs/*/real-qwen-report.json",
    "runs/*/manifest-hashes.json",
    "runs/*/raw/*.bin",
    "migrations-rollback.json",
    "graylog-reconciliation.json",
    "pg-api-p95.json",
    "e2e-assistance-results/**/*.webm",
    "e2e-assistance-results/**/*.png",
    "axe-*.json",
    "*.png",
)
EXCLUDED_ATTACHMENT_SUFFIXES = {".zip"}


def _is_forbidden(rel: Path) -> bool:
    if any(part in FORBIDDEN_PARTS or part.startswith(".env") for part in rel.parts):
        return True
    if rel.suffix.lower() in FORBIDDEN_SUFFIXES:
        return True
    return False


def _scan_forbidden(resolved_dir: Path, target_zip: Path, tmp_zip: Path) -> None:
    for item in resolved_dir.rglob("*"):
        if item in {target_zip, tmp_zip}:
            continue
        if item.is_symlink():
            raise ValueError(f"Symlink proibido no pacote: {item}")
        if not item.is_file():
            continue
        resolved_item = item.resolve()
        if not resolved_item.is_relative_to(resolved_dir):
            raise ValueError(f"Arquivo escapa do diretório de evidências: {item}")
        if _is_forbidden(resolved_item.relative_to(resolved_dir)):
            raise ValueError(
                f"Arquivo proibido no pacote: {resolved_item.relative_to(resolved_dir)}"
            )


def _is_excluded_attachment(path: Path) -> bool:
    name = path.name.lower()
    return (
        path.suffix.lower() in EXCLUDED_ATTACHMENT_SUFFIXES
        or name == "trace.zip"
        or name.startswith("trace.")
    )


def _collect_allowlisted_files(resolved_dir: Path) -> list[Path]:
    collected: set[Path] = set()
    for pattern in ALLOWED_PATTERNS:
        for item in resolved_dir.glob(pattern):
            if item.is_file() and not item.is_symlink():
                resolved_item = item.resolve()
                if resolved_item.is_relative_to(resolved_dir) and not _is_excluded_attachment(
                    resolved_item
                ):
                    collected.add(resolved_item)
    return sorted(collected)


def package_evidence(evidence_dir: Path, output_zip: Path | None = None) -> dict:
    resolved_dir = evidence_dir.resolve()
    if not resolved_dir.is_dir():
        raise FileNotFoundError(f"Diretório de evidências ausente: {evidence_dir}")

    target_zip = (output_zip or (resolved_dir / "package-issue-192.zip")).resolve()
    if not target_zip.is_relative_to(resolved_dir):
        raise ValueError(
            "Arquivo zip de saída deve ficar confinado ao diretório de evidências"
        )
    tmp_zip = target_zip.with_name(target_zip.name + ".tmp")

    _scan_forbidden(resolved_dir, target_zip, tmp_zip)
    files = _collect_allowlisted_files(resolved_dir)

    files_meta: list[dict] = []
    try:
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for resolved_item in files:
                rel = resolved_item.relative_to(resolved_dir)
                digest = hashlib.sha256(resolved_item.read_bytes()).hexdigest()
                zf.write(resolved_item, arcname=rel.as_posix())
                files_meta.append(
                    {
                        "path": rel.as_posix(),
                        "size_bytes": resolved_item.stat().st_size,
                        "sha256": digest,
                    }
                )
            manifest = {
                "schema_version": "1.0.0",
                "issue": 192,
                "created_at": datetime.now(UTC).isoformat(),
                "file_count": len(files_meta),
                "files": files_meta,
            }
            zf.writestr(
                "package-manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
        os.replace(tmp_zip, target_zip)
    except BaseException:
        if tmp_zip.exists():
            tmp_zip.unlink()
        raise
    return {"zip_path": str(target_zip), **manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output-zip", type=Path, default=None)
    args = parser.parse_args()
    result = package_evidence(args.evidence_dir, args.output_zip)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
