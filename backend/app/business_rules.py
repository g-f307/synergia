from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).with_name("model") / "business_rules.json"
REQUIRED_RULES = {
    "oqc_pass",
    "oqc_pending",
    "oqc_hold",
    "long_term_hold",
    "rework",
    "ship_block",
    "pre_release_pending",
    "post_release_hold",
    "aging",
    "container_impact",
    "missing_reason",
    "source_divergence",
}
HOLD_STATES = {"hold", "oqc_hold", "retained", "long_term_hold"}
PENDING_STATES = {"pending", "open", "in_progress", "oqc_pending"}
PASS_STATES = {"approved", "released", "oqc_pass"}
REWORK_STATES = {"rework"}
SHIP_BLOCK_STATES = {"ship_block"}
TERMINAL_STATES = {
    "approved",
    "released",
    "oqc_pass",
    "completed",
    "closed",
    "cancelled",
}
DIVERGENCE_CODES = {
    "source_divergence",
    "relationship_divergence",
    "conflicting_relationship",
    "ambiguous_relationship",
}


class BusinessRuleError(ValueError):
    """Raised when the rule catalog or classification input is invalid."""


def load_rule_catalog(path: Path = RULES_PATH) -> dict[str, Any]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BusinessRuleError(
            f"Não foi possível carregar o catálogo: {path}"
        ) from exc
    if not isinstance(catalog, dict) or not isinstance(catalog.get("version"), str):
        raise BusinessRuleError("Catálogo de regras sem versão válida")
    thresholds = catalog.get("thresholds")
    rules = catalog.get("rules")
    if not isinstance(thresholds, dict) or not isinstance(rules, dict):
        raise BusinessRuleError("Catálogo de regras incompleto")
    missing = REQUIRED_RULES - rules.keys()
    if missing:
        raise BusinessRuleError(f"Regras obrigatórias ausentes: {sorted(missing)}")
    for rule_id, rule in rules.items():
        if not isinstance(rule, dict):
            raise BusinessRuleError(f"Regra inválida: {rule_id}")
        if not isinstance(rule.get("priority"), int) or rule["priority"] < 0:
            raise BusinessRuleError(f"Prioridade inválida: {rule_id}")
        if not isinstance(rule.get("responsible_area"), str):
            raise BusinessRuleError(f"Área responsável inválida: {rule_id}")
    for name in (
        "long_term_hold_days",
        "aging_days",
        "aging_priority_bonus",
        "container_priority_bonus",
    ):
        if not isinstance(thresholds.get(name), int) or thresholds[name] < 0:
            raise BusinessRuleError(f"Limite inválido: {name}")
    return catalog


RULE_CATALOG = load_rule_catalog()


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise BusinessRuleError(
                f"Data inválida para classificação: {value!r}"
            ) from exc


def _occurred_at(fact: dict[str, Any]) -> str | None:
    for field in ("event_at", "created_at", "decided_at", "inspection_date"):
        if fact.get(field) not in (None, ""):
            parsed = _as_date(fact[field])
            return parsed.isoformat() if parsed else None
    return None


def _is_active(fact: dict[str, Any]) -> bool:
    if isinstance(fact.get("active"), bool):
        return fact["active"]
    if fact.get("resolved_at") not in (None, ""):
        return False
    return str(fact.get("status", "")).lower() not in TERMINAL_STATES


def _reason(fact: dict[str, Any]) -> str | None:
    for field in ("reason", "hold_reason", "pending_reason"):
        value = fact.get(field)
        if value not in (None, ""):
            return str(value)
    return None


def _entity(fact: dict[str, Any], workorder: str) -> tuple[str, str]:
    if fact.get("serial_number") not in (None, ""):
        return "serial", str(fact["serial_number"])
    if fact.get("lot_number") not in (None, ""):
        return "lot", str(fact["lot_number"])
    return "workorder", workorder


