from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any

DEFAULT_MAX_SHEETS = 64
DEFAULT_MAX_ROWS = 1_048_576
DEFAULT_MAX_COLUMNS = 16_384
DEFAULT_MAX_CELLS = 2_000_000
DEFAULT_MAX_FORMULAS = 2_000_000
DEFAULT_MAX_MEMORY_BYTES = 1024 * 1024 * 1024
RULE_DETAIL_DEFER_ROWS = 50_000  # keep equal to pipeline.RULE_DETAIL_DEFER_THRESHOLD
ROW_COST_BYTES = 22_000
DEFERRED_ROW_COST_BYTES = 4_500
CELL_COST_BYTES = 320
DEFAULT_MAX_SECONDS = 300.0
DEFAULT_MAX_ISSUES = 250_000
DEFAULT_PROGRESS_INTERVAL = 10_000

LIMIT_GUIDANCE: dict[str, tuple[str, str]] = {
    "workbook_sheet_limit": (
        "Planilha com abas em excesso",
        "Remova abas auxiliares ou envie somente as abas autorizadas.",
    ),
    "workbook_row_limit": (
        "Aba com linhas acima do limite",
        "Divida a aba em arquivos menores ou solicite aumento medido do limite.",
    ),
    "workbook_column_limit": (
        "Aba com colunas acima do limite",
        "Envie apenas as colunas previstas no contrato da fonte.",
    ),
    "workbook_cell_limit": (
        "Planilha com células acima do orçamento",
        "Reduza linhas ou colunas, ou solicite aumento medido do orçamento.",
    ),
    "workbook_dimension_limit": (
        "Dimensão declarada da aba acima do orçamento",
        "Reexporte a aba sem formatação ou células vazias além dos dados.",
    ),
    "workbook_memory_limit": (
        "Estimativa de memória da planilha acima do orçamento",
        "Reduza linhas ou colunas, ou solicite aumento medido do orçamento.",
    ),
    "workbook_formula_limit": (
        "Planilha com fórmulas acima do limite",
        "Exporte os valores calculados em vez das fórmulas.",
    ),
    "no_authorized_sheet": (
        "Nenhuma aba autorizada foi encontrada",
        "Configure as abas autorizadas da fonte (INGESTION_ALLOWED_SHEETS) e "
        "confirme os nomes previstos no contrato.",
    ),
    "ingestion_time_limit": (
        "Processamento acima do tempo permitido",
        "Envie um arquivo menor ou solicite aumento medido do tempo.",
    ),
    "ingestion_issue_limit": (
        "Ocorrências de validação acima do limite",
        "Corrija o arquivo de origem antes de enviá-lo novamente.",
    ),
    "unreadable_workbook": (
        "Planilha ilegível durante o processamento",
        "Reexporte o arquivo a partir da origem e envie novamente.",
    ),
}


