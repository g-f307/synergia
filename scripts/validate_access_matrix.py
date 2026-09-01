#!/usr/bin/env python3
"""Compara as operações OpenAPI atuais com o inventário de acesso documental."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "access-control-matrix.md"
PUBLIC = {
    ("GET", "/health"),
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
}
ROW = re.compile(r"^\| `(?P<method>GET|POST|PUT|PATCH|DELETE) (?P<path>/[^`]*)` \|")


def documented_operations() -> list[tuple[str, str]]:
    return [
        (match.group("method"), match.group("path"))
        for line in MATRIX.read_text(encoding="utf-8").splitlines()
        if (match := ROW.match(line))
    ]


def openapi_operations() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app  # pylint: disable=import-outside-toplevel

    methods = {"get", "post", "put", "patch", "delete"}
    schema = app.openapi()
    operations = {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
        if method in methods
    }
    secured = {
        (method.upper(), path)
        for path, path_operations in schema["paths"].items()
        for method, operation in path_operations.items()
        if method in methods and operation.get("security")
    }
    return operations, secured


def main() -> int:
    documented = documented_operations()
    duplicates = sorted({item for item in documented if documented.count(item) > 1})
    operations, secured = openapi_operations()
    private = operations - PUBLIC
    documented_set = set(documented)
    missing = sorted(private - documented_set)
    stale = sorted(documented_set - private)

    unsecured = sorted(private - secured)
    public_secured = sorted(PUBLIC & secured)

    if duplicates or missing or stale or unsecured or public_secured:
        if duplicates:
            print(f"Rotas duplicadas: {duplicates}")
        if missing:
            print(f"Rotas privadas ausentes: {missing}")
        if stale:
            print(f"Rotas documentadas inexistentes: {stale}")
        if unsecured:
            print(f"Rotas privadas sem esquema Bearer: {unsecured}")
        if public_secured:
            print(f"Rotas públicas marcadas como privadas: {public_secured}")
        return 1

    print(
        f"OK: {len(private)} operações privadas documentadas; "
        f"{len(PUBLIC)} operações públicas explícitas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
