from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

SPEC_PATH = Path(__file__).with_name("model") / "wo_status_adapter.json"
COMPOSITE_SOURCE = "WO Status"
KINDS = frozenset(
    {"id", "text", "status", "flag", "qty", "qty_int", "date", "datetime"}
)
WINDOW_MODES = frozenset({"all", "last_literal", "substantive"})


def column_index(letters: str) -> int:
    index = 0
    for character in letters.upper():
        index = index * 26 + ord(character) - 64
    return index


@dataclass(frozen=True)
class ColumnSpec:
    letter: str
    index: int
    header: str
    field: str
    kind: str
    contract_target: str


@dataclass(frozen=True)
class SheetSpec:
    name: str
    logical_source: str
    header_row: int
    data_start_row: int
    window_mode: str
    window_field: str | None
    identity_any: tuple[str, ...]
    identity_all: tuple[str, ...]
    blocked: str | None
    columns: tuple[ColumnSpec, ...]

    @property
    def max_column(self) -> int:
        return max(column.index for column in self.columns)


@dataclass(frozen=True)
class AdapterSpec:
    adapter_id: str
    adapter_version: str
    contract_version: str
    source: str
    sheets: tuple[SheetSpec, ...]

    @property
    def label(self) -> str:
        return f"{self.adapter_id}@{self.adapter_version}"

    def sheet(self, name: str) -> SheetSpec | None:
        key = name.casefold()
        return next((s for s in self.sheets if s.name.casefold() == key), None)

    def authorized_names(self) -> frozenset[str]:
        return frozenset(sheet.name.casefold() for sheet in self.sheets)

    def selected_columns(self) -> dict[str, frozenset[int]]:
        return {
            sheet.name.casefold(): frozenset(c.index for c in sheet.columns)
            for sheet in self.sheets
        }


class AdapterSpecError(ValueError):
    pass


def _sheet(name: str, raw: dict[str, Any]) -> SheetSpec:
    window = raw["window"]
    if window["mode"] not in WINDOW_MODES:
        raise AdapterSpecError(f"{name}: janela inválida {window['mode']!r}")
    columns = []
    for item in raw["columns"]:
        if item["kind"] not in KINDS:
            raise AdapterSpecError(f"{name}: tipo inválido {item['kind']!r}")
        columns.append(
            ColumnSpec(
                letter=item["letter"],
                index=column_index(item["letter"]),
                header=item["header"],
                field=item["field"],
                kind=item["kind"],
                contract_target=item["contract_target"],
            )
        )
    fields = [column.field for column in columns]
    if len(fields) != len(set(fields)) or len(
        {column.letter for column in columns}
    ) != len(columns):
        raise AdapterSpecError(f"{name}: colunas ou campos duplicados")
    identity = raw.get("identity", {})
    unknown = (set(identity.get("any", ())) | set(identity.get("all", ()))) - set(
        fields
    )
    if unknown or (window.get("field") and window["field"] not in fields):
        raise AdapterSpecError(f"{name}: identidade ou janela fora das colunas")
    return SheetSpec(
        name=name,
        logical_source=raw["logical_source"],
        header_row=int(raw["header_row"]),
        data_start_row=int(raw["data_start_row"]),
        window_mode=window["mode"],
        window_field=window.get("field"),
        identity_any=tuple(identity.get("any", ())),
        identity_all=tuple(identity.get("all", ())),
        blocked=raw.get("blocked"),
        columns=tuple(columns),
    )


@lru_cache(maxsize=1)
def load_spec() -> AdapterSpec:
    raw = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    return AdapterSpec(
        adapter_id=raw["adapter_id"],
        adapter_version=raw["adapter_version"],
        contract_version=raw["contract_version"],
        source=raw["source"],
        sheets=tuple(_sheet(name, sheet) for name, sheet in raw["sheets"].items()),
    )