class IngestionLimitError(ValueError):
    """A resource budget was exceeded; the file must be rejected safely."""

    def __init__(
        self,
        code: str,
        *,
        limit: int | float | None = None,
        observed: int | float | None = None,
        sheet: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.limit = limit
        self.observed = observed
        self.sheet = sheet
        self.recorded = False

    @property
    def message(self) -> str:
        return LIMIT_GUIDANCE.get(self.code, (self.code, ""))[0]

    @property
    def guidance(self) -> str:
        return LIMIT_GUIDANCE.get(self.code, ("", ""))[1]

    def details(self) -> dict[str, Any]:
        details: dict[str, Any] = {"guidance": self.guidance}
        if self.limit is not None:
            details["limit"] = self.limit
        if self.observed is not None:
            details["observed"] = self.observed
        if self.sheet is not None:
            details["sheet"] = self.sheet
        return details


@dataclass(frozen=True)
class IngestionBudget:
    max_sheets: int = DEFAULT_MAX_SHEETS
    max_rows: int = DEFAULT_MAX_ROWS
    max_columns: int = DEFAULT_MAX_COLUMNS
    max_cells: int = DEFAULT_MAX_CELLS
    max_formulas: int = DEFAULT_MAX_FORMULAS
    max_memory_bytes: int = DEFAULT_MAX_MEMORY_BYTES
    max_seconds: float = DEFAULT_MAX_SECONDS
    max_issues: int = DEFAULT_MAX_ISSUES
    progress_interval: int = DEFAULT_PROGRESS_INTERVAL
    allowed_sheets: frozenset[str] | None = None

    def estimated_memory(self, rows: int, cells: int) -> int:
        """Conservative peak bytes of the complete pipeline.

        ``rows`` is the number of **normalized records** of the execution, the
        same count that decides ``defer_rule_details`` in the pipeline; ``cells``
        is the number of values they hold. Calibrated on the resident memory of
        ``run_pipeline`` (validation, normalization, consolidation and rules) in
        docs/xlsx-ingestion-budget.md. The row cost drops once the pipeline
        defers per-rule details, so the estimate is piecewise on that threshold.
        """
        row_cost = (
            DEFERRED_ROW_COST_BYTES
            if rows >= RULE_DETAIL_DEFER_ROWS
            else ROW_COST_BYTES
        )
        return rows * row_cost + cells * CELL_COST_BYTES

    def minimum_memory(self, rows: int, cells: int) -> int:
        """Lower bound of ``estimated_memory`` for any normalized count.

        Before validation the normalized count is unknown (headers, preambles,
        empty and rejected rows lower it), so admission and streaming may only
        stop early on the cheapest regime, which holds for any final count.
        """
        return rows * DEFERRED_ROW_COST_BYTES + cells * CELL_COST_BYTES

    def authorizes(self, sheet: str) -> bool:
        return self.allowed_sheets is None or sheet.casefold() in self.allowed_sheets

    def start(self) -> IngestionClock:
        return IngestionClock(self.max_seconds)


class IngestionClock:
    def __init__(self, max_seconds: float) -> None:
        self.max_seconds = max_seconds
        self._deadline = time.monotonic() + max_seconds
        self._started = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._started

    def check(self) -> None:
        if time.monotonic() > self._deadline:
            raise IngestionLimitError(
                "ingestion_time_limit",
                limit=self.max_seconds,
                observed=round(self.elapsed, 1),
            )


def _source_key(source: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", source.upper()).strip("_")


def _positive(name: str, source_key: str, default: int | float, cast=int):
    raw = os.getenv(f"{name}_{source_key}", os.getenv(name))
    if raw is None or not raw.strip():
        return default
    try:
        value = cast(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} deve ser numérico") from exc
    if value <= 0:
        raise RuntimeError(f"{name} deve ser positivo")
    return value


def _allowed_sheets(source_key: str) -> frozenset[str] | None:
    """Resolve the sheets a source may read; unset or empty authorizes none.

    Failing closed keeps auxiliary or forbidden sheets out of the pipeline when
    nobody configured the contract's sheets. ``*`` is an explicit opt-in to read
    every sheet, intended for synthetic data and controlled environments.
    """
    raw = os.getenv(f"INGESTION_ALLOWED_SHEETS_{source_key}")
    if raw is None:
        raw = os.getenv("INGESTION_ALLOWED_SHEETS", "")
    names = frozenset(
        part.strip().casefold() for part in raw.split("|") if part.strip()
    )
    return None if "*" in names else names


def budget_for(source: str) -> IngestionBudget:
    """Resolve the ingestion budget for a source from the environment.

    Every limit accepts a source suffix (for example ``INGESTION_MAX_ROWS_OWM``)
    that overrides the global value. Sheet names are separated by ``|`` because
    workbook names can contain commas.
    """
    key = _source_key(source)
    return IngestionBudget(
        max_sheets=_positive("INGESTION_MAX_SHEETS", key, DEFAULT_MAX_SHEETS),
        max_rows=_positive("INGESTION_MAX_ROWS", key, DEFAULT_MAX_ROWS),
        max_columns=_positive("INGESTION_MAX_COLUMNS", key, DEFAULT_MAX_COLUMNS),
        max_cells=_positive("INGESTION_MAX_CELLS", key, DEFAULT_MAX_CELLS),
        max_formulas=_positive("INGESTION_MAX_FORMULAS", key, DEFAULT_MAX_FORMULAS),
        max_memory_bytes=_positive(
            "INGESTION_MAX_MEMORY_BYTES", key, DEFAULT_MAX_MEMORY_BYTES
        ),
        max_seconds=_positive(
            "INGESTION_MAX_SECONDS", key, DEFAULT_MAX_SECONDS, cast=float
        ),
        max_issues=_positive("INGESTION_MAX_ISSUES", key, DEFAULT_MAX_ISSUES),
        progress_interval=_positive(
            "INGESTION_PROGRESS_INTERVAL", key, DEFAULT_PROGRESS_INTERVAL
        ),
        allowed_sheets=_allowed_sheets(key),
    )
