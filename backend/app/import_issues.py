"""Public import diagnostics: safe locations and catalog messages, never cell values."""

import csv
import math
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from io import StringIO
from typing import Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app.execution_summary import start_execution_snapshot
from app.normalization import COLUMN_ALIASES, DATE_FIELDS, IDENTIFIER_FIELDS
from app.pipeline_issue_query import import_execution_visible, pipeline_issue_query
from app.total_decision_spec import load_spec as decision_spec
from app.validation import SCHEMAS
from app.wo_status_spec import column_index
from app.wo_status_spec import load_spec as wo_spec

# Messages are deliberately independent of stored free text, including exception
# messages and the values interpolated by older versions of the pipeline.
ISSUE_REASONS = {
    "broken_reference": "Referência de fórmula inválida na célula indicada.",
    "column_ignored": "Coluna fora do contrato; seu conteúdo não foi ingerido.",
    "contract_blocked": "Aba bloqueada: a chave de relacionamento não foi confirmada.",
    "contract_drift": "Cabeçalho divergente do contrato de importação.",
    "duplicate_row": "Linha repetida no mesmo arquivo e aba.",
    "duplicate_serial": "Serial repetido no arquivo.",
    "empty_file": "Arquivo sem linhas de dados reconhecidas.",
    "empty_row": "Linha vazia ignorada.",
    "empty_sheet": "Aba sem linhas de dados reconhecidas.",
    "formula_not_allowed": "Conteúdo calculado não permitido como fonte primária.",
    "gap_in_active_region": "Linha vazia dentro da região ativa da aba.",
    "identifier_stored_as_number": (
        "Identificador numérico; zeros iniciais podem ter sido perdidos."
    ),
    "invalid_date": "Data inválida no campo indicado.",
    "invalid_formula": "Erro de fórmula na célula indicada.",
    "invalid_header": "Cabeçalho vazio ou inválido.",
    "invalid_identifier": "Identificador em formato inválido.",
    "invalid_quantity": "Quantidade inválida; confira o formato e os limites do campo.",
    "invalid_structure": "Estrutura do arquivo incompatível com o contrato.",
    "missing_column": "Coluna ou aba obrigatória ausente no contrato recebido.",
    "missing_identity": "Identificador obrigatório ausente na linha.",
    "read_error": "Não foi possível ler a estrutura do arquivo ou a linha indicada.",
    "required_field": (
        "Campo obrigatório vazio ou identificador de relacionamento ausente."
    ),
    "restricted_value_minimized": (
        "Campo restrito: somente sua presença foi preservada."
    ),
    "sheet_ignored": "Aba fora do contrato; seu conteúdo não foi ingerido.",
    "sheet_missing": "Aba obrigatória ausente.",
    "sheet_not_authorized": "Aba não autorizada neste ambiente.",
    "unknown_boolean_flag": "Indicador lógico sem mapeamento reconhecido.",
    "unknown_oqc_flag": "Indicador OQC sem mapeamento reconhecido.",
    "unknown_organization": "Organização não reconhecida no escopo da importação.",
    "unknown_state": "Situação sem mapeamento reconhecido.",
    "unmatched_key": "Chave sem correspondência no relacionamento esperado.",
    "unparsed_date": "Formato de data não reconhecido; confira o campo indicado.",
    "validation_read_error": "Falha na leitura durante a validação do arquivo.",
    "workorder_processing_failed": (
        "Falha no processamento da ordem; solicite análise ao suporte."
    ),
    "workorder_relationship_pending": (
        "Identificador preservado; vínculo com a ordem não confirmado."
    ),
    "unmapped_issue": (
        "Divergência sem descrição pública disponível; solicite análise ao suporte."
    ),
}


def _public_locations() -> tuple[frozenset[str], frozenset[str]]:
    sheets = {"CSV", "JSON", "Data", "Dados", "Planilha", "Sheet"}
    fields = set(COLUMN_ALIASES) | set(COLUMN_ALIASES.values())
    fields.update(DATE_FIELDS | IDENTIFIER_FIELDS)
    fields.update({"status", "reason", "model", "oqc_flag", "quantity"})
    for schema in SCHEMAS.values():
        fields.update(schema.required + schema.quantities + schema.dates)
        fields.update(schema.aliases)
        fields.update(schema.aliases.values())
    for sheet in (*wo_spec().sheets, decision_spec().sheet):
        sheets.add(sheet.name)
        for column in sheet.columns:
            fields.update(
                (column.field, column.header, f"{column.letter}:{column.header}")
            )
    return frozenset(sheets), frozenset(fields)


PUBLIC_SHEETS, PUBLIC_COLUMNS = _public_locations()
CSV_FIELDS = (
    "id",
    "severity",
    "safe_file_name",
    "sheet_name",
    "row_number",
    "column_name",
    "code",
    "reason",
    "scope",
    "occurred_at",
)


