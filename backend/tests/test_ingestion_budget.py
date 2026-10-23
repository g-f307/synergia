from __future__ import annotations

import pytest

from app import ingestion_budget
from app.ingestion_budget import (
    DEFAULT_MAX_CELLS,
    IngestionBudget,
    IngestionLimitError,
    budget_for,
)


def test_defaults_are_explicit(monkeypatch) -> None:
    monkeypatch.delenv("INGESTION_MAX_CELLS", raising=False)
    monkeypatch.delenv("INGESTION_MAX_CELLS_OWM", raising=False)

    assert budget_for("OWM").max_cells == DEFAULT_MAX_CELLS


@pytest.mark.parametrize("value", [None, "", "   ", " | "])
def test_missing_or_empty_sheet_list_fails_closed(monkeypatch, value) -> None:
    monkeypatch.delenv("INGESTION_ALLOWED_SHEETS_OWM", raising=False)
    if value is None:
        monkeypatch.delenv("INGESTION_ALLOWED_SHEETS", raising=False)
    else:
        monkeypatch.setenv("INGESTION_ALLOWED_SHEETS", value)

    budget = budget_for("OWM")

    assert budget.allowed_sheets == frozenset()
    assert not budget.authorizes("Qualquer aba")


def test_wildcard_is_an_explicit_opt_in_per_source(monkeypatch) -> None:
    monkeypatch.setenv("INGESTION_ALLOWED_SHEETS", "OWM SN")
    monkeypatch.setenv("INGESTION_ALLOWED_SHEETS_TMS", "*")

    assert budget_for("TMS").allowed_sheets is None
    assert budget_for("TMS").authorizes("Qualquer aba")
    assert budget_for("OWM").authorizes("owm sn")
    assert not budget_for("OWM").authorizes("Qualquer aba")


def test_memory_estimate_covers_narrow_sheets_and_follows_rule_deferral() -> None:
    from app.pipeline import RULE_DETAIL_DEFER_THRESHOLD

    budget = budget_for("OWM")

    assert ingestion_budget.RULE_DETAIL_DEFER_ROWS == RULE_DETAIL_DEFER_THRESHOLD
    below = budget.estimated_memory(RULE_DETAIL_DEFER_THRESHOLD - 1, 0)
    above = budget.estimated_memory(RULE_DETAIL_DEFER_THRESHOLD, 0)
    assert below > above
    assert budget.estimated_memory(10, 100) == (
        10 * ingestion_budget.ROW_COST_BYTES + 100 * ingestion_budget.CELL_COST_BYTES
    )
    # Many rows of only two columns stay far from the cell limit but not from
    # the memory budget.
    assert budget.estimated_memory(1_048_576, 2_097_152) > budget.max_memory_bytes


def test_source_suffix_overrides_the_global_value(monkeypatch) -> None:
    monkeypatch.setenv("INGESTION_MAX_ROWS", "500")
    monkeypatch.setenv("INGESTION_MAX_ROWS_GMES_OQC", "700")

    assert budget_for("N-FP").max_rows == 500
    assert budget_for("GMES/OQC").max_rows == 700


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_rejects_invalid_limits_instead_of_disabling_them(monkeypatch, value) -> None:
    monkeypatch.setenv("INGESTION_MAX_CELLS", value)

    with pytest.raises(RuntimeError, match="INGESTION_MAX_CELLS"):
        budget_for("OWM")


def test_allowed_sheets_use_pipe_and_ignore_case(monkeypatch) -> None:
    monkeypatch.setenv("INGESTION_ALLOWED_SHEETS_OWM", "OWM SN | Total, Decision ")
    monkeypatch.delenv("INGESTION_ALLOWED_SHEETS", raising=False)

    budget = budget_for("OWM")

    assert budget.authorizes("owm sn")
    assert budget.authorizes("TOTAL, DECISION")
    assert not budget.authorizes("Analysis 2")
    assert budget_for("TMS").allowed_sheets == frozenset()


def test_limit_error_carries_code_guidance_and_measurements() -> None:
    error = IngestionLimitError(
        "workbook_row_limit", limit=10, observed=11, sheet="Dados"
    )

    assert error.code == "workbook_row_limit"
    assert error.message
    assert error.details() == {
        "guidance": error.guidance,
        "limit": 10,
        "observed": 11,
        "sheet": "Dados",
    }
    assert error.guidance


def test_every_limit_code_has_message_and_guidance() -> None:
    for code, (message, guidance) in ingestion_budget.LIMIT_GUIDANCE.items():
        assert message and guidance, code


def test_clock_raises_only_after_the_deadline(monkeypatch) -> None:
    now = [100.0]
    monkeypatch.setattr(ingestion_budget.time, "monotonic", lambda: now[0])
    clock = budget_for("OWM").start()

    now[0] = 100.0 + clock.max_seconds
    clock.check()
    now[0] += 0.1

    with pytest.raises(IngestionLimitError) as excinfo:
        clock.check()
    assert excinfo.value.code == "ingestion_time_limit"
    assert excinfo.value.limit == clock.max_seconds


def test_most_restrictive_budget_is_independent_of_the_order(monkeypatch) -> None:
    monkeypatch.setenv("INGESTION_MAX_MEMORY_BYTES", "1000000")
    monkeypatch.setenv("INGESTION_MAX_MEMORY_BYTES_OWM", "64000")
    monkeypatch.setenv("INGESTION_MAX_SECONDS_TMS", "5")
    budgets = [budget_for(source) for source in ("N-FP", "OWM", "TMS")]

    forward = IngestionBudget.most_restrictive(budgets)
    backward = IngestionBudget.most_restrictive(list(reversed(budgets)))

    assert forward.max_memory_bytes == backward.max_memory_bytes == 64000
    assert forward.max_seconds == backward.max_seconds == 5


def test_file_limit_is_global_and_positive(monkeypatch) -> None:
    monkeypatch.delenv("INGESTION_MAX_FILES", raising=False)
    assert ingestion_budget.max_files() == ingestion_budget.DEFAULT_MAX_FILES

    monkeypatch.setenv("INGESTION_MAX_FILES", "3")
    assert ingestion_budget.max_files() == 3

    monkeypatch.setenv("INGESTION_MAX_FILES", "0")
    with pytest.raises(RuntimeError, match="INGESTION_MAX_FILES"):
        ingestion_budget.max_files()


def test_composite_source_defaults_to_the_adapter_sheets(monkeypatch) -> None:
    from app.wo_status_spec import load_spec

    monkeypatch.delenv("INGESTION_ALLOWED_SHEETS", raising=False)
    monkeypatch.delenv("INGESTION_ALLOWED_SHEETS_WO_STATUS", raising=False)

    budget = budget_for("WO Status")

    assert budget.allowed_sheets == load_spec().authorized_names()
    assert budget.authorizes("owm sn")
    assert not budget.authorizes("Analysis 2")
    assert budget.columns_of("NFP") == frozenset(
        {21, 23, 25, 27, 28, 39, 233, 239, 282}
    )
    assert budget_for("OWM").columns_of("OWM SN") is None


def test_composite_source_allowlist_can_be_narrowed_but_not_widened_by_default(
    monkeypatch,
) -> None:
    monkeypatch.setenv("INGESTION_ALLOWED_SHEETS_WO_STATUS", "NFP")

    budget = budget_for("WO Status")

    assert budget.authorizes("NFP")
    assert not budget.authorizes("CTNR STATUS")
