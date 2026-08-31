#!/usr/bin/env python3
"""Compara as operações OpenAPI atuais com o inventário de acesso documental."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "access-control-matrix.md"
PUBLIC = {("GET", "/health")}
ROW = re.compile(r"^\| `(?P<method>GET|POST|PUT|PATCH|DELETE) (?P<path>/[^`]*)` \|")


def documented_operations() -> list[tuple[str, str]]:
    return [
        (match.group("method"), match.group("path"))
        for line in MATRIX.read_text(encoding="utf-8").splitlines()
        if (match := ROW.match(line))
    ]


def openapi_operations() -> set[tuple[str, str]]:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app  # pylint: disable=import-outside-toplevel

    methods = {"get", "post", "put", "patch", "delete"}
    schema = app.openapi()
    return {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
        if method in methods
    }


def main() -> int:
    documented = documented_operations()
    duplicates = sorted({item for item in documented if documented.count(item) > 1})
    private = openapi_operations() - PUBLIC
    documented_set = set(documented)
    missing = sorted(private - documented_set)
    stale = sorted(documented_set - private)

    if duplicates or missing or stale:
        if duplicates:
            print(f"Rotas duplicadas: {duplicates}")
        if missing:
            print(f"Rotas privadas ausentes: {missing}")
        if stale:
            print(f"Rotas documentadas inexistentes: {stale}")
        return 1

    print(
        f"OK: {len(private)} operações privadas documentadas; "
        f"{len(PUBLIC)} operação pública explícita."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

