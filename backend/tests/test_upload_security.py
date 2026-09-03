from __future__ import annotations

import asyncio
import hashlib
import zipfile
from io import BytesIO

import pytest
from openpyxl import Workbook
from starlette.datastructures import Headers, UploadFile

from app.upload_security import policy_for, purge_quarantined, receive_and_inspect

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_bytes(formula: str | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["workorder", "status"])
    sheet.append(["WO-1", formula or "open"])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _xlsx_with_entry(name: str, content: bytes = b"blocked") -> bytes:
    source = BytesIO(_xlsx_bytes())
    target = BytesIO()
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as modified,
    ):
        for entry in original.infolist():
            modified.writestr(entry, original.read(entry))
        modified.writestr(name, content)
    return target.getvalue()


def _zip_bomb_xlsx() -> bytes:
    target = BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("xl/workbook.xml", b"<workbook/>")
        archive.writestr("xl/sharedStrings.xml", b"A" * (2 * 1024 * 1024))
    return target.getvalue()


def _inspect(tmp_path, filename: str, content: bytes, media_type: str):
    upload = UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": media_type}),
    )
    return asyncio.run(
        receive_and_inspect(
            upload,
            source="N-FP",
            execution_id="security-test",
            root=tmp_path,
        )
    )


@pytest.mark.parametrize(
    ("filename", "content", "media_type", "reason"),
    [
        (
            "renamed.xlsx",
            b"MZ\x90\x00executable",
            XLSX_MIME,
            "content_signature_mismatch",
        ),
        (
            "page.csv",
            b"<!doctype html><script>alert(1)</script>",
            "text/csv",
            "disguised_active_content",
        ),
        (
            "script.csv",
            b"function launch() { return true; }",
            "text/csv",
            "disguised_active_content",
        ),
        (
            "renamed.csv",
            b'{"workorder": "WO-1"}',
            "text/csv",
            "content_type_mismatch",
        ),
        ("data.csv", b"id\n1\n", "application/json", "declared_mime_mismatch"),
        ("broken.xlsx", b"PK\x03\x04truncated", XLSX_MIME, "corrupted_file"),
        (
            "unknown.bin",
            b"unknown",
            "application/octet-stream",
            "unsupported_extension",
        ),
        ("book.xlsm", _xlsx_bytes(), XLSX_MIME, "unsupported_extension"),
        (
            "macro.xlsx",
            _xlsx_with_entry("xl/vbaProject.bin"),
            XLSX_MIME,
            "macro_or_active_content",
        ),
        (
            "object.xlsx",
            _xlsx_with_entry("xl/embeddings/oleObject1.bin"),
            XLSX_MIME,
            "embedded_object",
        ),
        (
            "external.xlsx",
            _xlsx_with_entry("xl/externalLinks/externalLink1.xml"),
            XLSX_MIME,
            "external_link",
        ),
        (
            "formula.xlsx",
            _xlsx_bytes('=WEBSERVICE("https://invalid")'),
            XLSX_MIME,
            "dangerous_formula",
        ),
        ("bomb.xlsx", _zip_bomb_xlsx(), XLSX_MIME, "archive_compression_ratio"),
    ],
)
def test_rejects_disguised_active_and_abusive_files(
    tmp_path, filename, content, media_type, reason
) -> None:
    result = _inspect(tmp_path, filename, content, media_type)

    assert result.accepted is False
    assert result.reason_code == reason
    assert len(result.sha256) == 64
    assert not list((tmp_path / "accepted").glob("**/*"))


def test_rejects_path_traversal_and_does_not_use_original_name_as_path(
    tmp_path,
) -> None:
    result = _inspect(tmp_path, "../secret.csv", b"id\n1\n", "text/csv")

    assert result.reason_code == "path_traversal"
    assert result.original_name == "../secret.csv"
    assert "secret" not in result.internal_name
    assert all("secret" not in path.name for path in tmp_path.glob("**/*"))


def test_applies_source_size_limit_while_hashing_the_complete_content(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("UPLOAD_MAX_BYTES_N_FP", "8")
    content = b"id\n123456789\n"

    result = _inspect(tmp_path, "large.csv", content, "text/csv")

    assert result.reason_code == "file_too_large"
    assert result.size_bytes == len(content)
    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.quarantine_path is None


def test_applies_allowed_formats_per_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_ALLOWED_EXTENSIONS_N_FP", "csv")

    result = _inspect(tmp_path, "book.xlsx", _xlsx_bytes(), XLSX_MIME)

    assert result.reason_code == "unsupported_extension"


def test_rejects_configured_extension_without_an_inspector(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_ALLOWED_EXTENSIONS_N_FP", "csv,xml")

    with pytest.raises(RuntimeError, match=r"extensões não suportadas: \.xml"):
        policy_for("N-FP")


def test_accepts_valid_content_with_random_internal_name(tmp_path) -> None:
    result = _inspect(tmp_path, "customer-name.xlsx", _xlsx_bytes(), XLSX_MIME)

    assert result.accepted is True
    assert result.internal_name.endswith(".xlsx")
    assert len(result.internal_name.split(".", 1)[0]) == 48
    assert "customer-name" not in result.internal_name
    assert result.detected_media_type == XLSX_MIME


def test_retention_cleanup_only_removes_expired_quarantine(tmp_path) -> None:
    result = _inspect(tmp_path, "page.csv", b"<html></html>", "text/csv")
    assert result.quarantine_path is not None
    removed = purge_quarantined(tmp_path, [result.internal_name.split(".", 1)[0]])

    assert removed == [result.internal_name.split(".", 1)[0]]
    assert result.quarantine_path.exists() is False
