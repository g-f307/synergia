#!/usr/bin/env python3
"""Valida e publica a matriz executável de segurança das APIs."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "access-control-matrix.md"
DEFAULT_REPORT = ROOT / "docs" / "security-test-report.md"
PUBLIC = {
    ("GET", "/health"),
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
}
ROLES = ("admin", "gestor", "analista", "operador", "consulta")
ROW = re.compile(r"^`(?P<method>GET|POST|PUT|PATCH|DELETE) (?P<path>/[^`]*)`$")


@dataclass(frozen=True)
class MatrixCase:
    method: str
    path: str
    permission: str
    resource: str
    scope: str
    allowed_roles: frozenset[str]

    @property
    def identifier(self) -> str:
        return f"{self.method} {self.path}"


def load_cases(path: Path = MATRIX) -> list[MatrixCase]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if len(columns) != 5:
            continue
        match = ROW.match(columns[0])
        if not match:
            continue
        roles = frozenset(
            role.strip() for role in columns[4].split(",") if role.strip()
        )
        cases.append(
            MatrixCase(
                method=match.group("method"),
                path=match.group("path"),
                permission=columns[1].strip("`"),
                resource=columns[2],
                scope=columns[3].strip("`"),
                allowed_roles=roles,
            )
        )
    return cases


def openapi_operations() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app

    methods = {"get", "post", "put", "patch", "delete"}
    schema = app.openapi()
    operations = {
        (method.upper(), path)
        for path, path_operations in schema["paths"].items()
        for method in path_operations
        if method in methods
    }
    secured = {
        (method.upper(), path)
        for path, path_operations in schema["paths"].items()
        for method, operation in path_operations.items()
        if method in methods and operation.get("security")
    }
    return operations, secured


def validate(cases: list[MatrixCase]) -> list[str]:
    errors: list[str] = []
    operations, secured = openapi_operations()
    documented = {(case.method, case.path) for case in cases}
    private = operations - PUBLIC
    if len(documented) != len(cases):
        errors.append("a matriz possui operações duplicadas")
    if missing := sorted(private - documented):
        errors.append(f"operações privadas ausentes: {missing}")
    if stale := sorted(documented - private):
        errors.append(f"operações documentadas inexistentes: {stale}")
    if unsecured := sorted(private - secured):
        errors.append(f"operações privadas sem Bearer: {unsecured}")
    for case in cases:
        unknown = case.allowed_roles - set(ROLES)
        if unknown:
            errors.append(f"{case.identifier}: papéis desconhecidos {sorted(unknown)}")
        if not case.allowed_roles:
            errors.append(f"{case.identifier}: nenhum caso positivo")
    return errors


def render_report(cases: list[MatrixCase]) -> str:
    lines = [
        "# Relatório da matriz de segurança",
        "",
        "Relatório determinístico da suíte da issue #43. `permitido` e `negado`",
        "representam os casos positivos e negativos exigidos para cada papel.",
        "",
        f"- operações privadas cobertas: {len(cases)}",
        f"- papéis iniciais: {len(ROLES)}",
        f"- combinações papel x operação: {len(cases) * len(ROLES)}",
        "- rotas públicas explicitamente verificadas: 3",
        "",
        "| Operação | Permissão | Escopo | Permitido | Negado |",
        "| --- | --- | --- | --- | --- |",
    ]
    for case in cases:
        allowed = ", ".join(role for role in ROLES if role in case.allowed_roles)
        denied = ", ".join(role for role in ROLES if role not in case.allowed_roles)
        lines.append(
            f"| `{case.identifier}` | `{case.permission}` | `{case.scope}` | "
            f"{allowed} | {denied} |"
        )
    lines.extend(
        [
            "",
            "## Evidências automatizadas",
            "",
            "- `test_security_matrix_persistence.py`: 285 requisições HTTP reais",
            "  com JWT, papéis e permissões carregados do PostgreSQL;",
            "- `test_security_regression.py`: completude OpenAPI, mass assignment,",
            "  respostas uniformes e ausência de segredos;",
            "- `test_auth.py`: tokens expirados, adulterados, emissor, audiência",
            "  e algoritmo inválidos;",
            "- `test_auth_persistence.py`: replay sequencial e concorrente,",
            "  revogação, usuário bloqueado e auditoria de autenticação;",
            "- `test_authorization_persistence.py`: escopo horizontal e vertical,",
            "  mudança de papel, sessão revogada e auditoria de negações;",
            "- PostgreSQL 16: todos os testes `integration` no job `project-data`.",
            "",
            "A suíte usa somente UUIDs, domínios `.invalid` e dados sintéticos.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    cases = load_cases()
    if errors := validate(cases):
        print("\n".join(errors))
        return 1
    report = render_report(cases)
    if args.check:
        current = (
            args.output.read_text(encoding="utf-8")
            if args.output.is_file()
            else None
        )
        if current != report:
            print(f"Relatório desatualizado: {args.output}")
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8", newline="\n")
    print(
        f"OK: {len(cases)} operações privadas e "
        f"{len(cases) * len(ROLES)} combinações validadas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
