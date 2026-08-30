from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

SOURCE_ORDER = ("N-FP", "GMES/OQC", "OWM", "TMS")
IDENTIFIER_FIELDS = (
    "demand_id",
    "lot_number",
    "model",
    "serial_number",
    "container_number",
    "organization_code",
    "workorder_type",
)
QUANTITY_FIELDS = (
    "planned_quantity",
    "produced_quantity",
    "received_quantity",
    "released_quantity",
    "pending_quantity",
    "retained_quantity",
)
CLASSIFICATION_FIELDS = (
    "status",
    "oqc_flag",
    "hold_flag",
    "rework_flag",
    "ship_block_flag",
    "reason",
    "hold_reason",
    "pending_reason",
    "event_at",
    "created_at",
    "decided_at",
    "inspection_date",
    "released_at",
    "resolved_at",
    "active",
    "responsible_organization",
    "responsible_area",
)
QUANTITY_SOURCE_PRIORITY = {
    "planned_quantity": ("N-FP", "GMES/OQC", "OWM", "TMS"),
    "produced_quantity": ("GMES/OQC", "N-FP", "OWM", "TMS"),
    "received_quantity": ("OWM", "GMES/OQC", "TMS", "N-FP"),
    "released_quantity": ("OWM", "GMES/OQC", "TMS", "N-FP"),
    "pending_quantity": ("OWM", "GMES/OQC", "N-FP", "TMS"),
    "retained_quantity": ("OWM", "GMES/OQC", "TMS", "N-FP"),
}


class ConsolidationError(ValueError):
    """Raised when normalized input cannot be consolidated safely."""


def _source_key(source: str) -> tuple[int, str]:
    try:
        return SOURCE_ORDER.index(source), source
    except ValueError:
        return len(SOURCE_ORDER), source


def _record_key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _source_key(str(record.get("source", ""))),
        str(record.get("execution_id", "")),
        str(record.get("source_file_id", "")),
        str(record.get("sheet", "")),
        int(record.get("row", 0)),
    )


def _record_identity(record: Mapping[str, Any]) -> tuple[Any, ...] | None:
    fields = ("source", "execution_id", "source_file_id", "sheet", "row")
    if any(record.get(field) is None for field in fields):
        return None
    return tuple(record[field] for field in fields)


def _value(record: Mapping[str, Any], field: str) -> Any:
    values = record.get("values", {})
    return values.get(field) if isinstance(values, Mapping) else None


def _nonempty(value: Any) -> bool:
    return value is not None and value != ""


def _quantity(value: Any, field: str) -> int | None:
    if not _nonempty(value):
        return None
    if isinstance(value, bool):
        raise ConsolidationError(f"{field} deve ser uma quantidade não negativa")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ConsolidationError(f"{field} inválida: {value!r}") from exc
    if number < 0 or number != number.to_integral_value():
        raise ConsolidationError(
            f"{field} deve ser uma quantidade inteira não negativa"
        )
    return int(number)


def _provenance(record: Mapping[str, Any], field: str, value: Any) -> dict[str, Any]:
    return {
        "source": str(record.get("source", "")),
        "execution_id": record.get("execution_id"),
        "source_file_id": record.get("source_file_id"),
        "sheet": record.get("sheet"),
        "row": record.get("row"),
        "field": field,
        "value": value,
    }


def _index_unique(
    records: Sequence[Mapping[str, Any]], field: str
) -> tuple[dict[str, str], set[str], dict[str, set[str]]]:
    candidates: dict[str, set[str]] = defaultdict(set)
    for record in records:
        workorder = _value(record, "workorder_number")
        identifier = _value(record, field)
        if _nonempty(workorder) and _nonempty(identifier):
            candidates[str(identifier)].add(str(workorder))
    ambiguous = {key for key, values in candidates.items() if len(values) > 1}
    return (
        {
            key: next(iter(values))
            for key, values in candidates.items()
            if len(values) == 1
        },
        ambiguous,
        candidates,
    )


def _relationship_conflicts(
    record: Mapping[str, Any],
    candidates: Mapping[str, Mapping[str, set[str]]],
) -> list[dict[str, Any]]:
    direct = _value(record, "workorder_number")
    if not _nonempty(direct):
        return []
    workorder = str(direct)
    conflicts: list[dict[str, Any]] = []
    for field in ("demand_id", "serial_number", "lot_number"):
        identifier = _value(record, field)
        if not _nonempty(identifier):
            continue
        related = candidates[field].get(str(identifier), set()) - {workorder}
        if related:
            conflicts.append(
                {
                    "code": "conflicting_relationship",
                    "source": record.get("source"),
                    "execution_id": record.get("execution_id"),
                    "source_file_id": record.get("source_file_id"),
                    "sheet": record.get("sheet"),
                    "row": record.get("row"),
                    "workorder_number": workorder,
                    "field": field,
                    "value": str(identifier),
                    "conflicting_workorders": sorted(related),
                }
            )
    return conflicts


