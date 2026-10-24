from __future__ import annotations

import json
import logging
import runpy
import socket
import sys
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = "SYNTHETIC-PRIVATE-OPERATION-143"


@pytest.fixture
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("CLI unit tests must not connect")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/unit")


@pytest.mark.parametrize(
    "arguments",
    [
        ["--apply"],
        ["--resolution", "accepted"],
        [
            "--apply",
            "--resolution",
            "not_accepted",
            "--evidence",
            "recipient_confirmation",
            "--request-id",
            str(uuid4()),
            "--actor-id",
            str(uuid4()),
            "--workers-stopped",
        ],
        ["--max-attempts", "11"],
    ],
)
def test_reconciliation_cli_rejects_unsafe_arguments_before_database(
    offline, monkeypatch, arguments
):
    module = runpy.run_path(str(ROOT / "scripts/reconcile_smtp_delivery.py"))
    monkeypatch.setattr(sys, "argv", ["reconcile", str(uuid4()), *arguments])
    with pytest.raises(SystemExit) as exit_info:
        module["main"]()
    assert exit_info.value.code == 2


@pytest.mark.parametrize("error,code", [(ValueError, 2), (RuntimeError, 1)])
def test_reconciliation_cli_does_not_expose_database_errors(
    offline, monkeypatch, capsys, error, code
):
    from app.email_reconciliation import EmailReconciliationRepository

    def fail(*args):
        raise error(PRIVATE)

    monkeypatch.setattr(EmailReconciliationRepository, "inspect", fail)
    module = runpy.run_path(str(ROOT / "scripts/reconcile_smtp_delivery.py"))
    monkeypatch.setattr(sys, "argv", ["reconcile", str(uuid4())])
    assert module["main"]() == code
    captured = capsys.readouterr()
    assert PRIVATE not in captured.out + captured.err
    assert json.loads(captured.out)["error_code"].startswith("smtp_reconciliation_")


@pytest.mark.parametrize("error,code", [(ValueError, 2), (RuntimeError, 1)])
def test_worker_cli_does_not_log_configuration_or_database_details(
    offline, monkeypatch, caplog, error, code
):
    module = runpy.run_path(str(ROOT / "scripts/process_email_notifications.py"))

    def fail():
        raise error(PRIVATE)

    function = module["main"]
    monkeypatch.setitem(function.__globals__, "_run", fail)
    monkeypatch.setitem(function.__globals__, "configure_logging", lambda: None)
    with caplog.at_level(logging.ERROR):
        assert function() == code
    assert PRIVATE not in caplog.text
    assert "email_worker.failed" in caplog.text
