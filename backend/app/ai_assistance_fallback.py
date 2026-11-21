"""Deterministic assistance fallback and fact-grounded triage catalog."""

from __future__ import annotations

import re
import unicodedata

from app.ai_assistance_context_models import (
    SECTIONS,
    ExecutionAssistanceContext,
)
from app.ai_assistance_contract import plain_text


def validate_language(value: str) -> str:
    """Lexical policy check; grounding is enforced separately by the generator."""
    plain_text(value)
    normalized = "".join(
        c
        for c in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(c)
    )
    if re.search(
        r"\b(select|from|where|join|drop|truncate|create|alter|grant|revoke|"
        r"union|having|values|sql|causa|causou|causada|causado|"
        r"devido a|em decorrencia|decidiu|determinou|decisao automatica|"
        r"sistema decidiu|system decided|caused by|root cause)\b",
        normalized,
    ) or re.search(r"[;]|--|/\*|\*/|\$\(|\|\|", value):
        raise ValueError("prohibited language")
    return value

NOTICE = "A conferência humana das evidências é necessária."
TRUNCATED = "O contexto possui seções truncadas."
FAILED = "A execução terminou com falha."
MISSING = "Há dados ausentes ou indisponíveis no contexto."
INSUFFICIENT = "As evidências disponíveis são insuficientes."

LEGACY_PREFIX_TITLES = {
    "DIV": "Divergência registrada",
    "PEN": "Pendência registrada",
    "CLA": "Classificação registrada",
    "EVI": "Evidência registrada",
    "HIS": "Transição registrada",
}
LEGACY_EXPLANATIONS = frozenset(
    {
        "Há um registro disponível para conferência.",
        "Há registros disponíveis para conferência.",
        "Os registros estão disponíveis para conferência.",
    }
)
HUMAN_CHECK_OPTIONS = (
    "Conferência humana das referências disponíveis.",
    "Conferência humana das evidências disponíveis.",
)

_AREA_ALT = "Qualidade|Produção|Logística|Suprimentos|Governança de Dados"
_RULE_ALT = (
    "aging|container_impact|long_term_hold|missing_reason|oqc_hold|oqc_pass|"
    "oqc_pending|post_release_hold|pre_release_pending|rework|ship_block|"
    "source_divergence"
)
_CODE_ALT = (
    "duplicate_record|empty_file|inconsistent_quantity|invalid_date|"
    "invalid_format|invalid_header|invalid_number|invalid_quantity|"
    "invalid_sheet|invalid_type|invalid_value|missing_required_column|"
    "missing_required_value|missing_sheet|quantity_mismatch|required_field|"
    "source_divergence|unknown_column"
)
_WO_TOKEN = r"[A-Za-z0-9._:/-]{1,64}"
_PERSISTENCE_SECRET_PATTERN = re.compile(
    r"(password|secret|bearer|token|eyJ[A-Za-z0-9_-]{10})", re.IGNORECASE
)

TRIAGE_TITLE_PATTERN = re.compile(
    rf"^(?:"
    rf"Pendência (?:aberta|registrada): (?:{_RULE_ALT})"
    rf"|Pendência aberta em (?:{_AREA_ALT})(?:: (?:{_RULE_ALT}))?"
    rf"|Divergência \((?:error|warning)\): (?:{_CODE_ALT})"
    rf"|Divergência \((?:error|warning)\) em (?:file|structure|record)"
    rf"|Classificação ativa: (?:{_RULE_ALT})"
    rf"|Classificação \((?:active|closed)\): (?:{_RULE_ALT})"
    rf")$"
)