class ImportIssue(BaseModel):
    id: int
    severity: Literal["error", "warning"]
    safe_file_name: str | None = None
    sheet_name: str | None = None
    row_number: int | None = Field(default=None, ge=1)
    column_name: str | None = None
    code: str
    reason: str
    scope: Literal["file", "structure", "record"]
    occurred_at: datetime


class ImportIssuePagination(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class ImportIssuePage(BaseModel):
    items: list[ImportIssue]
    pagination: ImportIssuePagination
    sort: Literal["oldest", "newest"]
    generated_at: datetime


def public_import_issue(row: dict) -> ImportIssue:
    """Only contract-defined labels pass; arbitrary text fails closed to null."""
    extension = row["extension"]
    suffix = f".{extension}" if extension in {"csv", "json", "xlsx"} else ""
    sheet = row["sheet_name"]
    sheet = (
        sheet
        if sheet in PUBLIC_SHEETS
        or (
            isinstance(sheet, str)
            and re.fullmatch(r"(?:Sheet|Planilha|Aba) ?[1-9]\d{0,2}", sheet)
        )
        else None
    )
    column = row["column_name"]
    column = (
        column
        if column in PUBLIC_COLUMNS
        or (
            isinstance(column, str)
            and re.fullmatch(r"[A-Z]{1,3}", column)
            and column_index(column) <= 16384
        )
        else None
    )
    code = row["code"] if row["code"] in ISSUE_REASONS else "unmapped_issue"
    return ImportIssue(
        id=row["id"],
        severity=row["severity"],
        safe_file_name=(
            f"arquivo-{row['source_file_id']}{suffix}"
            if row["source_file_id"] is not None
            else None
        ),
        sheet_name=sheet,
        column_name=column,
        row_number=row["row_number"] if (row["row_number"] or 0) > 0 else None,
        code=code,
        reason=ISSUE_REASONS[code],
        scope=row["scope"],
        occurred_at=row["occurred_at"],
    )


def read_import_issues(
    connection: psycopg.Connection,
    execution_id: str,
    *,
    organization_scopes: frozenset[UUID] | None,
    severity: Literal["error", "warning"] | None,
    page: int,
    page_size: int,
    sort: Literal["oldest", "newest"],
) -> ImportIssuePage | None:
    start_execution_snapshot(connection)
    if not import_execution_visible(connection, execution_id, organization_scopes):
        return None
    query = pipeline_issue_query(
        execution_id,
        projection="import",
        organization_scopes=organization_scopes,
        severity=severity,
        sort=sort,
    )
    rows, total = query.page(connection, page=page, page_size=page_size)
    generated_at = connection.execute(
        "SELECT transaction_timestamp() AS at"
    ).fetchone()["at"]
    return ImportIssuePage(
        items=[public_import_issue(row) for row in rows],
        pagination=ImportIssuePagination(
            page=page,
            page_size=page_size,
            total=total,
            pages=math.ceil(total / page_size) if total else 0,
        ),
        sort=sort,
        generated_at=generated_at.astimezone(UTC),
    )


def safe_csv_cell(value) -> str:
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _csv_chunks(cursor, first_rows: list[dict]) -> Iterator[str]:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(CSV_FIELDS)
    yield "\ufeff" + buffer.getvalue()
    rows = first_rows
    while rows:
        buffer.seek(0)
        buffer.truncate()
        for row in rows:
            issue = public_import_issue(row).model_dump(mode="json")
            writer.writerow([safe_csv_cell(issue[field]) for field in CSV_FIELDS])
        yield buffer.getvalue()
        rows = cursor.fetchmany(500)


@contextmanager
def open_import_issue_csv(
    connection: psycopg.Connection,
    execution_id: str,
    *,
    organization_scopes: frozenset[UUID] | None,
    severity: Literal["error", "warning"] | None,
    sort: Literal["oldest", "newest"],
) -> Iterator[Iterator[str] | None]:
    """One read-only snapshot, bounded batches, no artifact or temporary file."""
    start_execution_snapshot(connection)
    if not import_execution_visible(connection, execution_id, organization_scopes):
        yield None
        return
    query = pipeline_issue_query(
        execution_id,
        projection="import",
        organization_scopes=organization_scopes,
        severity=severity,
        sort=sort,
    )
    with connection.cursor(name="import_issue_export", row_factory=dict_row) as cursor:
        cursor.execute(query.select_sql(), query.parameters)
        # Prepare the first batch before sending headers: connection/query failures
        # still have the structured 503 contract, rather than a false CSV success.
        rows = cursor.fetchmany(500)
        yield _csv_chunks(cursor, rows)
