"""Testes fail-closed do verificador de ausência experimental em artefatos."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


def test_check_docker_image_is_fail_closed(monkeypatch):
    import check_experimental_absence_in_artifacts as checker

    # Must not contain || true anywhere
    target = ROOT / "scripts" / "check_experimental_absence_in_artifacts.py"
    source = target.read_text(encoding="utf-8")
    assert "|| true" not in source

    # Missing target path (stat fails -> exit != 0)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, "", "No such file"),
    )
    with pytest.raises(RuntimeError, match="ausente"):
        checker.check_docker_image("img:test", ["/opt/synergia/backend/app"])

    # Path exists, grep returns exit 2 (error) -> must fail, not pass!
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 2, "", "grep: error")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="Erro ao inspecionar"):
        checker.check_docker_image("img:test", ["/opt/synergia/backend/app"])

    # Path exists, grep returns exit 1 (no matches) -> pass!
    calls["n"] = 0

    def fake_run_clean(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 1, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run_clean)
    res = checker.check_docker_image("img:test", ["/opt/synergia/backend/app"])
    assert res["hits"] == []
