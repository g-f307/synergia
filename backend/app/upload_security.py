from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import secrets
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from io import StringIO
from pathlib import Path, PurePosixPath
from urllib.parse import unquote
from xml.etree import ElementTree

from fastapi import UploadFile

DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_RETENTION_HOURS = 24
READ_CHUNK_SIZE = 1024 * 1024
GENERIC_MEDIA_TYPES = {"", "application/octet-stream", "binary/octet-stream"}

MEDIA_TYPES = {
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel"},
    ".json": {"application/json", "text/json"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
}

DETECTED_MEDIA_TYPES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

DANGEROUS_FORMULA = re.compile(
    r"(?:^|[^A-Z0-9_.])(?:CALL|DDE|EXEC|HYPERLINK|REGISTER\.ID|RTD|"
    r"WEBSERVICE)\s*\(",
    re.IGNORECASE,
)


class InspectionDecision(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class UploadPolicy:
    source: str
    allowed_extensions: frozenset[str]
    max_bytes: int
    max_archive_entries: int
    max_archive_uncompressed_bytes: int
    max_compression_ratio: int
    rejected_retention_hours: int


@dataclass(frozen=True)
class InspectionResult:
    original_name: str
    internal_name: str
    extension: str
    declared_media_type: str
    detected_media_type: str | None
    size_bytes: int
    sha256: str
    decision: InspectionDecision
    reason_code: str
    analyzed_at: datetime
    retained_until: datetime | None
    discarded_at: datetime | None
    quarantine_path: Path | None

    @property
    def accepted(self) -> bool:
        return self.decision is InspectionDecision.ACCEPTED


class UnsafeUpload(ValueError):
    def __init__(self, reason_code: str, detected_media_type: str | None = None):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.detected_media_type = detected_media_type


def _source_env_key(source: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", source.upper()).strip("_")


def policy_for(source: str) -> UploadPolicy:
    source_key = _source_env_key(source)
    allowed_value = os.getenv(
        f"UPLOAD_ALLOWED_EXTENSIONS_{source_key}",
        os.getenv("UPLOAD_ALLOWED_EXTENSIONS", "csv,json,xlsx"),
    )
    allowed = frozenset(
        f".{value.strip().lower().lstrip('.')}"
        for value in allowed_value.split(",")
        if value.strip()
    )
    max_bytes = int(
        os.getenv(
            f"UPLOAD_MAX_BYTES_{source_key}",
            os.getenv("UPLOAD_MAX_BYTES", str(DEFAULT_MAX_BYTES)),
        )
    )
    if max_bytes <= 0:
        raise RuntimeError("UPLOAD_MAX_BYTES deve ser positivo")
    return UploadPolicy(
        source=source,
        allowed_extensions=allowed,
        max_bytes=max_bytes,
        max_archive_entries=int(os.getenv("UPLOAD_MAX_ARCHIVE_ENTRIES", "2000")),
        max_archive_uncompressed_bytes=int(
            os.getenv(
                "UPLOAD_MAX_ARCHIVE_UNCOMPRESSED_BYTES",
                str(min(max(max_bytes * 4, 50 * 1024 * 1024), 250 * 1024 * 1024)),
            )
        ),
        max_compression_ratio=int(os.getenv("UPLOAD_MAX_COMPRESSION_RATIO", "100")),
        rejected_retention_hours=max(
            0,
            int(
                os.getenv(
                    "UPLOAD_REJECTED_RETENTION_HOURS",
                    str(DEFAULT_RETENTION_HOURS),
                )
            ),
        ),
    )


def _normalized_original_name(original_name: str) -> str:
    decoded = unquote(unquote(original_name or ""))
    normalized = decoded.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not decoded
        or len(decoded) > 255
        or "\x00" in decoded
        or path.is_absolute()
        or len(path.parts) != 1
        or any(part in {".", ".."} for part in path.parts)
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        raise UnsafeUpload("path_traversal")
    return path.name


def _declared_media_type(upload: UploadFile) -> str:
    return (upload.content_type or "").split(";", 1)[0].strip().lower()


def _has_dangerous_formula(value: str) -> bool:
    candidate = value.lstrip()
    if not candidate:
        return False
    if DANGEROUS_FORMULA.search(candidate):
        return True
    return candidate.startswith(("=|", "+|", "@", "\t", "\r")) or "![" in candidate


def _detect_text_type(path: Path, extension: str) -> str:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnsafeUpload("invalid_text_encoding") from exc
    sample = text.lstrip().lower()
    if sample.startswith(
        (
            "<!doctype html",
            "<html",
            "<script",
            "javascript:",
            "function ",
            "const ",
            "let ",
            "var ",
        )
    ):
        raise UnsafeUpload("disguised_active_content", "text/html")
    if "\x00" in text:
        raise UnsafeUpload("binary_content_mismatch", "application/octet-stream")

    if extension == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise UnsafeUpload("corrupted_file", "application/json") from exc
        stack = [value]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
            elif isinstance(current, str) and _has_dangerous_formula(current):
                raise UnsafeUpload("dangerous_formula", "application/json")
        return DETECTED_MEDIA_TYPES[extension]

    if sample.startswith(("{", "[")):
        try:
            json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            raise UnsafeUpload("content_type_mismatch", "application/json")

    try:
        rows = csv.reader(StringIO(text))
        for row in rows:
            if any(_has_dangerous_formula(cell) for cell in row):
                raise UnsafeUpload("dangerous_formula", "text/csv")
    except csv.Error as exc:
        raise UnsafeUpload("corrupted_file", "text/csv") from exc
    return DETECTED_MEDIA_TYPES[extension]


def _safe_archive_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return not path.is_absolute() and all(
        part not in {"", ".", ".."} for part in path.parts
    )


def _validate_xlsx_archive(path: Path, policy: UploadPolicy) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > policy.max_archive_entries:
                raise UnsafeUpload("archive_too_many_entries")
            total_uncompressed = 0
            for entry in entries:
                if not _safe_archive_name(entry.filename):
                    raise UnsafeUpload("archive_path_traversal")
                if entry.flag_bits & 0x1:
                    raise UnsafeUpload("encrypted_archive")
                total_uncompressed += entry.file_size
                if total_uncompressed > policy.max_archive_uncompressed_bytes:
                    raise UnsafeUpload("archive_uncompressed_limit")
                if (
                    entry.file_size
                    and entry.file_size / max(entry.compress_size, 1)
                    > policy.max_compression_ratio
                ):
                    raise UnsafeUpload("archive_compression_ratio")

            names = {entry.filename.lower() for entry in entries}
            if "[content_types].xml" not in names or "xl/workbook.xml" not in names:
                raise UnsafeUpload("content_signature_mismatch", "application/zip")
            if any(
                marker in name
                for name in names
                for marker in (
                    "vbaproject.bin",
                    "xl/activex/",
                    "xl/macrosheets/",
                    "customui/",
                )
            ):
                raise UnsafeUpload("macro_or_active_content")
            if any(name.startswith("xl/embeddings/") for name in names):
                raise UnsafeUpload("embedded_object")
            if any(name.startswith("xl/externallinks/") for name in names):
                raise UnsafeUpload("external_link")
            if "xl/connections.xml" in names:
                raise UnsafeUpload("external_link")

            for entry in entries:
                lower_name = entry.filename.lower()
                if not lower_name.endswith((".xml", ".rels")):
                    continue
                payload = archive.read(entry)
                lowered = payload.lower()
                if b"macroenabled" in lowered or b"vbaproject" in lowered:
                    raise UnsafeUpload("macro_or_active_content")
                if (
                    b'targetmode="external"' in lowered
                    or b"targetmode='external'" in lowered
                ):
                    raise UnsafeUpload("external_link")
                if b"<oleobject" in lowered or b":oleobject" in lowered:
                    raise UnsafeUpload("embedded_object")
                if lower_name.startswith("xl/worksheets/"):
                    try:
                        root = ElementTree.fromstring(payload)
                    except ElementTree.ParseError as exc:
                        raise UnsafeUpload("corrupted_file") from exc
                    for formula in root.iter():
                        if formula.tag.rsplit("}", 1)[
                            -1
                        ] == "f" and _has_dangerous_formula(formula.text or ""):
                            raise UnsafeUpload("dangerous_formula")

            if archive.testzip() is not None:
                raise UnsafeUpload("corrupted_file")
    except zipfile.BadZipFile as exc:
        raise UnsafeUpload("corrupted_file") from exc
    return DETECTED_MEDIA_TYPES[".xlsx"]


def inspect_content(path: Path, extension: str, policy: UploadPolicy) -> str:
    if extension == ".xlsx":
        with path.open("rb") as stream:
            signature = stream.read(4)
        if signature != b"PK\x03\x04":
            raise UnsafeUpload("content_signature_mismatch", "application/octet-stream")
        return _validate_xlsx_archive(path, policy)
    return _detect_text_type(path, extension)


def _rejected_result(
    *,
    original_name: str,
    internal_name: str,
    extension: str,
    declared_media_type: str,
    detected_media_type: str | None,
    size_bytes: int,
    sha256: str,
    reason_code: str,
    quarantine_path: Path,
    policy: UploadPolicy,
    analyzed_at: datetime,
) -> InspectionResult:
    retained_until = analyzed_at + timedelta(hours=policy.rejected_retention_hours)
    discarded_at = None
    retained_path: Path | None = quarantine_path
    if policy.rejected_retention_hours == 0 or reason_code == "file_too_large":
        quarantine_path.unlink(missing_ok=True)
        retained_path = None
        discarded_at = analyzed_at
        retained_until = analyzed_at
    return InspectionResult(
        original_name=original_name,
        internal_name=internal_name,
        extension=extension,
        declared_media_type=declared_media_type,
        detected_media_type=detected_media_type,
        size_bytes=size_bytes,
        sha256=sha256,
        decision=InspectionDecision.REJECTED,
        reason_code=reason_code,
        analyzed_at=analyzed_at,
        retained_until=retained_until,
        discarded_at=discarded_at,
        quarantine_path=retained_path,
    )


async def receive_and_inspect(
    upload: UploadFile,
    *,
    source: str,
    execution_id: str,
    root: Path,
) -> InspectionResult:
    policy = policy_for(source)
    declared_media_type = _declared_media_type(upload)
    internal_stem = secrets.token_hex(24)
    quarantine_directory = root / "quarantine" / execution_id
    quarantine_directory.mkdir(parents=True, exist_ok=True)
    quarantine_path = quarantine_directory / f"{internal_stem}.upload"
    digest = hashlib.sha256()
    size_bytes = 0
    stored_bytes = 0
    with quarantine_path.open("xb") as stream:
        while chunk := await upload.read(READ_CHUNK_SIZE):
            size_bytes += len(chunk)
            digest.update(chunk)
            if stored_bytes <= policy.max_bytes:
                writable = chunk[: max(0, policy.max_bytes + 1 - stored_bytes)]
                stream.write(writable)
                stored_bytes += len(writable)

    raw_name = upload.filename or ""
    safe_name = Path(raw_name.replace("\\", "/")).name
    extension = Path(safe_name).suffix.lower()
    analyzed_at = datetime.now(UTC)
    sha256 = digest.hexdigest()
    detected_media_type: str | None = None
    try:
        original_name = _normalized_original_name(raw_name)
        extension = Path(original_name).suffix.lower()
        if extension not in policy.allowed_extensions or extension not in MEDIA_TYPES:
            raise UnsafeUpload("unsupported_extension")
        if size_bytes == 0:
            raise UnsafeUpload("empty_file")
        if size_bytes > policy.max_bytes:
            raise UnsafeUpload("file_too_large")
        detected_media_type = inspect_content(quarantine_path, extension, policy)
        if (
            declared_media_type not in GENERIC_MEDIA_TYPES
            and declared_media_type not in MEDIA_TYPES[extension]
        ):
            raise UnsafeUpload("declared_mime_mismatch", detected_media_type)
        internal_name = f"{internal_stem}{extension}"
        return InspectionResult(
            original_name=original_name,
            internal_name=internal_name,
            extension=extension,
            declared_media_type=declared_media_type,
            detected_media_type=detected_media_type,
            size_bytes=size_bytes,
            sha256=sha256,
            decision=InspectionDecision.ACCEPTED,
            reason_code="accepted",
            analyzed_at=analyzed_at,
            retained_until=None,
            discarded_at=None,
            quarantine_path=quarantine_path,
        )
    except UnsafeUpload as exc:
        rejected_extension = extension if extension in MEDIA_TYPES else ""
        rejected_name = (raw_name or "unnamed")[:255].replace("\x00", "�")
        return _rejected_result(
            original_name=rejected_name,
            internal_name=f"{internal_stem}{rejected_extension}",
            extension=extension,
            declared_media_type=declared_media_type,
            detected_media_type=exc.detected_media_type or detected_media_type,
            size_bytes=size_bytes,
            sha256=sha256,
            reason_code=exc.reason_code,
            quarantine_path=quarantine_path,
            policy=policy,
            analyzed_at=analyzed_at,
        )


def release_to_accepted(
    result: InspectionResult,
    *,
    source_key: str,
    execution_id: str,
    root: Path,
) -> Path:
    if not result.accepted or result.quarantine_path is None:
        raise ValueError("Somente arquivos aceitos podem sair da quarentena")
    destination = root / "accepted" / source_key / execution_id / result.internal_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.quarantine_path.replace(destination)
    try:
        result.quarantine_path.parent.rmdir()
    except OSError:
        pass
    return destination


def purge_quarantined(root: Path, internal_stems: list[str]) -> list[str]:
    removed: list[str] = []
    quarantine = root / "quarantine"
    if not quarantine.is_dir():
        return removed
    for internal_stem in internal_stems:
        if not re.fullmatch(r"[0-9a-f]{48}", internal_stem):
            continue
        removed.append(internal_stem)
        for path in quarantine.glob(f"*/{internal_stem}.upload"):
            if path.is_file():
                path.unlink(missing_ok=True)
    for directory in sorted(quarantine.glob("*")):
        if directory.is_dir():
            try:
                directory.rmdir()
            except OSError:
                pass
    return removed
