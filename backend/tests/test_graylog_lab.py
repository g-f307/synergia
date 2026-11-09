"""Laboratory ownership/privacy gates. No container or corporate network required."""

from __future__ import annotations

import json
import os
import stat
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.graylog_lab import LABEL, PREFIX, LabError, Laboratory, main  # noqa: E402


def test_lab_workspace_cannot_be_inside_checkout():
    with pytest.raises(LabError, match="workspace_must_be_outside_git"):
        Laboratory(ROOT / "private-lab", "docker")


def test_credentials_are_private_preserved_and_not_in_returned_metadata(tmp_path):
    # Certificate creation is independently exercised in the real laboratory;
    # this unit case isolates storage/credential lifecycle from OpenSSL.
    (tmp_path / "ca.pem").write_text("unused-public-certificate")
    lab = Laboratory(tmp_path, "docker")
    result = lab.initialize()
    first = lab.access()
    lab.initialize()
    assert first == lab.access()
    assert first["password"] not in json.dumps(result)
    assert first["input_key"] not in json.dumps(result)
    assert first["postgres_password"] not in json.dumps(result)
    if os.name != "nt":
        for name in ("access.json", "graylog.env", "postgres.env"):
            assert stat.S_IMODE((tmp_path / name).stat().st_mode) == 0o600
        assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700


@pytest.mark.parametrize(
    "details",
    [
        {"Config": {"Labels": {LABEL: "another-project"}}},
        {"Labels": {}},
        {"labels": {LABEL: "another-project"}},
    ],
)
def test_foreign_resources_are_not_started_stopped_or_reused(
    tmp_path, monkeypatch, details
):
    lab = Laboratory(tmp_path, "docker")
    monkeypatch.setattr(lab, "inspect", lambda *_: details)
    monkeypatch.setattr(
        lab, "command", lambda *_a, **_k: pytest.fail("mutation attempted")
    )
    with pytest.raises(LabError, match="resource_not_owned_by_lab"):
        lab.stop()
    with pytest.raises(LabError, match="resource_not_owned_by_lab"):
        lab.ensure_resource("network", PREFIX)


def test_api_does_not_send_credentials_without_owned_running_server(
    tmp_path, monkeypatch
):
    lab = Laboratory(tmp_path, "docker")
    monkeypatch.setattr(lab, "owned", lambda *_: {"State": {"Running": False}})
    monkeypatch.setattr(lab, "access", lambda: pytest.fail("credentials read"))
    with pytest.raises(LabError, match="owned_graylog_container_not_running"):
        lab.api("POST", "system/inputs", {})


def test_cli_failure_never_prints_private_exception_data(tmp_path, monkeypatch, capsys):
    def fail(_self):
        raise RuntimeError("private-lab-canary-value")

    monkeypatch.setattr(Laboratory, "initialize", fail)
    monkeypatch.setattr("scripts.graylog_lab.logging.disable", lambda *_: None)
    assert main(["--workspace", str(tmp_path), "init"]) == 1
    output = capsys.readouterr()
    assert "private-lab-canary-value" not in output.out + output.err
    assert json.loads(output.out)["error_code"] == "local_lab_operation_failed"


def test_configure_reports_stopped_dependency_without_waiting_for_graylog(
    tmp_path, monkeypatch
):
    lab = Laboratory(tmp_path, "podman")
    monkeypatch.setattr(
        lab,
        "owned",
        lambda _kind, name: {"State": {"Running": not name.endswith("-opensearch")}},
    )
    monkeypatch.setattr(lab, "api", lambda *_: pytest.fail("API contacted"))
    with pytest.raises(LabError, match="opensearch_not_running"):
        lab.configure()


def test_input_stop_waits_for_graylog_state_instead_of_published_port(
    tmp_path, monkeypatch
):
    lab = Laboratory(tmp_path, "podman")
    (tmp_path / "input.json").write_text(json.dumps({"id": "synthetic-input"}))
    states = iter(["RUNNING", "STOPPED"])
    calls = []

    def api(method, path):
        calls.append((method, path))
        return {"state": next(states)}

    monkeypatch.setattr(lab, "api", api)
    monkeypatch.setattr("scripts.graylog_lab.time.sleep", lambda *_: None)
    lab.wait_input(False)
    assert calls == [("GET", "system/inputstates/synthetic-input")] * 2


@pytest.mark.parametrize("configuration_exists", [True, False])
def test_missing_input_state_only_means_stopped_if_configuration_exists(
    tmp_path, monkeypatch, configuration_exists
):
    lab = Laboratory(tmp_path, "podman")
    (tmp_path / "input.json").write_text(json.dumps({"id": "synthetic-input"}))

    def api(_method, path):
        if "inputstates/" in path or not configuration_exists:
            raise urllib.error.HTTPError("http://localhost/", 404, "absent", {}, None)
        return {"id": "synthetic-input"}

    monkeypatch.setattr(lab, "api", api)
    if configuration_exists:
        lab.wait_input(False)
    else:
        with pytest.raises(urllib.error.HTTPError):
            lab.wait_input(False)
