#!/usr/bin/env python3
"""Verifica ausência de /ai/quality e assets experimentais no bundle web ou imagem."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

FORBIDDEN_MARKERS = ("/ai/quality", "ai_quality", "ai-quality", "scenarios.json")
FORBIDDEN_REGEX = r"/ai/quality|ai_quality|ai-quality|scenarios\.json"


def check_web_bundle(bundle_dir: Path) -> dict:
    if not bundle_dir.is_dir():
        raise FileNotFoundError(f"Bundle web ausente: {bundle_dir}")
    hits: list[str] = []
    files_checked = 0
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {
            ".js",
            ".html",
            ".json",
            ".css",
        }:
            continue
        files_checked += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                hits.append(f"{path.relative_to(bundle_dir)}:{marker}")
    if hits:
        raise AssertionError(f"Marcadores experimentais encontrados no bundle: {hits}")
    return {"bundle_dir": str(bundle_dir), "files_checked": files_checked, "hits": []}


def check_docker_image(image: str, paths: list[str]) -> dict:
    if not paths:
        raise ValueError("Lista de caminhos não pode ser vazia")
    for target in paths:
        stat_proc = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "test", image, "-d", target],
            capture_output=True,
            text=True,
            check=False,
        )
        if stat_proc.returncode != 0:
            raise RuntimeError(
                f"Caminho esperado ausente ou erro ao acessar imagem {image}: {target}"
            )
        grep_proc = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "grep",
                image,
                "-rnE",
                FORBIDDEN_REGEX,
                target,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if grep_proc.returncode == 0:
            lines = [line for line in grep_proc.stdout.splitlines() if line.strip()]
            raise AssertionError(
                f"Marcadores experimentais encontrados na imagem {image}: {lines}"
            )
        if grep_proc.returncode != 1:
            raise RuntimeError(
                f"Erro ao inspecionar imagem {image} ({grep_proc.returncode}): "
                f"{grep_proc.stderr.strip()}"
            )
    return {"image": image, "paths": paths, "hits": []}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-dist", type=Path, default=None)
    parser.add_argument("--backend-image", default=None)
    parser.add_argument("--web-image", default=None)
    args = parser.parse_args()
    results = []
    if args.web_dist is not None:
        results.append(check_web_bundle(args.web_dist))
    if args.backend_image:
        results.append(
            check_docker_image(args.backend_image, ["/opt/synergia/backend/app"])
        )
    if args.web_image:
        results.append(
            check_docker_image(args.web_image, ["/usr/share/nginx/html"])
        )
    if not results:
        parser.error("Informe ao menos --web-dist, --backend-image ou --web-image")
    print(json.dumps({"status": "passed", "checks": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
