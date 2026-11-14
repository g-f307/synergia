"""Vocabulary and selection policy 1.0.0; unknown persisted text stays absent."""

import unicodedata

RULE_IDS = frozenset(
    {
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
)
ISSUE_CODES = frozenset(
    {
        "invalid_header",
        "empty_file",
        "invalid_value",
        "quantity_mismatch",
        "missing_required_column",
        "missing_required_value",
        "invalid_date",
        "invalid_number",
        "invalid_quantity",
        "duplicate_record",
        "unknown_column",
        "missing_sheet",
        "invalid_sheet",
        "source_divergence",
        "required_field",
        "invalid_type",
        "invalid_format",
        "inconsistent_quantity",
    }
)
MEDIA_TYPES = {
    "csv": "text/csv",
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "bin": "application/octet-stream",
}
LIFECYCLES = {
    "completed": "completed",
    "duplicate": "completed",
    "completed_with_errors": "partial",
    "failed": "failed",
    "validation_failed": "failed",
    "cancelled": "failed",
}


def normalized_text(value: str | None, limit: int = 64) -> str | None:
    """Replace controls; omit an entire oversized value, never slice a negation."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid structured context text")
    value = "".join(
        " " if unicodedata.category(char).startswith("C") else char
        for char in unicodedata.normalize("NFKC", value)
    )
    value = " ".join(value.split())
    return value if value and len(value) <= limit else None


def vocabulary(value: str | None, allowed: frozenset[str]) -> str | None:
    normalized = normalized_text(value)
    return normalized if normalized in allowed else None
