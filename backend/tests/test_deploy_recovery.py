"""Recovery must never infer a safe schema downgrade or rerun uncertain SQL."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from deploy_common import DeploymentError, compose_values, private_json  # noqa: E402
from deploy_recovery import RecoveryWorkflow, runtime_service  # noqa: E402
from test_deploy_flow import (  # noqa: E402
    COMMIT,
    IMAGE,
    PREVIOUS,
    FlowRunner,
)
from test_deploy_flow import flow_factory as make_flow


class RecoveryRunner(FlowRunner):
    def __init__(self, root):
        super().__init__(root, existing=True)
        self.current_images = dict(PREVIOUS)
        self.current_env = {
            name: dict(self.config["services"][name]["environment"])
            for name in ("postgres", "backend", "web")
        }
        self.locked = False
        self.missing = set()
        self.migration_state = None

    def run(self, args, *, step, timeout=60, input_text=None):
        if self.failure == step:
            return super().run(args, step=step, timeout=timeout, input_text=input_text)
        if step == "capture current runtime":
            self.calls.append((args, step))
            name = next(
                name for name in self.services if self.container(name)["ID"] == args[-1]
            )
            return json.dumps(
                {
                    "image": self.current_images[name],
                    "environment": [
                        f"{key}={value}"
                        for key, value in self.current_env[name].items()
                    ],
                    "command": [],
                    "entrypoint": [],
                    "ports": {},
                    "labels": {},
                }
            )
        if step == "resolve immutable image" and args[-1].startswith("sha256:"):
            self.calls.append((args, step))
            if args[-1] in self.missing:
                raise DeploymentError("retained image missing")
            return json.dumps({"id": args[-1], "labels": {}})
        if step == "inspect migration lock":
            self.calls.append((args, step))
            return "true" if self.locked else "false"
        if step == "find interrupted migration":
            self.calls.append((args, step))
            return "d" * 64 if self.migration_state else ""
        if step == "inspect interrupted migration":
            self.calls.append((args, step))
            return json.dumps(
                self.migration_state | {"service": "migrate", "image": IMAGE["backend"]}
            )
        if step in {"backend readiness", "web readiness"}:
            name = args[-1]
            config = compose_values(private_json(Path(args[args.index("--file") + 1])))
            self.current_images[name] = config["services"][name]["image"]
            self.current_env[name] = config["services"][name]["environment"]
        return super().run(args, step=step, timeout=timeout, input_text=input_text)


@pytest.fixture
def recovery(tmp_path):
    flow = make_flow.__wrapped__(tmp_path)(existing=True)
    runner = RecoveryRunner(flow.runner.root)
    flow.deployment.runner = runner
    return RecoveryWorkflow(flow.deployment, flow.store_type)


def unresolved(recovery):
    recovery.runner.failure = "backend readiness"
    with pytest.raises(DeploymentError):
        recovery.apply(COMMIT)
    recovery.runner.failure = None
    return private_json(recovery.deployment.state_dir / "operation.json")["id"]


def test_rollback_restores_actual_unmanaged_baseline_without_sql_or_build(recovery):
    deployed = recovery.apply(COMMIT)
    before = len(recovery.runner.calls)
    result = recovery.rollback()
    assert result["images"] == PREVIOUS
    assert result["revision"] is None  # Legacy images never supplied a commit label.
    assert result["previous"] == deployed["id"]
    assert recovery.read_active() == result
    assert recovery.runner.current_images == PREVIOUS
    assert recovery.runner.migration_runs == 1
    recent = recovery.runner.calls[before:]
    assert not {
        "build candidate",
        "apply migrations",
        "PostgreSQL readiness",
    }.intersection(step for _, step in recent)
    assert all("--no-deps" in args for args, _ in recent if "up" in args)
    assert all(not {"down", "rm", "--volumes"}.intersection(args) for args, _ in recent)


@pytest.mark.parametrize("invalid", ["schema", "image", "configuration", "lock"])
def test_incompatible_or_missing_recovery_artifacts_block_before_shutdown(
    recovery, invalid
):
    deployed = recovery.apply(COMMIT)
    before = len(recovery.runner.calls)
    if invalid == "schema":
        recovery.runner.expected["0002_new_schema.sql"] = "b" * 64
    elif invalid == "image":
        recovery.runner.missing.add(PREVIOUS["backend"])
    elif invalid == "configuration":
        path = recovery.deployment.state_dir / deployed["previous"] / "compose.json"
        path.write_text(path.read_text() + " ")
    else:
        recovery.runner.locked = True
    with pytest.raises(DeploymentError):
        recovery.rollback()
    assert "stop application writers" not in [
        step for _, step in recovery.runner.calls[before:]
    ]
    assert recovery.read_active() == deployed


def test_interrupted_rollback_stays_blocked_until_explicit_reconciliation(recovery):
    deployed = recovery.apply(COMMIT)
    recovery.runner.failure = "web readiness"
    with pytest.raises(DeploymentError):
        recovery.rollback()
    record = private_json(recovery.deployment.state_dir / "operation.json")
    assert record["status"] == "uncertain"
    assert recovery.read_active() == deployed
    recovery.runner.failure = None
    with pytest.raises(DeploymentError, match="unresolved"):
        recovery.rollback()
    result = recovery.reconcile(record["id"], resolution="resume")
    assert result["verified"] is True
    assert recovery.read_active()["images"] == PREVIOUS
    assert recovery.runner.migration_runs == 1


def test_inspection_of_interrupted_operation_is_read_only(recovery):
    identifier = unresolved(recovery)
    before = {
        path: path.read_bytes()
        for path in recovery.deployment.state_dir.rglob("*")
        if path.is_file()
    }
    count = len(recovery.runner.calls)
    report = recovery.reconcile(identifier)
    assert report["migration"]["state"] == "not_found"
    assert report["candidate_ledger_matches"] is True
    assert before == {
        path: path.read_bytes()
        for path in recovery.deployment.state_dir.rglob("*")
        if path.is_file()
    }
    assert not {
        "application smoke",
        "stop application writers",
        "apply migrations",
    }.intersection(step for _, step in recovery.runner.calls[count:])


@pytest.mark.parametrize("resolution", ["resume", "rollback"])
def test_explicit_reconciliation_never_repeats_migrations(recovery, resolution):
    identifier = unresolved(recovery)
    migrations = recovery.runner.migration_runs
    result = recovery.reconcile(identifier, resolution=resolution)
    assert result["verified"] is True
    assert recovery.runner.migration_runs == migrations
    journal = private_json(recovery.deployment.state_dir / "operation.json")
    assert journal["status"] == (
        "succeeded" if resolution == "resume" else "reconciled"
    )
    expected = IMAGE if resolution == "resume" else PREVIOUS
    assert recovery.read_active()["images"] == expected
    logs = list((recovery.deployment.state_dir / "reconciliations").glob("*.json"))
    assert len(logs) == 1
    assert private_json(logs[0])["before"]["status"] == "uncertain"


def test_resume_requires_exact_candidate_ledger(recovery):
    identifier = unresolved(recovery)
    recovery.runner.expected["0002_other.sql"] = "b" * 64
    with pytest.raises(DeploymentError, match="migration history differs"):
        recovery.reconcile(identifier, resolution="resume")
    assert (
        private_json(recovery.deployment.state_dir / "operation.json")["status"]
        == "uncertain"
    )


def test_live_migration_lock_blocks_reconciliation_without_clearing_journal(recovery):
    identifier = unresolved(recovery)
    recovery.runner.locked = True
    assert recovery.reconcile(identifier)["migration_lock_held"] is True
    with pytest.raises(DeploymentError, match="reconciliation blocked"):
        recovery.reconcile(identifier, resolution="resume")
    assert (
        private_json(recovery.deployment.state_dir / "operation.json")["status"]
        == "uncertain"
    )


@pytest.mark.parametrize(
    "status,exit_code,expected",
    [
        ("running", 0, "running"),
        ("paused", 0, "running"),
        ("exited", 0, "completed"),
        ("exited", 1, "failed"),
        ("created", 0, "unknown"),
    ],
)
def test_migration_process_outcomes_are_distinguished(
    recovery, status, exit_code, expected
):
    identifier = unresolved(recovery)
    recovery.runner.migration_state = {"status": status, "exit_code": exit_code}
    assert recovery.reconcile(identifier)["migration"]["state"] == expected


def test_wrong_operation_cannot_unlock_an_unresolved_deployment(recovery):
    unresolved(recovery)
    with pytest.raises(DeploymentError, match="does not match"):
        recovery.reconcile("11111111-1111-4111-8111-111111111111", resolution="resume")


def test_failed_reconciliation_is_audited_and_remains_uncertain(recovery):
    identifier = unresolved(recovery)
    recovery.runner.failure = "application smoke"
    with pytest.raises(DeploymentError):
        recovery.reconcile(identifier, resolution="resume")
    assert (
        private_json(recovery.deployment.state_dir / "operation.json")["status"]
        == "uncertain"
    )
    log = next((recovery.deployment.state_dir / "reconciliations").glob("*.json"))
    assert private_json(log)["status"] == "uncertain"
    recovery.runner.failure = None
    assert recovery.reconcile(identifier, resolution="rollback")["verified"] is True


@pytest.mark.parametrize("state", ["running", "created"])
def test_live_or_unknown_migration_process_blocks_explicit_resume(recovery, state):
    identifier = unresolved(recovery)
    recovery.runner.migration_state = {"status": state, "exit_code": 0}
    with pytest.raises(DeploymentError, match="reconciliation blocked"):
        recovery.reconcile(identifier, resolution="resume")
    assert (
        private_json(recovery.deployment.state_dir / "operation.json")["status"]
        == "uncertain"
    )


def test_reconciliation_does_not_override_a_live_deployment_lock(recovery):
    identifier = unresolved(recovery)
    report = recovery.inventory()
    store = recovery.store_type(
        recovery.deployment.state_dir,
        identity=f"{report['daemon_id']}:{report['project']}",
    )
    with store.lock(), pytest.raises(DeploymentError, match="another deployment"):
        recovery.reconcile(identifier, resolution="resume")


def test_unmanaged_snapshot_preserves_runtime_settings_and_dual_stack_ports():
    config = {"volumes": {}}
    snapshot = runtime_service(
        {"depends_on": {"migrate": {}}, "build": {}, "profiles": ["email"]},
        {
            "image": PREVIOUS["backend"],
            "environment": {"KEY": "synthetic-$literal"},
            "command": ["original-command"],
            "entrypoint": ["original-entrypoint"],
            "user": "10001:10001",
            "ports": {
                "8000/tcp": [
                    {"HostPort": "18000", "HostIp": "0.0.0.0"},
                    {"HostPort": "18000", "HostIp": "::"},
                ]
            },
            "mounts": [
                {
                    "Type": "volume",
                    "Name": "retained-volume",
                    "Destination": "/data",
                    "RW": False,
                }
            ],
            "healthcheck": {
                "Test": ["CMD", "original-probe"],
                "Interval": 5_000_000_000,
            },
            "restart": {"Name": "on-failure", "MaximumRetryCount": 3},
        },
        config,
    )
    assert snapshot["ports"] == [
        {"target": 8000, "published": "18000", "protocol": "tcp"}
    ]
    assert snapshot["volumes"][0]["read_only"] is True
    assert config["volumes"]["retained-volume"]["external"] is True
    assert snapshot["command"] == ["original-command"]
    assert snapshot["entrypoint"] == ["original-entrypoint"]
    assert snapshot["healthcheck"]["test"] == ["CMD", "original-probe"]
    assert snapshot["restart"] == "on-failure:3"
    assert not {"depends_on", "build", "profiles"}.intersection(snapshot)


def test_corrupted_candidate_blocks_inspection_without_echoing_private_data(recovery):
    identifier = unresolved(recovery)
    path = recovery.deployment.state_dir / identifier / "candidate.json"
    path.write_text('{"private":"synthetic-secret"}')
    with pytest.raises(DeploymentError) as failure:
        recovery.reconcile(identifier)
    assert "synthetic-secret" not in str(failure.value)


def test_empty_host_binding_preserves_all_interfaces_without_invalid_host_ip():
    snapshot = runtime_service(
        {},
        {
            "image": PREVIOUS["backend"],
            "environment": {},
            "command": [],
            "entrypoint": [],
            "ports": {"8000/tcp": [{"HostPort": "18000", "HostIp": ""}]},
        },
        {},
    )
    assert snapshot["ports"] == [
        {"target": 8000, "published": "18000", "protocol": "tcp"}
    ]


def test_compose_rejecting_a_recovery_artifact_blocks_before_maintenance(recovery):
    deployed = recovery.apply(COMMIT)
    count = len(recovery.runner.calls)
    recovery.runner.failure = "recovery Compose validation"
    with pytest.raises(DeploymentError):
        recovery.rollback()
    assert recovery.read_active() == deployed
    assert "stop application writers" not in [
        step for _, step in recovery.runner.calls[count:]
    ]