TRIAGE_EXPLANATION_PATTERN = re.compile(
    rf"^(?:"
    rf"(?:Registro|[23] registros) de pendência (?:open|resolved|cancelled)"
    rf"(?: na regra (?:{_RULE_ALT}))?"
    rf"(?: sob responsabilidade de (?:{_AREA_ALT}))?"
    rf"(?: na Workorder {_WO_TOKEN})?"
    rf"(?: com aging(?: máximo)? de [0-9]{{1,5}} dias)?"
    rf"(?: e impacto em container)?"
    rf" (?:disponível|disponíveis) para conferência\."
    rf"|(?:Divergência|[23] divergências) de severidade (?:error|warning)"
    rf" no escopo (?:file|structure|record)"
    rf"(?: com código (?:{_CODE_ALT}))?"
    rf"(?: na Workorder {_WO_TOKEN})?"
    rf" (?:disponível|disponíveis) para conferência\."
    rf"|(?:Classificação|[23] classificações) (?:active|closed)"
    rf"(?: na regra (?:{_RULE_ALT}))?"
    rf"(?: sob responsabilidade de (?:{_AREA_ALT}))?"
    rf"(?: na Workorder {_WO_TOKEN})?"
    rf"(?: com aging(?: máximo)? de [0-9]{{1,5}} dias)?"
    rf"(?: e impacto em container)?"
    rf" com qualidade de dados (?:complete|partial)"
    rf" (?:disponível|disponíveis) para conferência\."
    rf")$"
)


def _safe_wo_for_text(value: str | None) -> str | None:
    if not value or _PERSISTENCE_SECRET_PATTERN.search(value):
        return None
    try:
        validate_language(f"na Workorder {value}")
    except ValueError:
        return None
    return value


def _is_valid_text(value: str, *, max_length: int) -> bool:
    if (
        not value
        or len(value) > max_length
        or _PERSISTENCE_SECRET_PATTERN.search(value)
    ):
        return False
    try:
        validate_language(value)
    except ValueError:
        return False
    return True


def _common_non_null(items: list, attr: str):
    values = [getattr(item, attr, None) for item in items]
    if values and values[0] is not None and all(v == values[0] for v in values):
        return values[0]
    return None


def _item_index(context: ExecutionAssistanceContext) -> dict[str, tuple[str, object]]:
    index: dict[str, tuple[str, object]] = {}
    for section in SECTIONS:
        for item in getattr(context, section):
            index[item.ref_id] = (section, item)
    return index


def valid_summaries(context: ExecutionAssistanceContext) -> tuple[str, ...]:
    counts = context.counts
    errors = "erro" if counts.errors == 1 else "erros"
    warnings = "aviso" if counts.warnings == 1 else "avisos"
    pending = "pendência" if counts.pending_items == 1 else "pendências"
    candidates = [
        (
            f"A execução registra {counts.errors} {errors}, "
            f"{counts.warnings} {warnings} e {counts.pending_items} {pending}."
        ),
        (
            f"A execução registra {counts.errors} erros, "
            f"{counts.warnings} avisos e {counts.pending_items} pendências."
        ),
        (
            f"Foram registrados {counts.errors} {errors}, "
            f"{counts.warnings} {warnings} e {counts.pending_items} {pending}."
        ),
        (
            f"Foram registrados {counts.errors} erros, "
            f"{counts.warnings} avisos e {counts.pending_items} pendências."
        ),
    ]
    return tuple(dict.fromkeys(candidates))


def prioritized_reference_ids(context: ExecutionAssistanceContext) -> list[str]:
    open_pending = sorted(
        (item for item in context.pending_items if item.status == "open"),
        key=lambda item: (
            not item.has_container,
            -(item.age_days or 0),
            -(item.priority_score or 0),
            item.ref_id,
        ),
    )
    error_divs = [item for item in context.divergences if item.severity == "error"]
    active_cla = sorted(
        (item for item in context.classifications if item.state == "active"),
        key=lambda item: (
            not item.has_container,
            -(item.age_days or 0),
            -item.priority_score,
            item.ref_id,
        ),
    )
    warning_divs = [item for item in context.divergences if item.severity == "warning"]
    other_pending = [item for item in context.pending_items if item.status != "open"]
    other_cla = [item for item in context.classifications if item.state != "active"]
    available_evi = [item for item in context.evidences if item.available]
    unavailable_evi = [item for item in context.evidences if not item.available]
    ordered = [
        *open_pending,
        *error_divs,
        *active_cla,
        *warning_divs,
        *other_pending,
        *other_cla,
        *available_evi,
        *unavailable_evi,
        *context.state_history,
    ]
    return [item.ref_id for item in ordered]


