from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from app.business_rules import RULE_CATALOG, BusinessRuleError, classify
from app.consolidation import QUANTITY_FIELDS, consolidate


class ProcessingError(ValueError):
    """Raised when normalized records cannot safely enter processing."""


def _validated_records(
    records: Iterable[Mapping[str, Any]], execution_id: str
) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for record in records:
        if record.get("execution_id") != execution_id:
            raise ProcessingError(
                "Todos os registros normalizados devem pertencer à execução atual"
            )
        if not isinstance(record.get("values"), Mapping):
            raise ProcessingError("Registro normalizado sem valores rastreáveis")
        # Consolidation treats normalized records as immutable. A shallow copy
        # protects the top-level contract without duplicating every values/
        # provenance payload at reference-volume scale.
        validated.append(dict(record))
    return validated


def process_normalized_records(
    records: Iterable[Mapping[str, Any]],
    *,
    execution_id: str,
    classified_at: str,
    catalog: dict[str, Any] = RULE_CATALOG,
    on_consolidated: Callable[[], None] | None = None,
    defer_rule_details: bool = False,
) -> dict[str, Any]:
    """Consolidate and classify eligible normalized records from one execution."""
    eligible = _validated_records(records, execution_id)
    consolidation = consolidate(eligible, isolate_failures=True)
    if on_consolidated is not None:
        on_consolidated()
    classifiable_workorders = []
    deferred_rule_counts: Counter[str] = Counter()
    deferred_classification_count = 0
    deferred_active_count = 0
    for workorder in consolidation["workorders"]:
        workorder_number = workorder["workorder_number"]
        workorder_issues = [
            issue
            for issue in consolidation["issues"]
            if issue.get("workorder_number") == workorder_number
        ]
        try:
            workorder_classifications = classify(
                {"workorders": [workorder], "issues": workorder_issues},
                run_id=execution_id,
                classified_at=classified_at,
                catalog=catalog,
            )
        except BusinessRuleError as exc:
            failure = {
                "code": "workorder_processing_failed",
                "stage": "classification",
                "workorder_number": workorder_number,
                "reason": str(exc),
            }
            consolidation["failed_workorders"].append(failure)
            consolidation["issues"].append(failure)
            continue
        classifiable_workorders.append(workorder)
        if defer_rule_details:
            events = workorder_classifications["current_classifications"]
            deferred_rule_counts.update(item["rule_id"] for item in events)
            deferred_classification_count += len(events)
            deferred_active_count += len(workorder_classifications["active_items"])
    consolidation["workorders"] = classifiable_workorders
    consolidation["workorder_count"] = len(classifiable_workorders)
    consolidation["failed_workorder_count"] = len(consolidation["failed_workorders"])
    consolidation["issue_count"] = len(consolidation["issues"])
    if defer_rule_details:
        classifications = {
            "run_id": execution_id,
            "classified_at": classified_at,
            "rule_catalog_version": catalog["version"],
            "active_items": [],
            "entities": [],
            "current_classifications": [],
            "rule_evaluations": [],
            "history": [],
            "divergence_report": [],
            "rule_details_deferred": True,
            "rule_catalog": catalog,
        }
    else:
        classifications = classify(
            consolidation,
            run_id=execution_id,
            classified_at=classified_at,
            catalog=catalog,
        )
    workorders = consolidation["workorders"]
    rule_counts = (
        deferred_rule_counts
        if defer_rule_details
        else Counter(
            item["rule_id"] for item in classifications["current_classifications"]
        )
    )
    consolidated_quantities = {}
    for field in QUANTITY_FIELDS:
        known = [item[field] for item in workorders if item[field] is not None]
        consolidated_quantities[field] = {
            "known_workorders": len(known),
            "total": sum(known) if known else None,
        }
    summary = {
        "eligible_normalized_records": len(eligible),
        "consolidated_workorders": len(workorders),
        "consolidated_lots": len(
            {lot for item in workorders for lot in item["lot_numbers"]}
        ),
        "consolidated_serials": len(
            {serial for item in workorders for serial in item["serial_numbers"]}
        ),
        "consolidated_organizations": len(
            {
                organization
                for item in workorders
                for organization in item["organization_codes"]
            }
        ),
        "consolidation_issues": consolidation["issue_count"],
        "failed_workorders": consolidation["failed_workorder_count"],
        "classifications": (
            deferred_classification_count
            if defer_rule_details
            else len(classifications["current_classifications"])
        ),
        "active_pending_items": (
            deferred_active_count
            if defer_rule_details
            else len(classifications["active_items"])
        ),
        "classifications_by_rule": dict(sorted(rule_counts.items())),
        "consolidated_quantities": consolidated_quantities,
    }
    return {
        "execution_id": execution_id,
        "rule_catalog_version": classifications["rule_catalog_version"],
        "summary": summary,
        "consolidation": consolidation,
        "classifications": classifications,
    }
