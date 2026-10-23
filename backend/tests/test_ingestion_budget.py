from __future__ import annotations

import pytest

from app import ingestion_budget
from app.ingestion_budget import (
    DEFAULT_MAX_CELLS,
    IngestionLimitError,
    budget_for,
)


def test_defaults_are_explicit_and_authorize_every_sheet(monkeypatch) -> None:
    for name in (
        "INGESTION_MAX_CELLS",
        "INGESTION_MAX_CELLS_OWM",
        "INGESTION_ALLOWED_SHEETS",
        "INGESTION_ALLOWED_SHEETS_OWM",
    ):
        monkeypatch.delenv(name, raising=False)

    budget = budget_for("OWM")

    assert budget.max_cells == DEFAULT_MAX_CELLS
    assert budget.allowed_sheets is None
    assert budget.authorizes("Qualquer aba")


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

    budget = budget_for("OWM")

    assert budget.authorizes("owm sn")
    assert budget.authorizes("TOTAL, DECISION")
    assert not budget.authorizes("Analysis 2")
    assert budget_for("TMS").allowed_sheets is None


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
