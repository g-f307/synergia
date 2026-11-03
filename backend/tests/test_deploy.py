"""Offline deployment contract: no credentials, Docker or external services."""

from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("deploy", ROOT / "scripts/deploy.py")
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


def configuration(project="synergia-test"):
    environment = {
        "SYNERGIA_ENV": "homologation",
        "PGPASSWORD": "synthetic-database-password",
        "AUTH_JWT_SIGNING_KEY": "synthetic-signing-key-with-at-least-32-bytes",
        "RATE_LIMIT_KEY_SECRET": "synthetic-rate-limit-key-with-at-least-32-bytes",
        "AUTH_ALLOWED_ORIGINS": "http://web.internal.example",
        "SYNERGIA_API_ORIGIN": "http://api.internal.example",
        "AUTH_IDENTITY_PROVIDER": "local",
    }
    return {
        "services": {
            "postgres": {
                "environment": {"POSTGRES_PASSWORD": environment["PGPASSWORD"]}
            },
            "backend": {"environment": environment, "image": "synergia-backend:local"},
            "web": {"image": "synergia-web:local"},
            "migrate": {},
        },
        "volumes": {name: {"name": f"{project}_{name}"} for name in deploy.VOLUMES},
    }


class FakeRunner:
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.responses = {
            "source revision": "a" * 40,
            "source worktree": "",
            "Docker Compose availability": "5.5.1",
            "Docker daemon": '"synthetic-daemon"',
            "Compose configuration": json.dumps(configuration()),
            "installation inventory": "",
            "persistent volume inventory": "",
            "image inventory": "",
            "persistent mount identity": json.dumps(
                [
                    {
                        "Type": "volume",
                        "Destination": "/var/lib/synergia",
                        "Name": "synergia-test_synergia-application-data",
                    }
                ]
            ),
        }

    def run(self, args, *, step, timeout=60):
        self.calls.append((args, step))
        return self.responses[step]


