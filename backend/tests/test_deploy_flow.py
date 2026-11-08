"""Exercise ordering, publication gates and preservation without Docker/network."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from deploy_common import DeploymentError, compose_literals, private_json  # noqa: E402
from deploy_flow import ApplyWorkflow  # noqa: E402
from test_deploy import FakeRunner, configuration, deploy  # noqa: E402

COMMIT = "a" * 40
IMAGE = {
    "backend": "sha256:" + "1" * 64,
    "web": "sha256:" + "2" * 64,
    "postgres": "sha256:" + "3" * 64,
}
PREVIOUS = {
    "backend": "sha256:" + "4" * 64,
    "web": "sha256:" + "5" * 64,
    "postgres": IMAGE["postgres"],
}


class FlowRunner(FakeRunner):
    def __init__(self, root, existing=False):
        super().__init__(root)
        self.existing = existing
        self.services = {}
        self.has_volumes = existing
        self.applied = existing
        self.upgraded = False
        self.failure = None
        self.migration_runs = 0
        self.expected = {"0001_synthetic.sql": hashlib.sha256(b"SELECT 1;").hexdigest()}
        self.config = configuration()
        self.config["services"]["postgres"]["image"] = "postgres:16-alpine"
        pg = self.config["services"]["postgres"]["environment"]
        pg.update({"POSTGRES_USER": "synergia", "POSTGRES_DB": "synergia"})
        for name in ("config-check", "migrate", "email-worker"):
            self.config["services"][name] = {
                "environment": copy.deepcopy(
                    self.config["services"]["backend"]["environment"]
                ),
                "image": "synergia-backend:local",
            }
        for name in ("backend", "web"):
            self.config["services"][name]["build"] = {"context": str(root)}
        self.config["services"]["web"]["environment"] = {
            "SYNERGIA_API_ORIGIN": "http://api.internal.example",
        }
        if existing:
            self.services = {name: "running" for name in ("postgres", "backend", "web")}

    def container(self, name):
        return {
            "ID": (str(list(IMAGE).index(name) + 1) if name in IMAGE else "9") * 64,
            "Service": name,
            "State": self.services[name],
            "OneOff": "False",
        }

    def run(self, args, *, step, timeout=60, input_text=None):
        self.calls.append((args, step))
        if self.failure == step:
            raise DeploymentError(f"{step}: synthetic failure")
        if step == "Compose configuration":
            return json.dumps(compose_literals(self.config))
        if step == "installation inventory":
            return "\n".join(json.dumps(self.container(name)) for name in self.services)
        if step == "persistent volume inventory":
            return (
                "\n".join(f"synergia-test_{key}" for key in deploy.VOLUMES)
                if self.has_volumes
                else ""
            )
        if step == "persistent mount identity":
            name = next(
                name for name in self.services if self.container(name)["ID"] == args[-1]
            )
            key = (
                "synergia-postgres"
                if name == "postgres"
                else "synergia-application-data"
            )
            return json.dumps(
                [
                    {
                        "Type": "volume",
                        "Destination": "/var/lib/postgresql/data"
                        if name == "postgres"
                        else "/var/lib/synergia",
                        "Name": f"synergia-test_{key}",
                    }
                ]
            )
        if step == "capture current runtime":
            name = next(
                name for name in self.services if self.container(name)["ID"] == args[-1]
            )
            env = self.config["services"][name]["environment"]
            return json.dumps(
                {
                    "image": IMAGE[name]
                    if self.upgraded or name == "postgres"
                    else PREVIOUS[name],
                    "environment": [f"{key}={value}" for key, value in env.items()],
                    "command": [],
                    "entrypoint": [],
                    "ports": {},
                    "labels": {},
                }
            )
        if step == "resolve immutable image":
            name = (
                "web"
                if "web" in args[-1]
                else "postgres"
                if "postgres" in args[-1]
                else "backend"
            )
            return json.dumps(
                {
                    "id": IMAGE[name],
                    "labels": {"org.opencontainers.image.revision": COMMIT},
                }
            )
        if step == "PostgreSQL readiness":
            self.services["postgres"] = "running"
            self.has_volumes = True
        elif step == "stop application writers":
            for name in ("backend", "web"):
                self.services[name] = "exited"
        elif step == "inspect migration ledger":
            return "true" if self.applied else "false"
        elif step == "read migration ledger":
            return json.dumps(self.expected)
        elif step == "apply migrations":
            self.migration_runs += 1
            self.applied = True
        elif step in {"backend readiness", "web readiness"}:
            self.services[args[-1]] = "running"
            self.upgraded = True
        elif step == "chosen revision":
            return COMMIT
        elif step in self.responses:
            return self.responses[step]
        return ""


@pytest.fixture
def flow_factory(tmp_path):
    def make(existing=False):
        root = tmp_path / "source"
        root.mkdir(exist_ok=True)
        migrations = root / "database/migrations"
        migrations.mkdir(parents=True, exist_ok=True)
        (migrations / "0001_synthetic.sql").write_bytes(b"SELECT 1;")
        scripts = root / "scripts"
        scripts.mkdir(exist_ok=True)
        (scripts / "smoke_containers.py").write_text("print('synthetic smoke')\n")
        env = tmp_path / "homologation.env"
        env.write_text("SYNERGIA_ENV=homologation\n")
        env.chmod(0o600)
        runner = FlowRunner(root, existing)
        deployment = deploy.Deployment(
            project="synergia-test",
            env_file=env,
            state_dir=tmp_path / "history",
            runner=runner,
        )
        return ApplyWorkflow(deployment, deploy.OperationStore)

    return make


def steps(flow):
    return [step for _, step in flow.runner.calls]


def test_initial_installation_promotes_only_after_verified_migrations_and_smoke(
    flow_factory,
):
    flow = flow_factory()
    result = flow.apply(COMMIT, initialize=True)
    assert result["revision"] == COMMIT
    assert result["images"] == IMAGE
    assert flow.runner.migration_runs == 1
    assert flow.read_active() == result
    order = steps(flow)
    assert order.index("build candidate") < order.index("PostgreSQL readiness")
    assert order.index("apply migrations") < order.index("backend readiness")
    assert order.index("backend readiness") < order.index("application smoke")
    assert flow.verify_active() == {"revision": COMMIT, "verified": True}
    assert flow.runner.migration_runs == 1


def test_update_preserves_previous_images_and_quiesces_before_migrations(flow_factory):
    flow = flow_factory(existing=True)
    manifest = flow.apply(COMMIT)
    order = steps(flow)
    assert order.index("retain previous image") < order.index("build candidate")
    assert order.index("build candidate") < order.index("stop application writers")
    assert order.index("stop application writers") < order.index("apply migrations")
    previous = private_json(flow.release_dir / "before-runtime.json")
    assert previous["backend"]["image"] == PREVIOUS["backend"]
    assert previous["web"]["image"] == PREVIOUS["web"]
    assert flow.read_active()["id"] == manifest["id"]
    for args, _ in flow.runner.calls:
        assert not {"down", "rm", "--volumes", "--renew-anon-volumes"}.intersection(
            args
        )
        if "up" in args:
            assert {"--no-deps", "--no-build", "--pull"}.issubset(args)
        if "migrate" in args and "run" in args:
            assert "--no-deps" in args
        assert "process_email_notifications.py" not in args


@pytest.mark.parametrize(
    "stage",
    [
        "build candidate",
        "candidate configuration",
        "PostgreSQL readiness",
        "stop application writers",
        "apply migrations",
        "backend readiness",
        "web readiness",
        "application smoke",
        "web smoke",
    ],
)
def test_failures_stop_flow_and_never_promote_candidate(flow_factory, stage):
    flow = flow_factory(existing=True)
    flow.runner.failure = stage
    with pytest.raises(DeploymentError, match="synthetic failure"):
        flow.apply(COMMIT)
    assert flow.read_active() is None
    journal = private_json(flow.deployment.state_dir / "operation.json")
    assert journal["status"] == (
        "failed"
        if stage
        in {
            "build candidate",
            "candidate configuration",
            "PostgreSQL readiness",
        }
        else "uncertain"
    )
    if stage in {"build candidate", "candidate configuration", "PostgreSQL readiness"}:
        assert "stop application writers" not in steps(flow)
    if stage == "apply migrations":
        assert "backend readiness" not in steps(flow)


@pytest.mark.parametrize("existing,initialize", [(False, False), (True, True)])
def test_empty_installation_requires_explicit_confirmation(
    flow_factory, existing, initialize
):
    flow = flow_factory(existing)
    with pytest.raises(DeploymentError, match="--initialize"):
        flow.apply(COMMIT, initialize=initialize)
    assert "build candidate" not in steps(flow)


@pytest.mark.parametrize(
    "service", ["email-worker", "graylog-worker", "migrate", "config-check"]
)
def test_active_operations_block_before_any_build_or_shutdown(flow_factory, service):
    flow = flow_factory(existing=True)
    flow.runner.services[service] = "running"
    with pytest.raises(DeploymentError, match="operation is active"):
        flow.apply(COMMIT)
    assert "build candidate" not in steps(flow)
    assert "stop application writers" not in steps(flow)


def test_graylog_worker_uses_the_confirmed_immutable_backend_image(flow_factory):
    flow = flow_factory()
    flow.runner.config["services"]["graylog-worker"] = copy.deepcopy(
        flow.runner.config["services"]["email-worker"]
    )
    flow.runner.config["services"]["graylog-worker"]["profiles"] = ["graylog"]
    flow.apply(COMMIT, initialize=True)
    saved = private_json(flow.compose_file)
    assert saved["services"]["graylog-worker"]["image"] == IMAGE["backend"]
    assert "graylog-worker" not in flow.runner.services


@pytest.mark.parametrize(
    "failure", ["apply migrations", "backend readiness", "application smoke"]
)
def test_failed_update_keeps_last_confirmed_release(flow_factory, failure):
    flow = flow_factory()
    confirmed = flow.apply(COMMIT, initialize=True)
    flow.runner.failure = failure
    with pytest.raises(DeploymentError):
        flow.apply(COMMIT)
    assert flow.read_active() == confirmed


def test_repeating_update_keeps_migration_inventory(flow_factory):
    flow = flow_factory()
    first = flow.apply(COMMIT, initialize=True)
    second = flow.apply(COMMIT)
    assert first["migrations"] == second["migrations"]
    assert second["previous"] == first["id"]
    assert flow.runner.migration_runs == 2  # Runner is idempotent, ledger is unchanged.


@pytest.mark.parametrize("change", ["source", "configuration"])
def test_build_time_source_or_configuration_changes_block_before_maintenance(
    flow_factory, change
):
    flow = flow_factory(existing=True)
    original = flow.runner.run

    def run(args, *, step, timeout=60, input_text=None):
        result = original(args, step=step, timeout=timeout, input_text=input_text)
        if step == "build candidate":
            if change == "source":
                flow.runner.responses["source revision"] = "b" * 40
            else:
                flow.runner.config["services"]["web"]["environment"][
                    "SYNERGIA_API_ORIGIN"
                ] = "http://different.internal.example"
        return result

    flow.runner.run = run
    with pytest.raises(DeploymentError, match="changed during build"):
        flow.apply(COMMIT)
    assert "stop application writers" not in steps(flow)


def test_migration_ledger_mismatch_blocks_startup(flow_factory):
    flow = flow_factory()
    original = flow.runner.run

    def run(args, *, step, timeout=60, input_text=None):
        if step == "read migration ledger":
            return "{}"
        return original(args, step=step, timeout=timeout, input_text=input_text)

    flow.runner.run = run
    with pytest.raises(DeploymentError, match="ledger does not match"):
        flow.apply(COMMIT, initialize=True)
    assert "backend readiness" not in steps(flow)
    assert flow.read_active() is None


def test_explicit_revision_must_match_checked_out_source(flow_factory):
    flow = flow_factory()
    flow.runner.responses["source revision"] = "b" * 40
    with pytest.raises(DeploymentError, match="checkout must match"):
        flow.apply(COMMIT, initialize=True)
    assert not flow.deployment.state_dir.exists()


def test_active_configuration_tampering_is_blocked(flow_factory):
    flow = flow_factory()
    flow.apply(COMMIT, initialize=True)
    flow.compose_file.write_text(flow.compose_file.read_text() + " ")
    with pytest.raises(DeploymentError, match="configuration changed"):
        flow.verify_active()


def test_immutable_image_revision_is_checked(flow_factory):
    flow = flow_factory()
    original = flow.runner.run

    def run(args, *, step, timeout=60, input_text=None):
        if step == "resolve immutable image":
            return json.dumps({"id": IMAGE["backend"], "labels": {}})
        return original(args, step=step, timeout=timeout, input_text=input_text)

    flow.runner.run = run
    with pytest.raises(DeploymentError, match="source revision does not match"):
        flow.apply(COMMIT, initialize=True)
    assert "PostgreSQL readiness" not in steps(flow)


def test_frozen_config_preserves_dollars_in_secrets_without_public_exposure(
    flow_factory,
):
    flow = flow_factory()
    password = "synthetic-$literal:${not_an_environment_variable}"
    for name in ("backend", "migrate", "config-check"):
        flow.runner.config["services"][name]["environment"]["PGPASSWORD"] = password
    flow.runner.config["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"] = (
        password
    )
    manifest = flow.apply(COMMIT, initialize=True)
    assert password not in json.dumps(manifest)
    saved = private_json(flow.compose_file)
    assert saved["services"]["postgres"]["environment"][
        "POSTGRES_PASSWORD"
    ] == password.replace("$", "$$")
    assert compose_literals({"value": "$variable"}) == {"value": "$$variable"}


def test_unmanaged_stopped_postgres_is_ready_before_capturing_baseline(flow_factory):
    flow = flow_factory(existing=True)
    flow.runner.services["postgres"] = "exited"
    original = flow.runner.run

    def run(args, *, step, **kwargs):
        if (
            step == "inspect migration ledger"
            and flow.runner.services["postgres"] != "running"
        ):
            raise DeploymentError("database is stopped")
        return original(args, step=step, **kwargs)

    flow.runner.run = run
    result = flow.apply(COMMIT)
    assert result["previous"] is not None
    order = steps(flow)
    assert order.index("PostgreSQL readiness") < order.index("inspect migration ledger")
    assert flow.verify_active()["verified"]