def _triage_candidates_for_items(
    prefix: str, items: list
) -> tuple[list[str], list[str]]:
    titles: list[str] = []
    explanations: list[str] = []
    count = len(items)

    if prefix == "PEN":
        rule_id = _common_non_null(items, "rule_id")
        area = _common_non_null(items, "responsible_area")
        status = _common_non_null(items, "status")
        wo = _safe_wo_for_text(_common_non_null(items, "workorder_number"))
        ages = [item.age_days for item in items if item.age_days is not None]
        has_container = any(item.has_container for item in items)

        if status == "open":
            if area and rule_id:
                titles.append(f"Pendência aberta em {area}: {rule_id}")
            if area:
                titles.append(f"Pendência aberta em {area}")
            if rule_id:
                titles.append(f"Pendência aberta: {rule_id}")
        if rule_id:
            titles.append(f"Pendência registrada: {rule_id}")

        if status:
            rule_clause = f" na regra {rule_id}" if rule_id else ""
            area_clause = f" sob responsabilidade de {area}" if area else ""
            wo_clause = f" na Workorder {wo}" if wo else ""
            aging_clause = (
                f" com aging de {ages[0]} dias"
                if count == 1 and ages
                else (f" com aging máximo de {max(ages)} dias" if ages else "")
            )
            container_clause = " e impacto em container" if has_container else ""
            subject = (
                "Registro de pendência"
                if count == 1
                else f"{count} registros de pendência"
            )
            avail = "disponível" if count == 1 else "disponíveis"
            explanations.append(
                f"{subject} {status}{rule_clause}{area_clause}{wo_clause}"
                f"{aging_clause}{container_clause} {avail} para conferência."
            )

    elif prefix == "DIV":
        severity = _common_non_null(items, "severity")
        scope = _common_non_null(items, "scope")
        code = _common_non_null(items, "code")
        wo = _safe_wo_for_text(_common_non_null(items, "workorder_number"))

        if severity and code:
            titles.append(f"Divergência ({severity}): {code}")
        if severity and scope:
            titles.append(f"Divergência ({severity}) em {scope}")

        if severity and scope:
            code_clause = f" com código {code}" if code else ""
            wo_clause = f" na Workorder {wo}" if wo else ""
            subject = (
                "Divergência" if count == 1 else f"{count} divergências"
            )
            avail = "disponível" if count == 1 else "disponíveis"
            explanations.append(
                f"{subject} de severidade {severity} no escopo {scope}"
                f"{code_clause}{wo_clause} {avail} para conferência."
            )

    elif prefix == "CLA":
        rule_id = _common_non_null(items, "rule_id")
        area = _common_non_null(items, "responsible_area")
        state = _common_non_null(items, "state")
        quality = _common_non_null(items, "data_quality")
        wo = _safe_wo_for_text(_common_non_null(items, "workorder_number"))
        ages = [item.age_days for item in items if item.age_days is not None]
        has_container = any(item.has_container for item in items)

        if state == "active" and rule_id:
            titles.append(f"Classificação ativa: {rule_id}")
        if state and rule_id:
            titles.append(f"Classificação ({state}): {rule_id}")

        if state and quality:
            rule_clause = f" na regra {rule_id}" if rule_id else ""
            area_clause = f" sob responsabilidade de {area}" if area else ""
            wo_clause = f" na Workorder {wo}" if wo else ""
            aging_clause = (
                f" com aging de {ages[0]} dias"
                if count == 1 and ages
                else (f" com aging máximo de {max(ages)} dias" if ages else "")
            )
            container_clause = " e impacto em container" if has_container else ""
            subject = (
                "Classificação" if count == 1 else f"{count} classificações"
            )
            avail = "disponível" if count == 1 else "disponíveis"
            explanations.append(
                f"{subject} {state}{rule_clause}{area_clause}{wo_clause}"
                f"{aging_clause}{container_clause}"
                f" com qualidade de dados {quality} {avail} para conferência."
            )

    return (
        [t for t in titles if _is_valid_text(t, max_length=120)],
        [e for e in explanations if _is_valid_text(e, max_length=600)],
    )


