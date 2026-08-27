from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

ERROR_VALUES = {"#VALUE!", "#REF!", "#DIV/0!", "#NAME?", "#N/A", "#NUM!", "#NULL!"}
KNOWN_ORGANIZATIONS = {"N-FP", "OWM", "GMES/OQC", "TMS"}


@dataclass(frozen=True)
class SourceSchema:
    required: tuple[str, ...]
    quantities: tuple[str, ...] = ()
    dates: tuple[str, ...] = ()
    identifiers: tuple[str, ...] = ()


SCHEMAS = {
    "N-FP": SourceSchema(
        required=("workorder_number", "planned_quantity", "status"),
        quantities=("planned_quantity",),
        dates=("planned_date",),
        identifiers=("workorder_number", "serial_number"),
    ),
    "OWM": SourceSchema(
        required=("workorder_number", "received_quantity", "source"),
        quantities=("received_quantity",),
        dates=("received_date",),
        identifiers=("workorder_number", "serial_number"),
    ),
    "GMES/OQC": SourceSchema(
        required=("workorder_number", "lot_number", "decision_state"),
        dates=("decision_date",),
        identifiers=("workorder_number", "lot_number", "serial_number"),
    ),
    "TMS": SourceSchema(
        required=("workorder_number", "container_number", "shipment_status"),
        dates=("shipment_date",),
        identifiers=("workorder_number", "container_number", "serial_number"),
    ),
}


class Severity:
    ERROR = "error"
    WARNING = "warning"


@dataclass
class ValidationIssue:
    code: str
    severity: str
    message: str
    file_name: str
    sheet: str | None = None
    row: int | None = None
    column: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ParsedRow:
    values: dict[str, Any]
    row: int
    sheet: str | None


def _normalized_header(value: Any) -> str:
    return str(value or "").strip().lower()


