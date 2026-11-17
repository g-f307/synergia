"""Canonical outcomes and the deliberately preserved legacy lifecycle."""

from collections import Counter

import pytest

from app.execution import ExecutionState
from app.execution_projection import execution_outcome, legacy_lifecycle

STATE_CASES = [
    ("pending", "active", "active"),
    ("validating", "active", "active"),
    ("normalizing", "active", "active"),
    ("consolidating", "active", "active"),
    ("applying_rules", "active", "active"),
    ("reprocessing", "active", "active"),
    ("completed", "completed", "completed"),
    ("completed_with_errors", "partial", "partial"),
    ("duplicate", "skipped_duplicate", "completed"),
    ("validation_failed", "failed", "failed"),
    ("failed", "failed", "failed"),
    ("cancelled", "cancelled", "failed"),
    ("future_state", "unknown", "active"),
    ("COMPLETED", "unknown", "active"),
    ("", "unknown", "active"),
    (None, "unknown", "active"),
]


@pytest.mark.parametrize(("status", "outcome", "legacy"), STATE_CASES)
def test_canonical_outcomes_and_legacy_compatibility(status, outcome, legacy):
    assert execution_outcome(status) == outcome
    assert legacy_lifecycle(status) == legacy


def test_projection_cases_cover_every_persisted_state():
    known = {state for state, _, _ in STATE_CASES[:12]}
    assert known == {state.value for state in ExecutionState}


def test_duplicates_and_partial_results_do_not_count_as_completed():
    states = ["completed"] * 3 + ["completed_with_errors"] * 2 + ["duplicate"] * 9
    counts = Counter(execution_outcome(state) for state in states)
    assert counts == {"completed": 3, "partial": 2, "skipped_duplicate": 9}
    assert sum(counts.values()) == 14
