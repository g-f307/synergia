"""Incremental Total Decision reader with minimization before the pipeline."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from app.normalization import normalize_state
from app.spreadsheet_reader import IngestionRun, open_workbook
from app.total_decision_spec import SOURCE, load_spec
from app.validation import FORMULA_ERRORS, SourceSchema, _issue
from app.wo_status import AdapterRow, AdapterRows, DriftedRows, convert

SCHEMA = SourceSchema((), {}, (), ())


class TotalDecisionRows(AdapterRows):
    def _convert(
        self, number: int, values: tuple
    ) -> tuple[AdapterRow, dict[str, bool]]:
        converted, originals, issues = [], [], []
        present = {}
        for column in self.spec.columns:
            raw = values[column.index - 1] if column.index <= len(values) else None
            exists = raw is not None and str(raw).strip() != ""
            if column.kind == "restricted":
                # Never put the original into an imported record, transformation,
                # normalized artifact, issue, log or report.
                value = exists
                original = exists
                cell_issues = []
                if isinstance(raw, str) and (
                    raw.lstrip().startswith("=") or raw in FORMULA_ERRORS
                ):
                    cell_issues.append(
                        _issue(
                            "formula_not_allowed",
                            "Conteúdo calculado ou inválido",
                            column=column.letter,
                        )
                    )
                if exists:
                    cell_issues.append(
                        _issue(
                            "restricted_value_minimized",
                            "Campo restrito: somente presença preservada",
                            severity="warning",
                            column=column.letter,
                        )
                    )
            else:
                if column.kind == "id" and (
                    isinstance(raw, bool)
                    or isinstance(raw, float)
                    and not math.isfinite(raw)
                ):
                    value = None
                    cell_issues = [
                        _issue(
                            "invalid_identifier",
                            "Identificador inválido",
                            column=column.letter,
                        )
                    ]
                else:
                    value, cell_issues = convert(column, raw)
                original = raw
                if column.kind == "status" and exists and not cell_issues:
                    value, known = normalize_state(value)
                    if not known:
                        # Preserve unknown values rather than manufacture a
                        # business meaning for a source-specific result code.
                        value = raw.strip() if isinstance(raw, str) else raw
                        cell_issues.append(
                            _issue(
                                "unknown_state",
                                "Estado sem catálogo confirmado",
                                severity="warning",
                                column=column.letter,
                            )
                        )
            converted.append(value)
            originals.append(original)
            issues.extend(cell_issues)
            present[column.field] = exists and value is not None
        if not present.get("workorder_number") and present.get("workorder_id"):
            issues.append(
                _issue(
                    "workorder_relationship_pending",
                    "ID preservado sem inferir número de Workorder",
                    severity="warning",
                )
            )
        row = AdapterRow(converted, number)
        row.original_values = originals
        row.adapter_issues = issues
        return row, present


def _header_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


class TotalDecisionImporter:
    def read(self, path: Path, extension: str, source: str):
        if extension != ".xlsx":
            raise ValueError("A fonte Total Decision exige arquivo XLSX")
        spec = load_spec()
        run = IngestionRun(SOURCE)
        issues = []
        tables = []
        with open_workbook(path, run.budget) as book:
            for name in book.sheetnames:
                if name != spec.sheet.name:
                    # Even an unexpected sheet's name may contain private data.
                    issues.append(
                        _issue(
                            "sheet_ignored",
                            "Aba fora do contrato não ingerida",
                            severity="warning",
                        )
                    )
                    continue
                if not run.budget.authorizes(name):
                    issues.append(
                        _issue(
                            "sheet_not_authorized",
                            "Aba não autorizada neste ambiente",
                            sheet=name,
                        )
                    )
                    continue
                worksheet = book[name]
                headers = list(
                    worksheet.iter_rows(
                        min_row=1,
                        max_row=2,
                        max_col=worksheet.max_column,
                        values_only=True,
                    )
                )
                drift = self._header_drift(headers)
                if drift:
                    issues.extend(drift)
                    tables.append((name, [], DriftedRows(spec.sheet)))
                    continue
                allowed = {c.index for c in spec.sheet.columns}
                for index in range(1, worksheet.max_column + 1):
                    if index not in allowed and any(row[index - 1] for row in headers):
                        issues.append(
                            _issue(
                                "column_ignored",
                                "Coluna fora da allowlist não ingerida",
                                severity="warning",
                                sheet=name,
                                column=str(index),
                            )
                        )
                rows = TotalDecisionRows(path, spec.sheet, spec.label, run)
                tables.append((name, rows.headers, rows))
            if spec.sheet.name not in book.sheetnames:
                issues.append(
                    _issue(
                        "missing_column",
                        "Aba contratada ausente",
                        sheet=spec.sheet.name,
                    )
                )
        return tables, issues

    @staticmethod
    def _header_drift(headers: list[tuple]) -> list[dict]:
        spec = load_spec()
        issues = []
        for column in spec.sheet.columns:
            index = column.index - 1
            top, bottom = (row[index] if index < len(row) else None for row in headers)
            expected = tuple(_header_text(part) for part in column.header_path)
            if len(expected) == 1:
                found = (_header_text(top),)
                valid = found == expected and not bottom
            else:
                anchor = (
                    min(
                        c.index
                        for c in spec.sheet.columns
                        if c.header_path[0] == column.header_path[0]
                    )
                    - 1
                )
                # Fill only the group's declared interval; never propagate an
                # arbitrary header across unrelated or repeated columns.
                parent = headers[0][anchor]
                group_valid = all(
                    not value or _header_text(value) == expected[0]
                    for value in headers[0][anchor : index + 1]
                )
                valid = (
                    group_valid
                    and (_header_text(top or parent), _header_text(bottom)) == expected
                )
            if not valid:
                issues.append(
                    _issue(
                        "contract_drift",
                        "Cabeçalho multinível diverge do contrato",
                        sheet=spec.sheet.name,
                        column=column.letter,
                        row=2,
                    )
                )
        return issues


def expand_total_decision(item: dict[str, Any]) -> dict[str, Any]:
    return {**item, "source": "GMES/OQC", "schema": SCHEMA}