def _read_csv(path: Path) -> tuple[list[str], list[ParsedRow]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        records = list(csv.reader(stream))
    if not records:
        return [], []
    headers = [_normalized_header(cell) for cell in records[0]]
    rows = [
        ParsedRow(dict(zip(headers, record, strict=False)), number, None)
        for number, record in enumerate(records[1:], start=2)
    ]
    return headers, rows


def _read_json(path: Path) -> tuple[list[str], list[ParsedRow]]:
    with path.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    records = payload if isinstance(payload, list) else [payload]
    if not records or not all(isinstance(item, dict) for item in records):
        return [], []
    headers: list[str] = []
    for item in records:
        for key in item:
            normalized = _normalized_header(key)
            if normalized not in headers:
                headers.append(normalized)
    return headers, [
        ParsedRow({_normalized_header(k): v for k, v in item.items()}, number, None)
        for number, item in enumerate(records, start=1)
    ]


def _read_xlsx(path: Path) -> tuple[list[str], list[ParsedRow]]:
    workbook = load_workbook(path, read_only=True, data_only=False)
    headers: list[str] = []
    rows: list[ParsedRow] = []
    for sheet in workbook.worksheets:
        iterator = sheet.iter_rows()
        header_cells = next(iterator, ())
        sheet_headers = [_normalized_header(cell.value) for cell in header_cells]
        if not headers and any(sheet_headers):
            headers = sheet_headers
        for cells in iterator:
            values = {
                header: cell.value
                for header, cell in zip(sheet_headers, cells, strict=False)
                if header
            }
            rows.append(ParsedRow(values, cells[0].row if cells else 1, sheet.title))
    workbook.close()
    return headers, rows


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _valid_identifier(value: Any) -> bool:
    if isinstance(value, str) and value.startswith("="):
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", str(value).strip()))


def _valid_date(value: Any) -> bool:
    if isinstance(value, str) and value.startswith("="):
        return True
    if isinstance(value, date | datetime):
        return True
    try:
        datetime.fromisoformat(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


def _valid_quantity(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, str) and value.startswith("="):
        return True
    try:
        return Decimal(str(value).strip()) >= 0
    except (InvalidOperation, ValueError):
        return False


def validate_file(
    path: Path, extension: str, source: str, file_name: str
) -> list[dict]:
    readers = {".csv": _read_csv, ".json": _read_json, ".xlsx": _read_xlsx}
    headers, rows = readers[extension](path)
    schema = SCHEMAS[source]
    issues: list[ValidationIssue] = []

    def add(
        code: str,
        severity: str,
        message: str,
        row: int | None = None,
        column: str | None = None,
        sheet: str | None = None,
    ) -> None:
        issues.append(
            ValidationIssue(code, severity, message, file_name, sheet, row, column)
        )

    if not headers:
        add("empty_file", Severity.ERROR, "Arquivo sem registros ou cabeçalho")
        return [issue.as_dict() for issue in issues]
    for field in schema.required:
        if field not in headers:
            add(
                "missing_column",
                Severity.ERROR,
                f"Coluna obrigatória ausente: {field}",
                column=field,
            )

    nonempty_rows: list[ParsedRow] = []
    for record in rows:
        if all(_is_blank(value) for value in record.values.values()):
            add(
                "empty_row",
                Severity.WARNING,
                "Linha vazia",
                record.row,
                sheet=record.sheet,
            )
            continue
        nonempty_rows.append(record)
        for field in schema.required:
            if field in headers and _is_blank(record.values.get(field)):
                code = (
                    "missing_workorder"
                    if field == "workorder_number"
                    else "missing_required_field"
                )
                add(
                    code,
                    Severity.ERROR,
                    f"Campo obrigatório vazio: {field}",
                    record.row,
                    field,
                    record.sheet,
                )
            elif (
                field not in schema.quantities
                and field in headers
                and isinstance(record.values.get(field), dict | list)
            ):
                add(
                    "invalid_type",
                    Severity.ERROR,
                    f"Tipo de dado inválido: {field}",
                    record.row,
                    field,
                    record.sheet,
                )
        for field in schema.quantities:
            value = record.values.get(field)
            if not _is_blank(value) and not _valid_quantity(value):
                add(
                    "invalid_quantity",
                    Severity.ERROR,
                    f"Quantidade inválida: {value}",
                    record.row,
                    field,
                    record.sheet,
                )
        for field in schema.dates:
            value = record.values.get(field)
            if not _is_blank(value) and not _valid_date(value):
                add(
                    "invalid_date",
                    Severity.ERROR,
                    f"Data inválida: {value}",
                    record.row,
                    field,
                    record.sheet,
                )
        for field in schema.identifiers:
            value = record.values.get(field)
            if not _is_blank(value) and not _valid_identifier(value):
                add(
                    "invalid_identifier",
                    Severity.ERROR,
                    f"Identificador inválido: {field}",
                    record.row,
                    field,
                    record.sheet,
                )
        organization = record.values.get("organization")
        if (
            not _is_blank(organization)
            and str(organization).strip() not in KNOWN_ORGANIZATIONS
        ):
            add(
                "unknown_organization",
                Severity.ERROR,
                f"Organização desconhecida: {organization}",
                record.row,
                "organization",
                record.sheet,
            )
        for column, value in record.values.items():
            text = str(value).upper() if value is not None else ""
            error = next((item for item in ERROR_VALUES if item in text), None)
            if error:
                code = "broken_reference" if error == "#REF!" else "invalid_formula"
                add(
                    code,
                    Severity.ERROR,
                    f"Erro de fórmula preservado: {error}",
                    record.row,
                    column,
                    record.sheet,
                )

    if not nonempty_rows:
        add("empty_file", Severity.ERROR, "Arquivo sem linhas de dados")

    fingerprints: Counter[tuple[str, ...]] = Counter()
    serials: dict[str, ParsedRow] = {}
    workorders = {
        str(r.values.get("workorder_number", "")).strip() for r in nonempty_rows
    }
    for record in nonempty_rows:
        fingerprint = tuple(
            str(record.values.get(header, "")).strip() for header in headers
        )
        fingerprints[fingerprint] += 1
        if fingerprints[fingerprint] > 1:
            add(
                "duplicate_row",
                Severity.WARNING,
                "Linha duplicada",
                record.row,
                sheet=record.sheet,
            )
        serial = str(record.values.get("serial_number", "")).strip()
        if serial:
            if serial in serials:
                add(
                    "duplicate_serial",
                    Severity.ERROR,
                    f"Serial duplicado: {serial}",
                    record.row,
                    "serial_number",
                    record.sheet,
                )
            else:
                serials[serial] = record
        reference = str(record.values.get("reference_workorder_number", "")).strip()
        if reference and reference not in workorders:
            add(
                "unmatched_key",
                Severity.ERROR,
                f"Chave sem correspondência: {reference}",
                record.row,
                "reference_workorder_number",
                record.sheet,
            )

    return [issue.as_dict() for issue in issues]
