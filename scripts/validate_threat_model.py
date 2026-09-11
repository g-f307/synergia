#!/usr/bin/env python3
"""Valida o threat model contra OpenAPI, matriz de acesso e evidências."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from scripts.validate_web_journey_map import (
        PUBLIC,
        _matrix_contracts,
        _openapi_operations,
    )
except ModuleNotFoundError:
    from validate_web_journey_map import (  # type: ignore[no-redef]
        PUBLIC,
        _matrix_contracts,
        _openapi_operations,
    )

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "security-risk-register.json"
MODEL = ROOT / "docs" / "threat-model.md"

REQUIRED_JOURNEYS = {
    "authentication-and-session",
    "upload-and-ingestion",
    "queries-and-reprocessing",
    "report-and-export",
    "notification-and-email-delivery",
    "human-approval",
    "identity-administration",
}
REQUIRED_TREATMENT_ISSUES = set(range(90, 97))
REQUIRED_THREAT_CLASSES = {"csrf", "ssrf", "xss"}
REQUIRED_OPERATIONS = {
    "authentication-and-session": {
        ("POST", "/auth/login"),
        ("POST", "/auth/refresh"),
        ("POST", "/auth/logout"),
        ("GET", "/me"),
    },
    "upload-and-ingestion": {
        ("POST", "/imports"),
        ("GET", "/imports/{execution_id}"),
        ("GET", "/imports/{execution_id}/validation-report"),
    },
    "queries-and-reprocessing": {
        ("GET", "/search"),
        ("GET", "/pending-items"),
        ("POST", "/executions/{execution_id}/reprocess"),
    },
    "report-and-export": {
        ("POST", "/reports"),
        ("GET", "/reports/{report_id}/versions/{version}"),
        ("GET", "/reports/{report_id}/versions/{version}/export"),
    },
    "notification-and-email-delivery": {
        ("GET", "/notifications"),
        ("PATCH", "/notifications/{notification_id}/read"),
        ("POST", "/notifications/read-all"),
    },
    "human-approval": {
        ("POST", "/pending-items/{pending_id}/approval"),
        ("POST", "/approvals/{request_id}/assign"),
        ("POST", "/approvals/{request_id}/approve"),
        ("POST", "/approvals/{request_id}/return"),
    },
    "identity-administration": {
        ("POST", "/admin/users"),
        ("PATCH", "/admin/users/{user_id}"),
        ("PUT", "/admin/access/users/{left_id}/roles/{right_id}"),
    },
}
LIKELIHOODS = {"unlikely", "possible", "likely"}
SEVERITIES = {"low", "medium", "high", "critical"}
DISPOSITIONS = {"mitigated", "accepted", "blocked", "transferred"}
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
INHERENT_MATRIX = {
    "unlikely": {
        "low": "low", "medium": "low", "high": "medium", "critical": "high"
    },
    "possible": {
        "low": "low", "medium": "medium", "high": "high", "critical": "critical"
    },
    "likely": {
        "low": "low", "medium": "high", "high": "high", "critical": "critical"
    },
}


def _non_empty_list(item: dict, field: str, subject: str) -> list:
    value = item.get(field)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{subject} sem {field}")
    return value


def validate() -> dict:
    document = json.loads(REGISTER.read_text(encoding="utf-8"))
    model_text = MODEL.read_text(encoding="utf-8")

    method = document.get("method", {})
    if set(method.get("likelihood", [])) != LIKELIHOODS:
        raise ValueError("Catálogo de probabilidade divergente")
    if set(method.get("impact", [])) != SEVERITIES:
        raise ValueError("Catálogo de impacto divergente")
    if set(method.get("severity", [])) != SEVERITIES:
        raise ValueError("Catálogo de severidade divergente")
    if set(method.get("dispositions", [])) != DISPOSITIONS:
        raise ValueError("Catálogo de decisões divergente")

    boundaries = _non_empty_list(document, "trust_boundaries", "Registro")
    boundary_ids = [item.get("id") for item in boundaries]
    if None in boundary_ids or len(boundary_ids) != len(set(boundary_ids)):
        raise ValueError("Fronteiras ausentes ou duplicadas")

    journeys = _non_empty_list(document, "journeys", "Registro")
    journey_ids = [item.get("id") for item in journeys]
    journey_names = {item.get("name") for item in journeys}
    if None in journey_ids or len(journey_ids) != len(set(journey_ids)):
        raise ValueError("Jornadas ausentes ou duplicadas")
    if journey_names != REQUIRED_JOURNEYS:
        raise ValueError(f"Cobertura de jornadas divergente: {journey_names}")

    openapi = _openapi_operations()
    contracts = _matrix_contracts()
    for journey in journeys:
        subject = f"Jornada {journey['id']}"
        _non_empty_list(journey, "actors", subject)
        _non_empty_list(journey, "assets", subject)
        _non_empty_list(journey, "threats", subject)
        used_boundaries = set(_non_empty_list(journey, "boundaries", subject))
        if unknown := used_boundaries - set(boundary_ids):
            raise ValueError(f"{subject} usa fronteira inexistente: {sorted(unknown)}")
        operations = _non_empty_list(journey, "operations", subject)
        operation_keys = {
            (operation.get("method"), operation.get("path"))
            for operation in operations
        }
        required = REQUIRED_OPERATIONS[journey["name"]]
        if missing := required - operation_keys:
            raise ValueError(
                f"{subject} sem operações obrigatórias: {sorted(missing)}"
            )
        for operation in operations:
            key = (operation.get("method"), operation.get("path"))
            if key not in openapi:
                raise ValueError(f"Operação OpenAPI inexistente em {subject}: {key}")
            expected = ("public", "public") if key in PUBLIC else contracts.get(key)
            if expected is None:
                raise ValueError(f"Operação sem matriz de acesso em {subject}: {key}")
            received = (operation.get("permission"), operation.get("scope"))
            if received != expected:
                raise ValueError(
                    f"Contrato divergente em {subject}: {key}; "
                    f"esperava {expected}, recebeu {received}"
                )

    risks = _non_empty_list(document, "risks", "Registro")
    risk_ids = [item.get("id") for item in risks]
    if None in risk_ids or len(risk_ids) != len(set(risk_ids)):
        raise ValueError("Riscos ausentes ou duplicados")
    covered_issues = set()
    covered_threat_classes = {
        str(risk.get("threat_class", "")).lower() for risk in risks
    }
    for risk in risks:
        subject = f"Risco {risk['id']}"
        if risk.get("journey") not in journey_ids:
            raise ValueError(f"{subject} aponta para jornada inexistente")
        if risk.get("likelihood") not in LIKELIHOODS:
            raise ValueError(f"{subject} possui probabilidade inválida")
        if risk.get("impact") not in SEVERITIES:
            raise ValueError(f"{subject} possui impacto inválido")
        inherent = risk.get("inherent_severity")
        residual = risk.get("residual_severity")
        if inherent not in SEVERITIES or residual not in SEVERITIES:
            raise ValueError(f"{subject} possui severidade inválida")
        expected_inherent = INHERENT_MATRIX[risk["likelihood"]][risk["impact"]]
        if inherent != expected_inherent:
            raise ValueError(
                f"{subject} possui severidade inerente divergente: "
                f"esperava {expected_inherent}, recebeu {inherent}"
            )
        if SEVERITY_RANK[residual] > SEVERITY_RANK[inherent]:
            raise ValueError(f"{subject} possui residual maior que o inerente")
        disposition = risk.get("disposition")
        if disposition not in DISPOSITIONS:
            raise ValueError(f"{subject} possui decisão inválida")
        _non_empty_list(risk, "controls", subject)
        evidence = _non_empty_list(risk, "evidence", subject)
        if not risk.get("owner") or not risk.get("treatment_issue"):
            raise ValueError(f"{subject} sem responsável ou issue")
        covered_issues.add(risk["treatment_issue"])
        for relative in evidence:
            path = Path(relative)
            if path.is_absolute() or not (ROOT / path).is_file():
                raise ValueError(f"Evidência inexistente em {subject}: {relative}")
        if disposition == "accepted" and not risk.get("rationale"):
            raise ValueError(f"{subject} aceito sem justificativa")
        if disposition == "blocked" and not risk.get("decision"):
            raise ValueError(f"{subject} bloqueado sem decisão")
        if disposition == "transferred" and (
            not risk.get("target_stage") or not risk.get("reopen_condition")
        ):
            raise ValueError(f"{subject} transferido sem etapa ou retomada")
        if risk["id"] not in model_text:
            raise ValueError(f"{subject} ausente no documento narrativo")

    applicability = document.get("applicability_decisions", [])
    if not isinstance(applicability, list):
        raise ValueError("Decisões de aplicabilidade inválidas")
    for decision in applicability:
        threat_class = str(decision.get("threat_class", "")).lower()
        if decision.get("status") != "not-applicable":
            raise ValueError(f"Decisão de aplicabilidade inválida: {threat_class}")
        if not decision.get("rationale") or not decision.get("reopen_condition"):
            raise ValueError(
                f"Ameaça não aplicável sem justificativa ou retomada: {threat_class}"
            )
        if not decision.get("target_stage"):
            raise ValueError(f"Ameaça não aplicável sem etapa: {threat_class}")
        covered_threat_classes.add(threat_class)

    if missing := REQUIRED_THREAT_CLASSES - covered_threat_classes:
        raise ValueError(f"Classes de ameaça obrigatórias ausentes: {sorted(missing)}")

    if missing := REQUIRED_TREATMENT_ISSUES - covered_issues:
        raise ValueError(f"Issues da Etapa 5 sem risco relacionado: {sorted(missing)}")
    for issue in REQUIRED_TREATMENT_ISSUES:
        if f"#{issue}" not in model_text:
            raise ValueError(f"Issue #{issue} ausente no documento narrativo")
    return document


def main() -> int:
    document = validate()
    print(
        f"OK: {len(document['journeys'])} jornadas, "
        f"{len(document['trust_boundaries'])} fronteiras e "
        f"{len(document['risks'])} riscos rastreados."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
