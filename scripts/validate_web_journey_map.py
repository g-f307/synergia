#!/usr/bin/env python3
"""Valida o mapa web contra OpenAPI, matriz de acesso e rotas atuais."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "docs" / "web-route-map.json"
MATRIX = ROOT / "docs" / "access-control-matrix.md"
APP_ROUTES = ROOT / "web" / "src" / "app" / "app.routes.ts"

PROTOTYPE_PAGES = {
    "index.html",
    "consulta.html",
    "monitor.html",
    "pendencias.html",
    "detalhe-pendencia.html",
    "relatorios.html",
    "visualizar-relatorio.html",
    "configuracoes.html",
}
REQUIRED_STATES = {
    "loading",
    "empty",
    "partial",
    "stale",
    "error",
    "forbidden",
    "unavailable",
}
PUBLIC = {
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
}
MATRIX_ROW = re.compile(
    r"^\| `(?P<method>GET|POST|PUT|PATCH|DELETE) (?P<path>/[^`]*)` "
    r"\| `(?P<permission>[^`]*)` \| [^|]+ \| "
    r"`?(?P<scope>[^`| ]+)`? \|"
)
ANGULAR_PATH = re.compile(r"\bpath:\s*'(?P<path>[^']*)'")


def _openapi_operations() -> set[tuple[str, str]]:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app  # pylint: disable=import-outside-toplevel

    methods = {"get", "post", "put", "patch", "delete"}
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method in methods
    }


def _matrix_contracts() -> dict[tuple[str, str], tuple[str, str]]:
    result = {}
    for line in MATRIX.read_text(encoding="utf-8").splitlines():
        if match := MATRIX_ROW.match(line):
            result[(match.group("method"), match.group("path"))] = (
                match.group("permission"),
                match.group("scope"),
            )
    return result


def _current_routes() -> set[str]:
    paths = {
        match.group("path")
        for match in ANGULAR_PATH.finditer(APP_ROUTES.read_text(encoding="utf-8"))
    }
    return {f"/{path}" for path in paths - {"", "**"}}


def validate() -> dict:
    document = json.loads(MAP.read_text(encoding="utf-8"))
    routes = document.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError("Mapa deve possuir uma lista não vazia de rotas")
    if set(document.get("required_states", [])) != REQUIRED_STATES:
        raise ValueError("Catálogo de estados do mapa está incompleto")

    ids = [route.get("id") for route in routes]
    paths = [route.get("route") for route in routes]
    if None in ids or len(ids) != len(set(ids)):
        raise ValueError("IDs de rota ausentes ou duplicados")
    if None in paths or len(paths) != len(set(paths)):
        raise ValueError("Caminhos web ausentes ou duplicados")

    operations = _openapi_operations()
    contracts = _matrix_contracts()
    mapped_prototype = set()
    allowed_statuses = {"implemented", "planned", "deferred"}

    for route in routes:
        route_id = route["id"]
        status = route.get("status")
        if status not in allowed_statuses:
            raise ValueError(f"Estado inválido em {route_id}: {status}")
        if not route.get("states") or not set(route["states"]) <= REQUIRED_STATES:
            raise ValueError(f"Estados de interface inválidos em {route_id}")
        if not route.get("permission") or not route.get("scope"):
            raise ValueError(f"Permissão ou escopo ausente em {route_id}")
        if not isinstance(route.get("url_state"), list):
            raise ValueError(f"Estado de URL ausente em {route_id}")

        prototype_pages = route.get("prototype_pages", [])
        unknown_pages = set(prototype_pages) - PROTOTYPE_PAGES
        if unknown_pages:
            raise ValueError(f"Páginas desconhecidas em {route_id}: {unknown_pages}")
        mapped_prototype.update(prototype_pages)

        endpoints = route.get("endpoints", [])
        if status == "deferred":
            has_invalid_deferred_contract = (
                endpoints
                or route.get("issue") != "stage-4"
                or not route.get("decision")
            )
            if has_invalid_deferred_contract:
                raise ValueError(f"Item adiado sem decisão explícita em {route_id}")
            continue
        if not endpoints:
            raise ValueError(f"Rota ativa sem contrato em {route_id}")

        for endpoint in endpoints:
            operation = (endpoint.get("method"), endpoint.get("path"))
            if operation not in operations:
                raise ValueError(
                    f"Operação OpenAPI inexistente em {route_id}: {operation}"
                )
            expected = (
                ("public", "public")
                if operation in PUBLIC
                else contracts.get(operation)
            )
            if expected is None:
                raise ValueError(
                    f"Operação sem matriz de acesso em {route_id}: {operation}"
                )
            expected_permission, expected_scope = expected
            if endpoint.get("permission") != expected_permission:
                raise ValueError(
                    f"Permissão divergente em {route_id}: {operation} "
                    f"esperava {expected_permission}, "
                    f"recebeu {endpoint.get('permission')}"
                )
            if route.get("scope") != expected_scope:
                raise ValueError(
                    f"Escopo divergente em {route_id}: {operation} "
                    f"esperava {expected_scope}, recebeu {route.get('scope')}"
                )

    if mapped_prototype != PROTOTYPE_PAGES:
        missing = sorted(PROTOTYPE_PAGES - mapped_prototype)
        raise ValueError(f"Páginas do protótipo sem decisão: {missing}")

    mapped_paths = set(paths)
    current_routes = _current_routes()
    current_missing = sorted(current_routes - mapped_paths)
    if current_missing:
        raise ValueError(f"Rotas Angular atuais fora do mapa: {current_missing}")
    implemented_missing = sorted(
        route["route"]
        for route in routes
        if route["status"] == "implemented" and route["route"] not in current_routes
    )
    if implemented_missing:
        raise ValueError(
            f"Rotas marcadas como implementadas ausentes no Angular: "
            f"{implemented_missing}"
        )
    return document


def main() -> int:
    document = validate()
    routes = document["routes"]
    active = sum(route["status"] != "deferred" for route in routes)
    deferred = len(routes) - active
    print(
        f"OK: {active} rotas ativas/planejadas, {deferred} adiadas e "
        f"{len(PROTOTYPE_PAGES)} páginas do protótipo com decisão."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
