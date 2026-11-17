"""Testes do empacotador único de evidências da #192."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


def test_package_evidence_creates_manifest_and_rejects_secrets(tmp_path):
    from package_issue_192_evidence import package_evidence

    ev = tmp_path / "ev"
    (ev / "runs" / "ci-fake-1").mkdir(parents=True)
    report = ev / "runs" / "ci-fake-1" / "ci-fake-report.json"
    report.write_text("{}", encoding="utf-8")
    (ev / "migrations-rollback.json").write_text("{}", encoding="utf-8")

    (ev / "unlisted-extra.txt").write_text("ignored", encoding="utf-8")
    result = package_evidence(ev)
    assert result["file_count"] == 2
    with zipfile.ZipFile(result["zip_path"]) as zf:
        names = set(zf.namelist())
        assert "package-manifest.json" in names
        assert "migrations-rollback.json" in names
        assert "unlisted-extra.txt" not in names
        manifest = json.loads(zf.read("package-manifest.json"))
        assert manifest["file_count"] == 2

    out_zip = ev / "fail-atomic.zip"
    (ev / ".env").write_text("SECRET=1", encoding="utf-8")
    with pytest.raises(ValueError, match="proibido"):
        package_evidence(ev, output_zip=out_zip)
    assert not out_zip.exists()