def _resolve_workorder(
    record: Mapping[str, Any], indexes: Mapping[str, Mapping[str, str]]
) -> str | None:
    direct = _value(record, "workorder_number")
    if _nonempty(direct):
        return str(direct)
    matches: set[str] = set()
    for field in ("demand_id", "serial_number", "lot_number"):
        identifier = _value(record, field)
        if _nonempty(identifier) and str(identifier) in indexes[field]:
            matches.add(indexes[field][str(identifier)])
    return next(iter(matches)) if len(matches) == 1 else None


def _identifier_values(
    records: Sequence[Mapping[str, Any]], field: str
) -> tuple[list[str], list[dict[str, Any]]]:
    seen: set[str] = set()
    values: list[str] = []
    origins: list[dict[str, Any]] = []
    for record in records:
        value = _value(record, field)
        if not _nonempty(value):
            continue
        text = str(value)
        origins.append(_provenance(record, field, text))
        if text not in seen:
            seen.add(text)
            values.append(text)
    return sorted(values), origins


def _classification_facts(
    records: Sequence[Mapping[str, Any]], workorder: str
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for record in records:
        values = record.get("values", {})
        if not isinstance(values, Mapping):
            continue
        observed = {
            field: values.get(field)
            for field in CLASSIFICATION_FIELDS
            if _nonempty(values.get(field)) or values.get(field) is False
        }
        if not observed:
            continue
        facts.append(
            {
                "source": record.get("source"),
                "execution_id": record.get("execution_id"),
                "source_file_id": record.get("source_file_id"),
                "sheet": record.get("sheet"),
                "row": record.get("row"),
                "workorder_number": workorder,
                "lot_number": values.get("lot_number"),
                "serial_number": values.get("serial_number"),
                "container_number": values.get("container_number"),
                **observed,
            }
        )
    return facts


def _quantity_observations(
    records: Sequence[Mapping[str, Any]], field: str
) -> tuple[int | None, list[dict[str, Any]], dict[str, int]]:
    by_source: dict[str, int] = defaultdict(int)
    origins: list[dict[str, Any]] = []
    for record in records:
        raw = _value(record, field)
        value = _quantity(raw, field)
        if value is None:
            continue
        source = str(record.get("source", ""))
        by_source[source] += value
        origins.append(_provenance(record, field, value))
    selected_source = next(
        (
            source
            for source in QUANTITY_SOURCE_PRIORITY[field]
            if source in by_source
        ),
        min(by_source, key=_source_key) if by_source else None,
    )
    return (
        by_source[selected_source] if selected_source is not None else None,
        origins,
        dict(sorted(by_source.items(), key=lambda item: _source_key(item[0]))),
    )


def _divergences(
    workorder: str,
    identifiers: Mapping[str, list[str]],
    quantities_by_source: Mapping[str, Mapping[str, int]],
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for field in ("demand_id", "model", "organization_code", "workorder_type"):
        values = identifiers[field]
        if len(values) > 1:
            issues.append(
                {
                    "code": "source_divergence",
                    "workorder_number": workorder,
                    "field": field,
                    "values": values,
                }
            )
    lots_by_serial: dict[str, set[str]] = defaultdict(set)
    for record in records:
        serial = _value(record, "serial_number")
        lot = _value(record, "lot_number")
        if _nonempty(serial) and _nonempty(lot):
            lots_by_serial[str(serial)].add(str(lot))
    for serial, lots in sorted(lots_by_serial.items()):
        if len(lots) > 1:
            issues.append(
                {
                    "code": "relationship_divergence",
                    "workorder_number": workorder,
                    "field": "lot_number",
                    "serial_number": serial,
                    "values": sorted(lots),
                }
            )
    for field, source_values in quantities_by_source.items():
        if len(set(source_values.values())) > 1:
            issues.append(
                {
                    "code": "source_divergence",
                    "workorder_number": workorder,
                    "field": field,
                    "values_by_source": source_values,
                }
            )
    return issues


def _consolidate_workorder(
    workorder: str, records: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sources = sorted(
        {str(record.get("source", "")) for record in records}, key=_source_key
    )
    identifiers: dict[str, list[str]] = {}
    provenance: dict[str, list[dict[str, Any]]] = {
        "workorder_number": [
            _provenance(record, "workorder_number", workorder)
            for record in records
            if _nonempty(_value(record, "workorder_number"))
        ]
    }
    for field in IDENTIFIER_FIELDS:
        identifiers[field], provenance[field] = _identifier_values(records, field)

    quantities: dict[str, int | None] = {}
    quantities_by_source: dict[str, dict[str, int]] = {}
    selected_quantity_sources: dict[str, str | None] = {}
    for field in QUANTITY_FIELDS:
        quantities[field], provenance[field], quantities_by_source[field] = (
            _quantity_observations(records, field)
        )
        selected_quantity_sources[field] = next(
            (
                source
                for source in QUANTITY_SOURCE_PRIORITY[field]
                if source in quantities_by_source[field]
            ),
            min(quantities_by_source[field], key=_source_key)
            if quantities_by_source[field]
            else None,
        )

    held_serials = {
        str(_value(record, "serial_number"))
        for record in records
        if _nonempty(_value(record, "serial_number"))
        and (
            _value(record, "hold_flag") is True
            or _value(record, "status") in {"hold", "retained"}
        )
    }
    explicit_retained = quantities["retained_quantity"]
    quantities["retained_quantity"] = (
        max(explicit_retained or 0, len(held_serials))
        if explicit_retained is not None or held_serials
        else None
    )
    explicit_pending = quantities["pending_quantity"]
    calculated_pending = (
        max(quantities["planned_quantity"] - quantities["released_quantity"], 0)
        if quantities["planned_quantity"] is not None
        and quantities["released_quantity"] is not None
        else None
    )
    pending_candidates = [
        value for value in (explicit_pending, calculated_pending) if value is not None
    ]
    quantities["pending_quantity"] = (
        max(pending_candidates) if pending_candidates else None
    )
    partial_release = (
        0 < quantities["released_quantity"] < quantities["received_quantity"]
        if quantities["received_quantity"] is not None
        and quantities["released_quantity"] is not None
        else None
    )
    missing_sources = [source for source in SOURCE_ORDER if source not in sources]
    status = "complete" if not missing_sources else "incomplete"
    issues = _divergences(workorder, identifiers, quantities_by_source, records)
    if missing_sources:
        issues.append(
            {
                "code": "missing_source_match",
                "workorder_number": workorder,
                "missing_sources": missing_sources,
            }
        )
    return (
        {
            "workorder_number": workorder,
            "status": status,
            "sources": sources,
            "missing_sources": missing_sources,
            "demand_ids": identifiers["demand_id"],
            "lot_numbers": identifiers["lot_number"],
            "models": identifiers["model"],
            "serial_numbers": identifiers["serial_number"],
            "container_numbers": identifiers["container_number"],
            "organization_codes": identifiers["organization_code"],
            "workorder_types": identifiers["workorder_type"],
            "classification_facts": _classification_facts(records, workorder),
            **quantities,
            "partially_released": partial_release,
            "selected_quantity_sources": selected_quantity_sources,
            "provenance": provenance,
            "calculations": {
                "pending_quantity": {
                    "operation": (
                        "max(explicit_pending, planned_quantity - "
                        "released_quantity, 0)"
                    ),
                    "inputs": {
                        "explicit_pending": explicit_pending,
                        "planned_quantity": quantities["planned_quantity"],
                        "released_quantity": quantities["released_quantity"],
                    },
                },
                "retained_quantity": {
                    "operation": "max(explicit_retained, explicit_held_serial_count)",
                    "inputs": {
                        "explicit_retained": explicit_retained,
                        "explicit_held_serial_count": len(held_serials),
                    },
                },
                "partially_released": {
                    "operation": "0 < released_quantity < received_quantity",
                    "inputs": {
                        "released_quantity": quantities["released_quantity"],
                        "received_quantity": quantities["received_quantity"],
                    },
                },
            },
        },
        issues,
    )


def consolidate(
    records: Iterable[Mapping[str, Any]], *, isolate_failures: bool = False
) -> dict[str, Any]:
    """Consolidate normalized records into deterministic, auditable Workorders."""
    ordered: list[Mapping[str, Any]] = []
    seen_records: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    duplicate_issues: list[dict[str, Any]] = []
    for record in sorted(records, key=_record_key):
        identity = _record_identity(record)
        if identity is None or identity not in seen_records:
            ordered.append(record)
            if identity is not None:
                seen_records[identity] = record
            continue
        if record != seen_records[identity]:
            raise ConsolidationError(
                "Registros diferentes compartilham a mesma proveniência: "
                f"{identity!r}"
            )
        duplicate_issues.append(
            {
                "code": "duplicate_record_ignored",
                "source": record.get("source"),
                "execution_id": record.get("execution_id"),
                "source_file_id": record.get("source_file_id"),
                "sheet": record.get("sheet"),
                "row": record.get("row"),
            }
        )
    indexes: dict[str, dict[str, str]] = {}
    ambiguous: dict[str, set[str]] = {}
    candidates: dict[str, dict[str, set[str]]] = {}
    for field in ("demand_id", "serial_number", "lot_number"):
        indexes[field], ambiguous[field], candidates[field] = _index_unique(
            ordered, field
        )

    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    unmatched: list[dict[str, Any]] = []
    relationship_conflicts: list[dict[str, Any]] = []
    for record in ordered:
        record_conflicts = _relationship_conflicts(record, candidates)
        if record_conflicts:
            relationship_conflicts.extend(record_conflicts)
            continue
        workorder = _resolve_workorder(record, indexes)
        if workorder is None:
            unmatched.append(
                {
                    "code": "unmatched_record",
                    "source": record.get("source"),
                    "execution_id": record.get("execution_id"),
                    "source_file_id": record.get("source_file_id"),
                    "sheet": record.get("sheet"),
                    "row": record.get("row"),
                    "identifiers": {
                        field: _value(record, field)
                        for field in (
                            "workorder_number",
                            "demand_id",
                            "lot_number",
                            "serial_number",
                        )
                        if _nonempty(_value(record, field))
                    },
                }
            )
            continue
        grouped[workorder].append(record)

    workorders: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = [
        *duplicate_issues,
        *relationship_conflicts,
        *unmatched,
    ]
    failed_workorders: list[dict[str, Any]] = []
    for workorder in sorted(grouped):
        try:
            consolidated, workorder_issues = _consolidate_workorder(
                workorder, grouped[workorder]
            )
        except ConsolidationError as exc:
            if not isolate_failures:
                raise
            failure = {
                "code": "workorder_processing_failed",
                "workorder_number": workorder,
                "reason": str(exc),
            }
            failed_workorders.append(failure)
            issues.append(failure)
            continue
        workorders.append(consolidated)
        issues.extend(workorder_issues)
    for field, values in ambiguous.items():
        for value in sorted(values):
            issues.append(
                {
                    "code": "ambiguous_relationship",
                    "field": field,
                    "value": value,
                }
            )
    return {
        "workorder_count": len(workorders),
        "duplicate_record_count": len(duplicate_issues),
        "conflicting_relationship_count": len(relationship_conflicts),
        "unmatched_record_count": len(unmatched),
        "issue_count": len(issues),
        "failed_workorder_count": len(failed_workorders),
        "failed_workorders": failed_workorders,
        "workorders": workorders,
        "issues": issues,
    }


def compare_with_reference(
    result: Mapping[str, Any],
    reference_rows: Iterable[Mapping[str, Any]],
    fields: Sequence[str] = QUANTITY_FIELDS,
) -> dict[str, Any]:
    """Compare a consolidation with WO Status-like rows without changing either."""
    actual = {
        str(row["workorder_number"]): row for row in result.get("workorders", [])
    }
    reference = {
        str(row["workorder_number"]): row for row in reference_rows
    }
    differences: list[dict[str, Any]] = []
    for workorder in sorted(actual.keys() | reference.keys()):
        if workorder not in actual:
            differences.append(
                {"workorder_number": workorder, "code": "missing_in_consolidation"}
            )
            continue
        if workorder not in reference:
            differences.append(
                {"workorder_number": workorder, "code": "missing_in_reference"}
            )
            continue
        for field in fields:
            expected = _quantity(reference[workorder].get(field), field)
            observed = _quantity(actual[workorder].get(field), field)
            if (observed or 0) != (expected or 0):
                differences.append(
                    {
                        "workorder_number": workorder,
                        "code": "value_mismatch",
                        "field": field,
                        "expected": expected,
                        "observed": observed,
                    }
                )
    return {
        "matches": not differences,
        "compared_workorder_count": len(actual.keys() | reference.keys()),
        "difference_count": len(differences),
        "differences": differences,
    }
