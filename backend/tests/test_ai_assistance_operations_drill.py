"""Safety gates of the optional real-Graylog exercise; no external service."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts import validate_ai_assistance_operations as drill  # noqa: E402
from scripts.graylog_lab import LabError  # noqa: E402

pytestmark = pytest.mark.security


def test_drill_refuses_checkout_workspace_without_using_database(monkeypatch, capsys):
    monkeypatch.setattr(drill.logging, "disable", lambda *_: None)
    assert drill.main(["--workspace", str(ROOT / "private")]) == 1
    assert "ai191_drill_failed" in capsys.readouterr().out


def test_drill_checks_owned_lab_before_credentials_or_database(monkeypatch):
    import psycopg

    class ForeignLab:
        def configure(self):
            raise LabError("resource_belongs_to_another_lab_workspace")

        def access(self):
            pytest.fail("credentials must not be read")

    monkeypatch.setattr(
        psycopg, "connect", lambda *_a, **_k: pytest.fail("database used")
    )
    with pytest.raises(LabError, match="another_lab_workspace"):
        drill.run(ForeignLab())


def test_drill_cli_does_not_print_private_exception(tmp_path, monkeypatch, capsys):
    def fail(*_):
        raise RuntimeError("private-connection-canary-191")

    monkeypatch.setattr(drill, "run", fail)
    monkeypatch.setattr(drill.logging, "disable", lambda *_: None)
    assert drill.main(["--workspace", str(tmp_path)]) == 1
    output = capsys.readouterr()
    assert "ai191_drill_failed" in output.out
    assert "private-connection-canary-191" not in output.out + output.err
