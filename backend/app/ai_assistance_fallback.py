"""Deterministic assistance fallback, independent of prompts and model output."""

from app.ai_assistance_context_models import ExecutionAssistanceContext

NOTICE = "A conferência humana das evidências é necessária."
TRUNCATED = "O contexto possui seções truncadas."
FAILED = "A execução terminou com falha."
MISSING = "Há dados ausentes ou indisponíveis no contexto."
INSUFFICIENT = "As evidências disponíveis são insuficientes."


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
    refs = sorted(context.evidence_refs())[:3]
    if refs:
        summary += f" Referências disponíveis: {', '.join(refs)}."
    limitations = required_limitations(context)
    if context.sufficiency == "insufficient":
        limitations.append(INSUFFICIENT)
    return summary, limitations
