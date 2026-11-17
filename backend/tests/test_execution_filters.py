"""Execution filters normalize periods without broadening authorization."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.errors import ApiError
from app.execution_filters import (
    ExecutionQueryFilters,
    build_execution_predicate,
    normalize_execution_period,
)
from app.execution_projection import ExecutionOutcome

ORG_A = UUID("19300000-0000-4000-8000-000000000001")
ORG_B = UUID("19300000-0000-4000-8000-000000000002")


def test_normalizes_period_to_utc_and_accepts_equal_inclusive_bounds():
    start = datetime(2026, 11, 1, 8, tzinfo=timezone(timedelta(hours=-4)))
    end = datetime(2026, 11, 1, 15, tzinfo=timezone(timedelta(hours=3)))
    filters = ExecutionQueryFilters(date_from=start, date_to=end, file_type=".CSV")
    assert filters.date_from == filters.date_to == datetime(2026, 11, 1, 12, tzinfo=UTC)
    assert filters.date_from.tzinfo is UTC
    assert filters.file_type == "csv"


@pytest.mark.parametrize("provided_start", [True, False])
def test_open_period_preserves_the_unspecified_bound(provided_start):
    instant = datetime(2026, 11, 1, tzinfo=UTC)
    bounds = (instant, None) if provided_start else (None, instant)
    assert normalize_execution_period(*bounds) == bounds


@pytest.mark.parametrize(
    ("start", "end", "code"),
    [
        ("2026-11-01T08:00:00", None, "timezone_required"),
        (None, "2026-11-01T08:00:00", "timezone_required"),
        ("2026-11-01T08:00:00", "2026-11-01T12:00:00Z", "timezone_required"),
        ("2026-11-01T08:00:00-04:00", "2026-11-01T11:00:00Z", "invalid_period"),
        ("0001-01-01T00:00:00+14:00", None, "invalid_period"),
        (None, "9999-12-31T23:59:59-12:00", "invalid_period"),
    ],
)
def test_rejects_naive_or_inverted_periods(start, end, code):
    with pytest.raises(ApiError) as error:
        ExecutionQueryFilters(
            date_from=datetime.fromisoformat(start) if start else None,
            date_to=datetime.fromisoformat(end) if end else None,
        )
    assert error.value.status_code == 422
    assert error.value.code == code


def test_requested_organization_never_replaces_the_authorized_scope():
    predicate = build_execution_predicate(
        ExecutionQueryFilters(organization_id=ORG_B),
        organization_scopes=frozenset({ORG_A}),
    )
    assert predicate.parameters == ([ORG_A], ORG_B)
    assert "e.organization_id = ANY(%s)" in predicate.where
    assert "e.organization_id = %s" in predicate.where


def test_global_scope_excludes_unknown_iam_and_empty_scope_matches_nothing():
    filters = ExecutionQueryFilters()
    global_scope = build_execution_predicate(filters, organization_scopes=None)
    assert global_scope.where == "e.organization_id IS NOT NULL"
    assert global_scope.parameters == ()
    empty_scope = build_execution_predicate(filters, organization_scopes=frozenset())
    assert empty_scope.where == "FALSE"
    assert empty_scope.parameters == ()


def test_combined_filter_values_are_normalized_and_parameterized():
    start = datetime(2026, 11, 1, tzinfo=UTC)
    end = datetime(2026, 11, 2, tzinfo=UTC)
    source = "OWM' OR TRUE --"
    identifier = "untrusted' OR TRUE --"
    predicate = build_execution_predicate(
        ExecutionQueryFilters(
            organization_id=ORG_A,
            status="completed_with_errors",
            lifecycle="partial",
            outcome=ExecutionOutcome.PARTIAL,
            source=source,
            file_type=".XLSX",
            date_from=start,
            date_to=end,
            execution_id=identifier,
        ),
        organization_scopes=frozenset({ORG_B, ORG_A}),
    )
    assert predicate.parameters == (
        [ORG_A, ORG_B],
        ORG_A,
        "completed_with_errors",
        source,
        start,
        end,
        identifier,
        "xlsx",
        "partial",
        "partial",
    )
    assert source not in predicate.where
    assert identifier not in predicate.where


def test_canonical_filter_rejects_unrecognized_outcomes():
    with pytest.raises(ValueError):
        ExecutionQueryFilters(outcome="success")