def _fact_categories(
    fact: dict[str, Any],
    workorder: dict[str, Any],
    *,
    age_days: int,
    occurred_date: date,
    release_date: date | None,
    catalog: dict[str, Any],
) -> tuple[set[str], bool]:
    status = str(fact.get("status", "")).lower()
    active = _is_active(fact)
    hold = fact.get("hold_flag") is True or status in HOLD_STATES
    pending = status in PENDING_STATES
    rework = fact.get("rework_flag") is True or status in REWORK_STATES
    ship_block = fact.get("ship_block_flag") is True or status in SHIP_BLOCK_STATES
    actionable = hold or pending or rework or ship_block
    thresholds = catalog["thresholds"]
    categories: set[str] = set()
    if fact.get("oqc_flag") is True or status in PASS_STATES:
        categories.add("oqc_pass")
    if pending:
        categories.add("oqc_pending")
    if hold:
        categories.add("oqc_hold")
    if status == "long_term_hold" or (
        hold and age_days >= thresholds["long_term_hold_days"]
    ):
        categories.add("long_term_hold")
    if rework:
        categories.add("rework")
    if ship_block:
        categories.add("ship_block")
    released = workorder.get("released_quantity")
    if active and (pending or hold):
        if release_date is not None:
            if occurred_date < release_date:
                categories.add("pre_release_pending")
            elif hold:
                categories.add("post_release_hold")
        elif released == 0:
            categories.add("pre_release_pending")
        elif released is not None and hold:
            categories.add("post_release_hold")
    if active and actionable and age_days >= thresholds["aging_days"]:
        categories.add("aging")
    if active and actionable and fact.get("container_number") not in (None, ""):
        categories.add("container_impact")
    missing_reason = active and actionable and _reason(fact) is None
    if missing_reason:
        categories.add("missing_reason")
    return categories, missing_reason


def _priority(
    rule_id: str,
    *,
    age_days: int,
    has_container: bool,
    active: bool,
    catalog: dict[str, Any],
) -> tuple[int, list[dict[str, Any]]]:
    rule = catalog["rules"][rule_id]
    score = rule["priority"]
    factors = [{"factor": "rule_base", "value": rule["priority"]}]
    thresholds = catalog["thresholds"]
    if active and age_days >= thresholds["aging_days"]:
        bonus = thresholds["aging_priority_bonus"]
        score += bonus
        factors.append({"factor": "aging", "value": bonus})
    if active and has_container:
        bonus = thresholds["container_priority_bonus"]
        score += bonus
        factors.append({"factor": "container_impact", "value": bonus})
    return score, factors


def _priority_label(score: int) -> str:
    if score >= 90:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "normal"
    return "low"


def _classification_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _container_counts(
    facts: list[dict[str, Any]], workorder: dict[str, Any]
) -> dict[str, dict[str, int]]:
    serials: dict[str, set[str]] = {}
    affected: dict[str, set[str]] = {}
    for fact in facts:
        container = fact.get("container_number")
        serial = fact.get("serial_number")
        if container in (None, "") or serial in (None, ""):
            continue
        container = str(container)
        serial = str(serial)
        serials.setdefault(container, set()).add(serial)
        status = str(fact.get("status", "")).lower()
        if _is_active(fact) and (
            fact.get("hold_flag") is True
            or fact.get("rework_flag") is True
            or fact.get("ship_block_flag") is True
            or status
            in HOLD_STATES | PENDING_STATES | REWORK_STATES | SHIP_BLOCK_STATES
        ):
            affected.setdefault(container, set()).add(serial)
    return {
        container: {
            "serial_count": len(values),
            "affected_serial_count": len(affected.get(container, set())),
        }
        for container, values in serials.items()
    }


