"""Versioned structural contract; importing it performs no workbook I/O."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.wo_status_spec import ColumnSpec, SheetSpec, column_index

SOURCE = "Total Decision"
SPEC_PATH = Path(__file__).with_name("model") / "total_decision_adapter.json"
KINDS = frozenset({"id", "text", "status", "date", "datetime", "qty", "restricted"})


@dataclass(frozen=True)
class DecisionColumn(ColumnSpec):
    header_path: tuple[str, ...]


@dataclass(frozen=True)
class DecisionSpec:
    adapter_id: str
    adapter_version: str
    contract_version: str
    source: str
    sheet: SheetSpec
    summary_rows: tuple[int, ...]

    @property
    def label(self) -> str:
        return f"{self.adapter_id}@{self.adapter_version}"

    def authorized_names(self) -> frozenset[str]:
        return frozenset({self.sheet.name.casefold()})

    def selected_columns(self) -> dict[str, frozenset[int]]:
        return {
            self.sheet.name.casefold(): frozenset(c.index for c in self.sheet.columns)
        }


@lru_cache(maxsize=1)
def load_spec() -> DecisionSpec:
    raw = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    if (
        raw["source"] != SOURCE
        or raw["header_rows"] != [1, 2]
        or raw["summary_rows"] != [3]
        or raw["data_start_row"] != 4
        or not re.fullmatch(r"\d+\.\d+\.\d+", raw["adapter_version"])
    ):
        raise ValueError("Contrato Total Decision inválido")
    columns = []
    for column in raw["columns"]:
        path = column["header_path"]
        if (
            column["kind"] not in KINDS
            or not re.fullmatch(r"[A-Z]{1,3}", column["letter"])
            or not isinstance(path, list)
            or not 1 <= len(path) <= 2
            or not all(isinstance(part, str) and part.strip() for part in path)
        ):
            raise ValueError("Coluna Total Decision inválida")
        columns.append(
            DecisionColumn(
                letter=column["letter"],
                index=column_index(column["letter"]),
                header=" / ".join(path),
                header_path=tuple(path),
                field=column["field"],
                kind=column["kind"],
                contract_target=column["contract_target"],
            )
        )
    fields = {c.field for c in columns}
    if (
        not columns
        or len(fields) != len(columns)
        or len({c.index for c in columns}) != len(columns)
        or not set(raw["identity"]["all"] + raw["identity"]["any"]) <= fields
        or raw["identity"]
        != {"all": ["oqc_lot_id"], "any": ["workorder_number", "workorder_id"]}
        or any(
            c.kind == "restricted" and not c.field.endswith("_present") for c in columns
        )
    ):
        raise ValueError("Identidade ou colunas Total Decision inválidas")
    sheet = SheetSpec(
        name=raw["sheet"],
        logical_source="GMES/OQC",
        header_row=2,
        data_start_row=4,
        window_mode="all",
        window_field=None,
        identity_any=tuple(raw["identity"]["any"]),
        identity_all=tuple(raw["identity"]["all"]),
        blocked=None,
        columns=tuple(columns),
    )
    return DecisionSpec(
        raw["adapter_id"],
        raw["adapter_version"],
        raw["contract_version"],
        SOURCE,
        sheet,
        tuple(raw["summary_rows"]),
    )
