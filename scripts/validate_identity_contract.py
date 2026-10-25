#!/usr/bin/env python3
"""Valida o registro de decisões do contrato de identidade corporativa."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "corporate-identity-decisions.json"
REQUIRED_IDS = {f"ID-P{number:02d}" for number in range(1, 12)}
STATES = {"pending_external", "proposed", "decided"}
OWNERS = {
    "TI/Segurança LG",
    "TI/Gestor LG",
    "TI/DevOps LG",
    "TI/Segurança LG e Gestor",
    "Gestor LG",
    "DPO/TI/Gestor LG",
    "Equipe SYNERGIA",
}
GATES = {f"ID-P{number:02d}" for number in range(1, 8)}
DOCUMENTS = {
    "docs/corporate-identity-contract.md": REQUIRED_IDS,
    "docs/adr/0002-corporate-identity-contract.md": REQUIRED_IDS,
    "docs/runbooks/corporate-identity-activation.md": GATES,
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*(?:PRIVATE KEY|CERTIFICATE)"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
    re.compile(
        r"(?i)\b(?:client_secret|secret|password|senha)\s*[:=]\s*['\"]?[^\s'\"<>$]{6,}"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
)
FILES_WITHOUT_SECRETS = (
    "docs/corporate-identity-decisions.json",
    "docs/corporate-identity-claims-examples.json",
    *DOCUMENTS,
)


def _require_text(item: dict, field: str, subject: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{subject} sem {field}")
    return value


def validate(register: Path = REGISTER) -> dict:
    document = json.loads(register.read_text(encoding="utf-8"))
    if set(document.get("states", {})) != STATES:
        raise ValueError("Catálogo de estados divergente")
    decisions = document.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("Registro sem decisões")
    identifiers = [item.get("id") for item in decisions]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Decisões duplicadas")
    if missing := REQUIRED_IDS - set(identifiers):
        raise ValueError(f"Decisões obrigatórias ausentes: {sorted(missing)}")
    for item in decisions:
        subject = f"Decisão {item.get('id')}"
        for field in (
            "title",
            "scope_item",
            "required_input",
            "blocks",
            "interim_behavior",
        ):
            _require_text(item, field, subject)
        if item.get("owner") not in OWNERS:
            raise ValueError(f"{subject} sem responsável válido")
        if item.get("state") not in STATES:
            raise ValueError(f"{subject} com estado inválido")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"{subject} sem evidência")
        for relative in evidence:
            path = Path(relative)
            if path.is_absolute() or not (ROOT / path).is_file():
                raise ValueError(f"Evidência inexistente em {subject}: {relative}")
        if item["state"] == "decided" and item["owner"] != "Equipe SYNERGIA":
            if "confirmação" not in item["required_input"]:
                raise ValueError(f"{subject} decidida por terceiros sem confirmação")
    for relative, required in DOCUMENTS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        if absent := [i for i in sorted(required) if i not in text]:
            raise ValueError(f"{relative} não cita {absent}")
    for relative in FILES_WITHOUT_SECRETS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                raise ValueError(f"Possível segredo em {relative}")
    return document


def main() -> int:
    document = validate()
    states: dict[str, int] = {}
    for item in document["decisions"]:
        states[item["state"]] = states.get(item["state"], 0) + 1
    print(f"OK: {len(document['decisions'])} decisões ({states}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