@pytest.fixture
def subject(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    env = tmp_path / "homologation.env"
    env.write_text("synthetic external configuration\n")
    env.chmod(0o600)
    runner = FakeRunner(root)
    return deploy.Deployment(
        project="synergia-test",
        env_file=env,
        state_dir=tmp_path / "private-history",
        runner=runner,
    )


def test_diagnose_is_read_only_and_redacts_configuration(subject):
    before = set(subject.runner.root.parent.rglob("*"))
    report = subject.diagnose()
    assert report["environment"] == "homologation"
    assert report["revision"] == "a" * 40
    assert report["operation"] is None
    assert report["services"] == []
    assert not any(report["volumes_present"].values())
    assert not any(report["images_present"].values())
    assert before == set(subject.runner.root.parent.rglob("*"))
    commands = [args for args, _ in subject.runner.calls]
    assert all(
        not {"up", "run", "build", "exec", "create", "down"}.intersection(args)
        for args in commands
    )
    assert "synthetic-database-password" not in json.dumps(report)
    assert "AUTH_JWT_SIGNING_KEY" not in json.dumps(report)
    assert all("--project-name" in args for args in commands if "compose" in args)


@pytest.mark.parametrize(
    "inventory",
    [
        '[{"Service":"backend","State":"running"}]',
        '{"Service":"backend","State":"running"}\n',
    ],
)
def test_diagnose_reports_existing_services_without_echoing_metadata(
    subject, inventory
):
    parsed = json.loads(inventory)
    if isinstance(parsed, list):
        parsed[0]["ID"] = "a" * 64
    else:
        parsed["ID"] = "a" * 64
    subject.runner.responses["installation inventory"] = json.dumps(parsed)
    subject.runner.responses["persistent volume inventory"] = (
        "synergia-test_synergia-postgres\nsynergia-test_synergia-application-data\n"
    )
    subject.runner.responses["image inventory"] = json.dumps(
        {
            "Repository": "synergia-backend",
            "Tag": "local",
            "ID": "sha256:" + "a" * 64,
        }
    )
    result = subject.diagnose()
    assert result["services"] == [{"service": "backend", "running": True}]
    assert all(result["volumes_present"].values())
    assert result["images_present"] == {"backend": True, "web": False}


@pytest.mark.parametrize(
    "key,value,message",
    [
        ("source worktree", " M docker-compose.yml", "dirty"),
        ("source revision", "not-a-commit", "full Git commit"),
        ("Docker daemon", '""', "installation identity"),
        ("Compose configuration", "invalid", "invalid tool response"),
        ("Compose configuration", "[]", "unsupported service contract"),
        ("installation inventory", "{}", "unsupported response"),
        ("image inventory", '"unexpected"', "unsupported response"),
    ],
)
def test_precheck_blocks_invalid_source_or_tool_responses(subject, key, value, message):
    subject.runner.responses[key] = value
    with pytest.raises(deploy.DeploymentError, match=message):
        subject.diagnose()
    assert not subject.state_dir.exists()


@pytest.mark.parametrize(
    "name,value,message",
    [
        ("SYNERGIA_ENV", "", "SYNERGIA_ENV"),
        ("PGPASSWORD", "synergia-local-only", "PGPASSWORD"),
        ("AUTH_ALLOWED_ORIGINS", "http://*.internal.example", "AUTH_ALLOWED_ORIGINS"),
        ("AUTH_JWT_ALGORITHM", "RS256", "AUTH_JWT_ALGORITHM"),
        (
            "MIGRATION_BASELINE_THROUGH",
            "0033_example.sql",
            "separate controlled procedure",
        ),
    ],
)
def test_existing_deployment_rules_are_used_without_duplication(
    subject, name, value, message
):
    config = configuration()
    config["services"]["backend"]["environment"][name] = value
    subject.runner.responses["Compose configuration"] = json.dumps(config)
    with pytest.raises(deploy.DeploymentError, match=message):
        subject.precheck()


def test_database_and_volume_identity_fail_closed(subject):
    config = configuration()
    config["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"] = "different"
    subject.runner.responses["Compose configuration"] = json.dumps(config)
    with pytest.raises(deploy.DeploymentError, match="passwords must agree"):
        subject.precheck()
    config = configuration()
    config["volumes"]["synergia-postgres"]["name"] = "another-installation"
    subject.runner.responses["Compose configuration"] = json.dumps(config)
    with pytest.raises(deploy.DeploymentError, match="volume identity"):
        subject.precheck()


@pytest.mark.parametrize(
    "mounts",
    [
        [],
        [{"Type": "bind", "Destination": "/var/lib/synergia", "Name": "other"}],
        [{"Type": "volume", "Destination": "/var/lib/synergia", "Name": "other"}],
        {"unexpected": "response"},
    ],
)
def test_precheck_blocks_existing_container_with_different_storage(subject, mounts):
    subject.runner.responses["installation inventory"] = json.dumps(
        [
            {
                "ID": "a" * 64,
                "Service": "backend",
                "State": "running",
            }
        ]
    )
    subject.runner.responses["persistent mount identity"] = json.dumps(mounts)
    with pytest.raises(deploy.DeploymentError, match="unexpected persistent storage"):
        subject.precheck()


@pytest.mark.parametrize("project", ["", "UPPER", "../other", "-other", "a" * 64])
def test_project_must_be_explicit_and_safe(subject, project):
    with pytest.raises(deploy.DeploymentError, match="project"):
        deploy.Deployment(
            project=project,
            env_file=subject.env_file,
            state_dir=subject.state_dir,
            runner=subject.runner,
        )


def test_configuration_is_external_private_and_not_executed(subject):
    subject.env_file.chmod(0o644)
    with pytest.raises(deploy.DeploymentError, match="private file"):
        deploy.Deployment(
            project="valid",
            env_file=subject.env_file,
            state_dir=subject.state_dir,
            runner=subject.runner,
        )
    with pytest.raises(deploy.DeploymentError, match="outside Git"):
        deploy.external_path(subject.runner.root / "secret.env", subject.runner.root)
    with pytest.raises(deploy.DeploymentError, match="unavailable"):
        deploy.external_path(
            subject.runner.root.parent / "missing",
            subject.runner.root,
            configuration=True,
        )


def test_host_runner_removes_ambient_compose_and_secret_overrides(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "ambient-secret")
    monkeypatch.setenv("COMPOSE_FILE", "unexpected.yml")
    monkeypatch.setenv("SYNERGIA_ENV", "production")
    captured = {}

    def run(args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 1, "", "ambient-secret")

    monkeypatch.setattr(deploy.subprocess, "run", run)
    with pytest.raises(deploy.DeploymentError) as result:
        deploy.CommandRunner().run(["docker", "info"], step="Docker daemon")
    assert "ambient-secret" not in str(result.value)
    assert not {"POSTGRES_PASSWORD", "COMPOSE_FILE", "SYNERGIA_ENV"}.intersection(
        captured["env"]
    )
    assert captured["env"]["COMPOSE_DISABLE_ENV_FILE"] == "1"
    assert captured["env"]["GIT_OPTIONAL_LOCKS"] == "0"
    assert captured["capture_output"] is True


@pytest.mark.parametrize(
    "error,message",
    [
        (subprocess.TimeoutExpired(["docker", "ambient-secret"], 1), "timeout"),
        (FileNotFoundError("ambient-secret"), "executable unavailable"),
    ],
)
def test_command_errors_never_echo_arguments_or_raw_errors(monkeypatch, error, message):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(deploy.subprocess, "run", fail)
    with pytest.raises(deploy.DeploymentError, match=message) as result:
        deploy.CommandRunner().run(["docker"], step="tooling")
    assert "ambient-secret" not in str(result.value)


def test_host_cli_help_works_without_backend_dependencies():
    result = subprocess.run(
        [sys.executable, "-S", str(ROOT / "scripts/deploy.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "diagnose" in result.stdout


def store(tmp_path, *, identity="synthetic-daemon:project", name="history"):
    return deploy.OperationStore(tmp_path / name, identity=identity)


def test_journal_is_atomic_private_and_bound_to_installation(tmp_path):
    journal = store(tmp_path)
    with journal.operation("apply") as record:
        assert journal.read()["status"] == "running"
        assert record["stage"] == "precheck"
    assert journal.read()["status"] == "succeeded"
    assert stat.S_IMODE(journal.directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(journal.path.stat().st_mode) == 0o600
    assert not list(journal.directory.glob(".operation-*"))
    with pytest.raises(deploy.DeploymentError, match="journal invalid"):
        store(tmp_path, identity="another-daemon:project").read()


def test_concurrent_operations_are_blocked_even_with_different_state_dirs(tmp_path):
    first = store(tmp_path)
    second = store(tmp_path, name="other-history")
    with first.operation("apply"):
        with pytest.raises(deploy.DeploymentError, match="another deployment"):
            with second.operation("rollback"):
                pytest.fail("concurrent operation was allowed")
    with second.operation("apply"):
        pass


@pytest.mark.parametrize(
    "error", [RuntimeError("synthetic-secret"), KeyboardInterrupt()]
)
def test_uncertain_operations_block_retry_without_persisting_exception(tmp_path, error):
    journal = store(tmp_path)
    with pytest.raises(type(error)), journal.operation("apply") as record:
        record["stage"] = "migrate"
        raise error
    assert journal.read()["status"] == "uncertain"
    assert journal.read()["stage"] == "migrate"
    assert "synthetic-secret" not in journal.path.read_text()
    with pytest.raises(deploy.DeploymentError, match="unresolved"):
        with journal.operation("apply"):
            pytest.fail("uncertain operation retried")


def test_process_crash_leaves_running_journal_and_blocks_retry(tmp_path):
    journal = store(tmp_path)
    child = """
import os
import runpy
import sys
from pathlib import Path
module = runpy.run_path(sys.argv[1])
journal = module["OperationStore"](
    Path(sys.argv[2]), identity="synthetic-daemon:project"
)
with journal.operation("apply") as record:
    record["stage"] = "migrate"
    journal.write(record)
    os._exit(19)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            child,
            str(ROOT / "scripts/deploy.py"),
            str(journal.directory),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 19, result.stderr
    assert journal.read()["status"] == "running"
    assert journal.read()["stage"] == "migrate"
    with pytest.raises(deploy.DeploymentError, match="unresolved"):
        with journal.operation("apply"):
            pytest.fail("crashed operation retried")


def test_raw_validator_errors_are_not_echoed(subject, monkeypatch):
    def fail(_environment):
        raise ValueError("synthetic-secret is not a valid URL")

    monkeypatch.setattr(deploy, "validate_deployment_environment", fail)
    with pytest.raises(deploy.DeploymentError) as result:
        subject.precheck()
    assert "synthetic-secret" not in str(result.value)
    assert "environment profile" in str(result.value)


def test_corrupt_or_public_history_is_blocked(tmp_path):
    journal = store(tmp_path)
    journal.directory.mkdir(mode=0o755)
    with pytest.raises(deploy.DeploymentError, match="private"):
        journal.read()
    journal.directory.chmod(0o700)
    journal.path.write_text('{"secret":"do-not-echo"}')
    journal.path.chmod(0o600)
    with pytest.raises(deploy.DeploymentError, match="journal invalid") as result:
        journal.read()
    assert "do-not-echo" not in str(result.value)


def test_cli_reports_only_safe_errors(subject, monkeypatch, capsys):
    monkeypatch.setattr(deploy, "Deployment", lambda **kwargs: subject)
    subject.runner.responses["source worktree"] = "dirty-with-secret"
    assert (
        deploy.main(
            [
                "diagnose",
                "--project",
                "synergia-test",
                "--env-file",
                str(subject.env_file),
                "--state-dir",
                str(subject.state_dir),
            ]
        )
        == 1
    )
    result = capsys.readouterr()
    assert "dirty" in result.err
    assert "dirty-with-secret" not in result.err
