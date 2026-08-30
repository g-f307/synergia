from __future__ import annotations

import hashlib
from enum import StrEnum

PIPELINE_VERSION = "1.0.0"


class ExecutionState(StrEnum):
    PENDING = "pending"
    VALIDATING = "validating"
    VALIDATION_FAILED = "validation_failed"
    NORMALIZING = "normalizing"
    CONSOLIDATING = "consolidating"
    APPLYING_RULES = "applying_rules"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    REPROCESSING = "reprocessing"
    DUPLICATE = "duplicate"
    CANCELLED = "cancelled"


TERMINAL_STATES = frozenset(
    {
        ExecutionState.VALIDATION_FAILED,
        ExecutionState.COMPLETED,
        ExecutionState.COMPLETED_WITH_ERRORS,
        ExecutionState.FAILED,
        ExecutionState.DUPLICATE,
        ExecutionState.CANCELLED,
    }
)

ALLOWED_TRANSITIONS = {
    ExecutionState.PENDING: frozenset(
        {
            ExecutionState.VALIDATING,
            ExecutionState.REPROCESSING,
            ExecutionState.DUPLICATE,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
        }
    ),
    ExecutionState.REPROCESSING: frozenset(
        {ExecutionState.VALIDATING, ExecutionState.FAILED}
    ),
    ExecutionState.VALIDATING: frozenset(
        {
            ExecutionState.NORMALIZING,
            ExecutionState.VALIDATION_FAILED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.NORMALIZING: frozenset(
        {
            ExecutionState.CONSOLIDATING,
            ExecutionState.VALIDATION_FAILED,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.CONSOLIDATING: frozenset(
        {
            ExecutionState.APPLYING_RULES,
            ExecutionState.COMPLETED_WITH_ERRORS,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.APPLYING_RULES: frozenset(
        {
            ExecutionState.COMPLETED,
            ExecutionState.COMPLETED_WITH_ERRORS,
            ExecutionState.FAILED,
        }
    ),
}


class InvalidExecutionTransition(ValueError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Transição de execução não permitida: {current} -> {target}")
        self.current = current
        self.target = target


def validate_transition(current: str, target: str) -> None:
    try:
        current_state = ExecutionState(current)
        target_state = ExecutionState(target)
    except ValueError as exc:
        raise InvalidExecutionTransition(current, target) from exc
    if target_state not in ALLOWED_TRANSITIONS.get(current_state, frozenset()):
        raise InvalidExecutionTransition(current, target)


def fingerprint(*parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def import_fingerprint(
    file_hashes: list[str], pipeline_version: str, rule_catalog_version: str
) -> str:
    return fingerprint(
        "import",
        pipeline_version,
        rule_catalog_version,
        *sorted(file_hashes),
    )


def reprocessing_fingerprint(
    source_execution_id: str,
    request_key: str,
    pipeline_version: str,
    rule_catalog_version: str,
) -> str:
    return fingerprint(
        "reprocess",
        source_execution_id,
        request_key,
        pipeline_version,
        rule_catalog_version,
    )
