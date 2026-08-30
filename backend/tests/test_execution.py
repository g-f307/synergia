from __future__ import annotations

import pytest

from app.execution import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    ExecutionState,
    InvalidExecutionTransition,
    import_fingerprint,
    reprocessing_fingerprint,
    validate_transition,
)


def test_complete_execution_flow_is_authorized() -> None:
    flow = [
        ExecutionState.PENDING,
        ExecutionState.VALIDATING,
        ExecutionState.NORMALIZING,
        ExecutionState.CONSOLIDATING,
        ExecutionState.APPLYING_RULES,
        ExecutionState.COMPLETED,
    ]

    for current, target in zip(flow, flow[1:]):
        validate_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ExecutionState.COMPLETED, ExecutionState.VALIDATING),
        (ExecutionState.COMPLETED_WITH_ERRORS, ExecutionState.APPLYING_RULES),
        (ExecutionState.FAILED, ExecutionState.PENDING),
        (ExecutionState.VALIDATION_FAILED, ExecutionState.NORMALIZING),
        (ExecutionState.PENDING, ExecutionState.COMPLETED),
        (ExecutionState.VALIDATING, ExecutionState.APPLYING_RULES),
        (ExecutionState.NORMALIZING, ExecutionState.COMPLETED),
    ],
)
def test_rejects_relevant_invalid_transitions(current: str, target: str) -> None:
    with pytest.raises(InvalidExecutionTransition) as error:
        validate_transition(current, target)

    assert error.value.current == current
    assert error.value.target == target


def test_every_terminal_state_rejects_further_transitions() -> None:
    assert all(state not in ALLOWED_TRANSITIONS for state in TERMINAL_STATES)


def test_import_fingerprint_is_order_independent_and_versioned() -> None:
    first = import_fingerprint(["b" * 64, "a" * 64], "1.0.0", "1.0.0")
    repeated = import_fingerprint(["a" * 64, "b" * 64], "1.0.0", "1.0.0")
    new_rules = import_fingerprint(["a" * 64, "b" * 64], "1.0.0", "2.0.0")

    assert first == repeated
    assert first != new_rules


def test_reprocessing_fingerprint_considers_request_and_versions() -> None:
    first = reprocessing_fingerprint("exec-1", "request-1", "1.0.0", "1.0.0")

    assert first == reprocessing_fingerprint("exec-1", "request-1", "1.0.0", "1.0.0")
    assert first != reprocessing_fingerprint("exec-1", "request-1", "1.0.0", "2.0.0")
    assert first != reprocessing_fingerprint("exec-1", "request-2", "1.0.0", "1.0.0")
