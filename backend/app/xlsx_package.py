from __future__ import annotations

import posixpath
import re
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, BinaryIO
from xml.etree import ElementTree

from app.ingestion_budget import IngestionBudget, IngestionClock, IngestionLimitError

if TYPE_CHECKING:
    from app.upload_security import UploadPolicy

READ_BLOCK = 1024 * 1024
MAX_STRUCTURE_BYTES = 8 * 1024 * 1024
RELATIONSHIP_ID = (
    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
)
DIMENSION = re.compile(r"^([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$")
MARKERS: tuple[tuple[bytes, str], ...] = (
    (b"macroenabled", "macro_or_active_content"),
    (b"vbaproject", "macro_or_active_content"),
    (b'targetmode="external"', "external_link"),
    (b"targetmode='external'", "external_link"),
    (b"<oleobject", "embedded_object"),
    (b":oleobject", "embedded_object"),
    (b"<!entity", "corrupted_file"),
)
LONGEST_MARKER = max(len(marker) for marker, _ in MARKERS)


class PackageViolation(Exception):
    """The package content is unsafe or unreadable; carries a stable reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class ByteLedger:
    limit: int
    total: int = 0

    def add(self, size: int) -> None:
        self.total += size
        if self.total > self.limit:
            raise PackageViolation("archive_uncompressed_limit")


@dataclass
class Totals:
    declared_cells: int = 0
    declared_rows: int = 0
    actual_cells: int = 0
    rows: int = 0
    formulas: int = 0
    processed_sheets: int = 0


@dataclass
class SheetProfile:
    name: str | None
    authorized: bool
    rows: int = 0
    columns: int = 0
    cells: int = 0
    formulas: int = 0


@dataclass
class XlsxProfile:
    sheet_names: list[str] = field(default_factory=list)
    processed: list[SheetProfile] = field(default_factory=list)
    skipped_sheets: int = 0


@dataclass(frozen=True)
class SheetRef:
    name: str
    part: str


class ScanningReader:
    """Stream an archive member in blocks, rejecting unsafe markers on the fly.

    The member is never held whole in memory: each block is scanned (with an
    overlap so markers split across blocks are still found), counted against
    the decompressed-size ledger and checked against the time budget.
    """

    def __init__(self, raw: BinaryIO, clock: IngestionClock, ledger: ByteLedger):
        self._raw = raw
        self._clock = clock
        self._ledger = ledger
        self._tail = b""
        self._buffer = b""

    def _fill(self) -> bool:
        self._clock.check()
        block = self._raw.read(READ_BLOCK)
        if not block:
            return False
        self._ledger.add(len(block))
        window = self._tail + block.lower()
        for marker, code in MARKERS:
            if marker in window:
                raise PackageViolation(code)
        self._tail = window[-(LONGEST_MARKER - 1) :]
        self._buffer = block
        return True

    def read(self, size: int = -1) -> bytes:
        if not self._buffer and not self._fill():
            return b""
        if size is None or size < 0 or size > len(self._buffer):
            size = len(self._buffer)
        chunk, self._buffer = self._buffer[:size], self._buffer[size:]
        return chunk

    def drain(self) -> None:
        while self.read(READ_BLOCK):
            pass


def _column_index(reference: str) -> int:
    index = 0
    for character in reference:
        if not character.isalpha():
            break
        index = index * 26 + ord(character.upper()) - 64
    return index


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


OPEN_PARTS = ("xl/sharedstrings.xml", "xl/styles.xml", "xl/workbook.xml")


def open_parts_bytes(archive: zipfile.ZipFile) -> int:
    """Uncompressed size of the parts openpyxl loads whole when opening a book.

    Shared strings, styles and the workbook definition are materialized by the
    reader before any row is read, so their size must be bounded up front.
    """
    return sum(
        entry.file_size
        for entry in archive.infolist()
        if entry.filename.lower() in OPEN_PARTS
        or entry.filename.lower().startswith("xl/theme/")
    )


def check_open_parts(archive: zipfile.ZipFile, budget: IngestionBudget) -> None:
    size = open_parts_bytes(archive)
    if size > budget.max_open_bytes:
        raise IngestionLimitError(
            "workbook_metadata_limit", limit=budget.max_open_bytes, observed=size
        )


def read_sheet_refs(archive: zipfile.ZipFile) -> list[SheetRef]:
    """Resolve sheet names to package parts from the (small) workbook parts."""
    members = {entry.filename.lower(): entry for entry in archive.infolist()}

    def small(name: str) -> bytes:
        entry = members.get(name)
        if entry is None or entry.file_size > MAX_STRUCTURE_BYTES:
            raise PackageViolation("corrupted_file")
        return archive.read(entry)

    try:
        workbook = ElementTree.fromstring(small("xl/workbook.xml"))
        relationships = ElementTree.fromstring(small("xl/_rels/workbook.xml.rels"))
    except ElementTree.ParseError as exc:
        raise PackageViolation("corrupted_file") from exc
    targets = {
        element.get("Id"): element.get("Target", "")
        for element in relationships.iter()
        if _local(element.tag) == "Relationship"
    }
    references: list[SheetRef] = []
    for element in workbook.iter():
        if _local(element.tag) != "sheet":
            continue
        target = targets.get(element.get(RELATIONSHIP_ID))
        name = element.get("name")
        if not target or not name:
            raise PackageViolation("corrupted_file")
        part = (
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath(posixpath.join("xl", target))
        )
        references.append(SheetRef(name, part))
    return references


def _scan_worksheet(
    reader: ScanningReader,
    profile: SheetProfile,
    *,
    budget: IngestionBudget,
    totals: Totals,
    is_dangerous: Callable[[str], bool],
) -> None:
    authorized = profile.authorized
    sheet_data = None
    row_index = 0
    for event, element in ElementTree.iterparse(reader, events=("start", "end")):  # type: ignore[arg-type]
        tag = _local(element.tag)
        if event == "start":
            if tag == "sheetData":
                sheet_data = element
            continue
        if tag == "f":
            if is_dangerous(element.text or ""):
                raise PackageViolation("dangerous_formula")
            if authorized:
                profile.formulas += 1
                totals.formulas += 1
                if totals.formulas > budget.max_formulas:
                    raise IngestionLimitError(
                        "workbook_formula_limit",
                        limit=budget.max_formulas,
                        observed=totals.formulas,
                        sheet=profile.name,
                    )
        elif tag == "dimension" and authorized:
            _check_dimension(element.get("ref", ""), profile, budget, totals)
        elif tag == "c" and authorized:
            profile.cells += 1
            totals.actual_cells += 1
            profile.columns = max(profile.columns, _column_index(element.get("r", "")))
            if totals.actual_cells > budget.max_cells:
                raise IngestionLimitError(
                    "workbook_cell_limit",
                    limit=budget.max_cells,
                    observed=totals.actual_cells,
                    sheet=profile.name,
                )
        elif tag == "row":
            if authorized:
                reference = element.get("r")
                row_index = int(reference) if reference else row_index + 1
                profile.rows = max(profile.rows, row_index)
                _check_memory(
                    budget,
                    totals.rows + profile.rows,
                    totals.actual_cells,
                    profile,
                )
                if profile.columns > budget.max_columns:
                    raise IngestionLimitError(
                        "workbook_column_limit",
                        limit=budget.max_columns,
                        observed=profile.columns,
                        sheet=profile.name,
                    )
                if profile.rows > budget.max_rows:
                    raise IngestionLimitError(
                        "workbook_row_limit",
                        limit=budget.max_rows,
                        observed=profile.rows,
                        sheet=profile.name,
                    )
            element.clear()
            if sheet_data is not None:
                sheet_data.clear()
    reader.drain()


def _check_dimension(
    reference: str,
    profile: SheetProfile,
    budget: IngestionBudget,
    totals: Totals,
) -> None:
    match = DIMENSION.match(reference.strip().upper())
    if match is None:
        return
    first_column, first_row = _column_index(match.group(1)), int(match.group(2))
    last_column = _column_index(match.group(3) or match.group(1))
    last_row = int(match.group(4) or match.group(2))
    columns = max(last_column - first_column + 1, 0)
    rows = max(last_row - first_row + 1, 0)
    if last_column > budget.max_columns:
        raise IngestionLimitError(
            "workbook_column_limit",
            limit=budget.max_columns,
            observed=last_column,
            sheet=profile.name,
        )
    if last_row > budget.max_rows:
        raise IngestionLimitError(
            "workbook_row_limit",
            limit=budget.max_rows,
            observed=last_row,
            sheet=profile.name,
        )
    totals.declared_cells += rows * columns
    totals.declared_rows += rows
    if totals.declared_cells > budget.max_cells:
        raise IngestionLimitError(
            "workbook_dimension_limit",
            limit=budget.max_cells,
            observed=totals.declared_cells,
            sheet=profile.name,
        )
    _check_memory(budget, totals.declared_rows, totals.declared_cells, profile)


def _check_memory(
    budget: IngestionBudget, rows: int, cells: int, profile: SheetProfile
) -> None:
    """Reject early only when even the cheapest pipeline regime would not fit.

    The regime that applies depends on how many records survive validation, a
    count that is unknown at admission; the pipeline applies the exact estimate
    on the execution totals once it is known.
    """
    estimate = budget.minimum_memory(rows, cells)
    if estimate > budget.max_memory_bytes:
        raise IngestionLimitError(
            "workbook_memory_limit",
            limit=budget.max_memory_bytes,
            observed=estimate,
            sheet=profile.name,
        )


def scan_package(
    archive: zipfile.ZipFile,
    policy: UploadPolicy,
    *,
    is_dangerous: Callable[[str], bool],
) -> XlsxProfile:
    """Stream every XML part once, enforcing safety and the resource budget."""
    budget = policy.budget
    clock = budget.start()
    ledger = ByteLedger(policy.max_archive_uncompressed_bytes)
    check_open_parts(archive, budget)
    references = read_sheet_refs(archive)
    profile = XlsxProfile(sheet_names=[reference.name for reference in references])
    if len(references) > budget.max_sheets:
        raise IngestionLimitError(
            "workbook_sheet_limit",
            limit=budget.max_sheets,
            observed=len(references),
        )
    by_part = {reference.part.lower(): reference.name for reference in references}
    authorized_names = [name for name in profile.sheet_names if budget.authorizes(name)]
    if budget.allowed_sheets is not None and not authorized_names:
        raise IngestionLimitError("no_authorized_sheet")
    totals = Totals()
    try:
        for entry in archive.infolist():
            lower_name = entry.filename.lower()
            if not lower_name.endswith((".xml", ".rels")):
                continue
            clock.check()
            is_sheet = (
                lower_name.startswith("xl/worksheets/")
                and lower_name.endswith(".xml")
                and "/_rels/" not in lower_name
            )
            with archive.open(entry) as raw:
                reader = ScanningReader(raw, clock, ledger)
                if not is_sheet:
                    reader.drain()
                    continue
                name = by_part.get(lower_name)
                authorized = name is not None and budget.authorizes(name)
                sheet = SheetProfile(name, authorized)
                _scan_worksheet(
                    reader,
                    sheet,
                    budget=budget,
                    totals=totals,
                    is_dangerous=is_dangerous,
                )
                if authorized:
                    totals.rows += sheet.rows
                    totals.processed_sheets += 1
                    profile.processed.append(sheet)
                else:
                    profile.skipped_sheets += 1
    except ElementTree.ParseError as exc:
        raise PackageViolation("corrupted_file") from exc
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError) as exc:
        raise PackageViolation("corrupted_file") from exc
    return profile