def _event(
    *,
    rule_id: str,
    fact: dict[str, Any],
    workorder: dict[str, Any],
    run_id: str,
    classified_at: str,
    as_of: date,
    missing_reason: bool,
    container_counts: dict[str, dict[str, int]],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    workorder_number = str(workorder["workorder_number"])
    entity_type, entity_id = _entity(fact, workorder_number)
    occurred_at = _occurred_at(fact)
    occurred_date = _as_date(occurred_at) if occurred_at else as_of
    age_days = max((as_of - occurred_date).days, 0)
    active = _is_active(fact) and rule_id != "oqc_pass"
    container = fact.get("container_number")
    priority, factors = _priority(
        rule_id,
        age_days=age_days,
        has_container=container not in (None, ""),
        active=active,
        catalog=catalog,
    )
    organizations = workorder.get("organization_codes", [])
    organization = fact.get("responsible_organization")
    if organization in (None, "") and len(organizations) == 1:
        organization = organizations[0]
    rule = catalog["rules"][rule_id]
    area = fact.get("responsible_area") or rule["responsible_area"]
    identity = {
        "run_id": run_id,
        "rule_id": rule_id,
        "workorder_number": workorder_number,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source": fact.get("source"),
        "execution_id": fact.get("execution_id"),
        "source_file_id": fact.get("source_file_id"),
        "sheet": fact.get("sheet"),
        "row": fact.get("row"),
    }
    result = {
        "classification_id": _classification_id(identity),
        "run_id": run_id,
        "classified_at": classified_at,
        "rule_catalog_version": catalog["version"],
        "rule_id": rule_id,
        "rule_description": rule["description"],
        "justification": _reason(fact) or rule["description"],
        "state": "active" if active else "closed",
        "workorder_number": workorder_number,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "lot_number": fact.get("lot_number"),
        "serial_number": fact.get("serial_number"),
        "container_number": container,
        "reason": _reason(fact),
        "data_quality": "partial" if missing_reason else "complete",
        "occurred_at": occurred_at,
        "age_days": age_days,
        "responsible_organization": organization,
        "responsible_area": area,
        "priority_score": priority,
        "priority": _priority_label(priority),
        "priority_factors": factors,
        "evidence": {
            key: fact.get(key)
            for key in (
                "source",
                "execution_id",
                "source_file_id",
                "sheet",
                "row",
                "status",
                "oqc_flag",
                "hold_flag",
                "rework_flag",
                "ship_block_flag",
            )
            if fact.get(key) is not None
        },
    }
    if container not in (None, ""):
        impact = container_counts.get(str(container), {})
        result["container_impact"] = {
            "serial_count": impact.get("serial_count", 0),
            "affected_serial_count": impact.get("affected_serial_count", 0),
            "partially_affected": (
                0
                < impact.get("affected_serial_count", 0)
                < impact.get("serial_count", 0)
            ),
        }
    return result


def _divergence_events(
    consolidation: dict[str, Any],
    workorders: dict[str, dict[str, Any]],
    *,
    run_id: str,
    classified_at: str,
    catalog: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    rule = catalog["rules"]["source_divergence"]
    for issue in consolidation.get("issues", []):
        if issue.get("code") not in DIVERGENCE_CODES:
            continue
        report.append(deepcopy(issue))
        workorder_number = issue.get("workorder_number")
        if workorder_number not in workorders:
            continue
        organizations = workorders[workorder_number].get("organization_codes", [])
        identity = {
            "run_id": run_id,
            "rule_id": "source_divergence",
            "workorder_number": workorder_number,
            "issue": issue,
        }
        events.append(
            {
                "classification_id": _classification_id(identity),
                "run_id": run_id,
                "classified_at": classified_at,
                "rule_catalog_version": catalog["version"],
                "rule_id": "source_divergence",
                "rule_description": rule["description"],
                "justification": rule["description"],
                "state": "active",
                "workorder_number": workorder_number,
                "entity_type": "workorder",
                "entity_id": workorder_number,
                "lot_number": None,
                "serial_number": None,
                "container_number": None,
                "reason": issue.get("code"),
                "data_quality": "partial",
                "occurred_at": None,
                "age_days": 0,
                "responsible_organization": (
                    organizations[0] if len(organizations) == 1 else None
                ),
                "responsible_area": rule["responsible_area"],
                "priority_score": rule["priority"],
                "priority": _priority_label(rule["priority"]),
                "priority_factors": [
                    {"factor": "rule_base", "value": rule["priority"]}
                ],
                "evidence": deepcopy(issue),
            }
        )
    return events, report


def _entity_summary(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for event in events:
        workorder = event["workorder_number"]
        keys = {(workorder, "workorder", workorder)}
        if event.get("lot_number") not in (None, ""):
            keys.add((workorder, "lot", str(event["lot_number"])))
        if event.get("serial_number") not in (None, ""):
            keys.add((workorder, "serial", str(event["serial_number"])))
        if event["entity_type"] != "workorder":
            keys.add((workorder, event["entity_type"], event["entity_id"]))
        for key in keys:
            grouped.setdefault(key, []).append(event)
    return [
        {
            "workorder_number": key[0],
            "entity_type": key[1],
            "entity_id": key[2],
            "state": (
                "active"
                if any(event["state"] == "active" for event in values)
                else "closed"
            ),
            "active_rule_ids": sorted(
                {
                    event["rule_id"]
                    for event in values
                    if event["state"] == "active"
                }
            ),
            "closed_rule_ids": sorted(
                {
                    event["rule_id"]
                    for event in values
                    if event["state"] == "closed"
                }
            ),
            "partially_released": next(
                (
                    event.get("partially_released")
                    for event in values
                    if event.get("partially_released") is not None
                ),
                None,
            ),
            "priority_score": max(
                (event["priority_score"] for event in values), default=0
            ),
        }
        for key, values in sorted(grouped.items())
    ]


def _active_queue(events: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for event in events:
        if event["state"] != "active":
            continue
        key = (
            event["workorder_number"],
            event["entity_type"],
            event["entity_id"],
        )
        grouped.setdefault(key, []).append(event)
    queue: list[dict[str, Any]] = []
    for key, values in grouped.items():
        oldest = min(
            (event["occurred_at"] for event in values if event["occurred_at"]),
            default=None,
        )
        priority_score = max(event["priority_score"] for event in values)
        primary = min(
            (
                event
                for event in values
                if event["priority_score"] == priority_score
            ),
            key=lambda event: event["rule_id"],
        )
        identity = {
            "run_id": run_id,
            "workorder_number": key[0],
            "entity_type": key[1],
            "entity_id": key[2],
        }
        queue.append(
            {
                "queue_item_id": _classification_id(identity),
                "run_id": run_id,
                "workorder_number": key[0],
                "entity_type": key[1],
                "entity_id": key[2],
                "lot_number": primary.get("lot_number"),
                "serial_number": primary.get("serial_number"),
                "container_number": primary.get("container_number"),
                "state": "active",
                "rule_ids": sorted({event["rule_id"] for event in values}),
                "primary_rule_id": primary["rule_id"],
                "classification_ids": sorted(
                    event["classification_id"] for event in values
                ),
                "occurred_at": oldest,
                "age_days": max(event["age_days"] for event in values),
                "priority_score": priority_score,
                "priority": _priority_label(priority_score),
                "responsible_organizations": sorted(
                    {
                        str(event["responsible_organization"])
                        for event in values
                        if event["responsible_organization"] not in (None, "")
                    }
                ),
                "responsible_areas": sorted(
                    {event["responsible_area"] for event in values}
                ),
                "data_quality": (
                    "partial"
                    if any(event["data_quality"] == "partial" for event in values)
                    else "complete"
                ),
            }
        )
    queue.sort(
        key=lambda item: (
            item["occurred_at"] is None,
            item["occurred_at"] or "9999-12-31",
            -item["priority_score"],
            item["workorder_number"],
            item["entity_type"],
            item["entity_id"],
        )
    )
    return queue


def classify(
    consolidation: dict[str, Any],
    *,
    run_id: str,
    classified_at: str,
    previous_history: list[dict[str, Any]] | None = None,
    catalog: dict[str, Any] = RULE_CATALOG,
) -> dict[str, Any]:
    """Apply deterministic rules without mutating consolidation or prior history."""
    if not run_id.strip():
        raise BusinessRuleError("run_id é obrigatório")
    as_of = _as_date(classified_at)
    if as_of is None:
        raise BusinessRuleError("classified_at é obrigatório")
    workorders = {
        str(item["workorder_number"]): item
        for item in consolidation.get("workorders", [])
    }
    current: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    for workorder_number in sorted(workorders):
        workorder = workorders[workorder_number]
        facts = sorted(
            workorder.get("classification_facts", []),
            key=lambda fact: (
                str(fact.get("source", "")),
                str(fact.get("execution_id", "")),
                str(fact.get("source_file_id", "")),
                str(fact.get("sheet", "")),
                int(fact.get("row", 0)),
            ),
        )
        release_dates = [
            parsed
            for fact in facts
            if (parsed := _as_date(fact.get("released_at"))) is not None
        ]
        release_date = min(release_dates, default=None)
        counts = _container_counts(facts, workorder)
        for fact in facts:
            occurred = _occurred_at(fact)
            occurred_date = _as_date(occurred) if occurred else as_of
            age_days = max((as_of - occurred_date).days, 0)
            categories, missing_reason = _fact_categories(
                fact,
                workorder,
                age_days=age_days,
                occurred_date=occurred_date,
                release_date=release_date,
                catalog=catalog,
            )
            for rule_id in sorted(REQUIRED_RULES - {"source_divergence"}):
                matched = rule_id in categories
                evaluations.append(
                    {
                        "workorder_number": workorder_number,
                        "source": fact.get("source"),
                        "execution_id": fact.get("execution_id"),
                        "source_file_id": fact.get("source_file_id"),
                        "sheet": fact.get("sheet"),
                        "row": fact.get("row"),
                        "rule_id": rule_id,
                        "rule_catalog_version": catalog["version"],
                        "result": "matched" if matched else "not_matched",
                        "justification": (
                            catalog["rules"][rule_id]["description"]
                            if matched
                            else "A evidência não satisfez os critérios da regra"
                        ),
                    }
                )
            for rule_id in sorted(categories):
                event = _event(
                    rule_id=rule_id,
                    fact=fact,
                    workorder=workorder,
                    run_id=run_id,
                    classified_at=classified_at,
                    as_of=as_of,
                    missing_reason=missing_reason,
                    container_counts=counts,
                    catalog=catalog,
                )
                event["partially_released"] = workorder.get("partially_released")
                current.append(event)
    divergence_events, divergence_report = _divergence_events(
        consolidation,
        workorders,
        run_id=run_id,
        classified_at=classified_at,
        catalog=catalog,
    )
    current.extend(divergence_events)
    for workorder_number in sorted(workorders):
        matched = any(
            issue.get("workorder_number") == workorder_number
            and issue.get("code") in DIVERGENCE_CODES
            for issue in consolidation.get("issues", [])
        )
        evaluations.append(
            {
                "workorder_number": workorder_number,
                "rule_id": "source_divergence",
                "rule_catalog_version": catalog["version"],
                "result": "matched" if matched else "not_matched",
                "justification": (
                    catalog["rules"]["source_divergence"]["description"]
                    if matched
                    else "Nenhuma divergência entre fontes foi identificada"
                ),
            }
        )
    current.sort(key=lambda item: item["classification_id"])
    active = _active_queue(current, run_id)
    history = deepcopy(previous_history or [])
    history.extend(deepcopy(current))
    return {
        "run_id": run_id,
        "classified_at": classified_at,
        "rule_catalog_version": catalog["version"],
        "active_items": active,
        "entities": _entity_summary(current),
        "current_classifications": current,
        "rule_evaluations": evaluations,
        "history": history,
        "divergence_report": divergence_report,
    }