def describe_finding_items(
    context: ExecutionAssistanceContext, selected_refs: list[str]
) -> tuple[set[str], set[str]]:
    """Return allowed (titles, explanations) grounded strictly in selected_refs."""
    if not selected_refs:
        return set(), set()
    index = _item_index(context)
    if any(ref not in index for ref in selected_refs):
        return set(), set()

    titles = {"Registros disponíveis", "Registros para conferência"}
    explanations = {
        "Há registros disponíveis para conferência.",
        "Os registros estão disponíveis para conferência.",
    }
    if len(selected_refs) == 1:
        explanations.add("Há um registro disponível para conferência.")

    prefixes = {ref[:3] for ref in selected_refs}
    if len(prefixes) == 1:
        prefix = next(iter(prefixes))
        titles.add(LEGACY_PREFIX_TITLES[prefix])
        items = [index[ref][1] for ref in selected_refs]
        triage_titles, triage_explanations = _triage_candidates_for_items(prefix, items)
        titles.update(triage_titles)
        explanations.update(triage_explanations)
    return (
        {t for t in titles if _is_valid_text(t, max_length=120)},
        {e for e in explanations if _is_valid_text(e, max_length=600)},
    )


def deterministic_triage_findings(context: ExecutionAssistanceContext) -> list[dict]:
    """Build up to 5 disjoint, priority-ranked grounded triage findings."""
    index = _item_index(context)
    ordered_refs = prioritized_reference_ids(context)
    used: set[str] = set()
    findings: list[dict] = []

    def _group_key(ref: str):
        prefix = ref[:3]
        item = index[ref][1]
        if prefix == "PEN":
            return ("PEN", item.status, item.rule_id, item.responsible_area)
        if prefix == "DIV":
            return ("DIV", item.severity, item.scope, item.code)
        if prefix == "CLA":
            return ("CLA", item.state, item.rule_id, item.responsible_area)
        return (prefix, ref)

    groups: dict[tuple, list[str]] = {}
    group_order: list[tuple] = []
    for ref in ordered_refs:
        key = _group_key(ref)
        if key not in groups:
            groups[key] = []
            group_order.append(key)
        groups[key].append(ref)

    for key in group_order:
        if len(findings) >= 5:
            break
        refs = [ref for ref in groups[key] if ref not in used][:3]
        if not refs:
            continue
        used.update(refs)
        prefix = refs[0][:3]
        items = [index[ref][1] for ref in refs]
        triage_titles, triage_explanations = _triage_candidates_for_items(prefix, items)
        title = triage_titles[0] if triage_titles else LEGACY_PREFIX_TITLES[prefix]
        explanation = (
            triage_explanations[0]
            if triage_explanations
            else (
                "Há um registro disponível para conferência."
                if len(refs) == 1
                else "Há registros disponíveis para conferência."
            )
        )
        findings.append(
            {
                "title": title,
                "explanation": explanation,
                "evidence_refs": refs,
            }
        )
    return findings


def context_finding_enums(
    context: ExecutionAssistanceContext,
) -> tuple[list[str], list[str]]:
    """Collect the finite grounded title and explanation enums for prompt schema."""
    titles: set[str] = {"Registros disponíveis", "Registros para conferência"}
    explanations: set[str] = set(LEGACY_EXPLANATIONS)
    if len(context.evidence_refs()) == 0:
        return [], []
    for finding in deterministic_triage_findings(context):
        t, e = describe_finding_items(context, finding["evidence_refs"])
        titles.update(t)
        explanations.update(e)
    for ref in context.evidence_refs():
        t, e = describe_finding_items(context, [ref])
        titles.update(t)
        explanations.update(e)
    return sorted(titles), sorted(explanations)


def required_limitations(context: ExecutionAssistanceContext) -> list[str]:
    counts = context.counts
    result = [NOTICE]
    if context.truncated_sections:
        result.append(TRUNCATED)
    if context.lifecycle == "failed":
        result.append(FAILED)
    if (
        not context.evidences
        or any(not e.available for e in context.evidences)
        or counts.pending_items > len(context.pending_items)
        or counts.classifications > len(context.classifications)
        or counts.errors + counts.warnings > len(context.divergences)
    ):
        result.append(MISSING)
    return result


def deterministic_fallback(
    context: ExecutionAssistanceContext,
) -> tuple[str, list[str]]:
    counts = context.counts
    summary = (
        f"A execução registra {counts.errors} erros, {counts.warnings} avisos e "
        f"{counts.pending_items} pendências."
    )
    refs = prioritized_reference_ids(context)[:3]
    if refs:
        summary += f" Referências disponíveis: {', '.join(refs)}."
    limitations = required_limitations(context)
    if context.sufficiency == "insufficient":
        limitations.append(INSUFFICIENT)
    return summary, limitations
