"""Offline checks of failure injection and ownership guards for the Docker drill."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from deploy import CommandRunner  # noqa: E402
from deploy_common import DeploymentError, private_json  # noqa: E402
from validate_deploy import Drill, FaultRunner  # noqa: E402


@pytest.mark.parametrize(
    "fault,step,tail",
    [
        ("build", "build candidate", ["build", "backend", "web"]),
        ("health", "backend readiness", ["up", "--wait", "backend"]),
        ("migration", "apply migrations", ["run", "--no-deps", "migrate"]),
        ("slow-migration", "apply migrations", ["run", "--no-deps", "migrate"]),
        (
            "smoke",
            "application smoke",
            [
                "exec",
                "python",
                "-",
                "--expected-api-origin",
                "http://api.internal.example",
            ],
        ),
    ],
)
def test_faults_execute_real_commands_without_editing_trusted_snapshots(
    tmp_path, monkeypatch, fault, step, tail
):
    trusted = tmp_path / "trusted.json"
    trusted.write_text("trusted-original")
    captured = {}

    def run(_self, args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return "safe-output"

    monkeypatch.setattr(CommandRunner, "run", run)
    runner = FaultRunner(tmp_path)
    runner.fault = fault
    runner.run(
        ["docker", "compose", "--file", str(trusted), *tail],
        step=step,
        input_text="trusted-smoke-code",
    )
    assert trusted.read_text() == "trusted-original"
    assert runner.fault is None
    assert captured["input_text"] == "trusted-smoke-code"
    if fault in {"build", "health"}:
        override = private_json(tmp_path / f"fault-{fault}.json")
        assert set(override["services"]) == {"backend"}
        assert captured["args"].count("--file") == 2
    elif fault in {"migration", "slow-migration"}:
        assert captured["args"][-3:-1] == ["python", "-c"]
        code = captured["args"][-1]
        assert (
            "SELECT 1/0" in code
            if fault == "migration"
            else "pg_advisory_lock(7347319119)" in code
        )
    else:
        assert captured["args"][-1] == "http://wrong.internal.example"


def test_cleanup_refuses_any_non_owned_project_before_calling_docker():
    drill = object.__new__(Drill)
    drill.environments = [SimpleNamespace(project="synergia")]
    drill.runner = SimpleNamespace(
        run=lambda *args, **kwargs: pytest.fail("foreign resource touched")
    )
    with pytest.raises(DeploymentError, match="cleanup project ownership"):
        drill.cleanup()


def test_cleanup_blocks_unexpected_container_identifiers():
    drill = object.__new__(Drill)
    drill.environments = [SimpleNamespace(project="synergia-check-123456abcdef")]
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return "unexpected-non-container-value"

    drill.runner = SimpleNamespace(run=run)
    with pytest.raises(DeploymentError, match="cleanup container identity"):
        drill.cleanup()
    assert len(calls) == 1
    assert "rm" not in calls[0]


def test_validation_cli_uses_only_the_python_standard_library():
    script = Path(__file__).resolve().parents[2] / "scripts/validate_deploy.py"
    result = subprocess.run(
        [sys.executable, "-S", str(script), "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "--previous-revision" in result.stdout
