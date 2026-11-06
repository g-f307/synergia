"""Synthetic Docker drill. Owns only randomly named synergia-check-* projects."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import secrets
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

sys.dont_write_bytecode = True

from deploy import CommandRunner, Deployment, OperationStore  # noqa: E402
from deploy_common import (  # noqa: E402
    DeploymentError,
    atomic_json,
    compose_literals,
    private_json,
)
from deploy_recovery import RecoveryWorkflow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
USER_ID = "16600000-0000-4000-8000-000000000001"
FAULTS = {
    "build",
    "migration",
    "health",
    "smoke",
    "slow-migration",
    "initial-readiness",
}
SOURCE_FILES = (
    "docker-compose.yml",
    "backend/Dockerfile",
    "web/Dockerfile",
    "backend/app/deployment_environment.py",
    "backend/app/container_runtime.py",
    "scripts/container_entrypoint.py",
    "scripts/apply_migrations.py",
    "scripts/smoke_containers.py",
    "scripts/deploy.py",
    "scripts/deploy_common.py",
    "scripts/deploy_flow.py",
    "scripts/deploy_recovery.py",
    "scripts/validate_deploy.py",
)


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise DeploymentError(f"synthetic drill invariant failed: {reason}")


def available_port() -> int:
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


class FaultRunner(CommandRunner):
    """Inject one real Docker failure; never alter the trusted Compose snapshot."""

    def __init__(self, directory: Path, *, root: Path = ROOT) -> None:
        super().__init__(root)
        self.directory = directory
        self.fault: str | None = None

    def run(self, args, *, step, timeout=60, input_text=None):
        args = list(args)
        fault = self.fault
        if fault == "initial-readiness" and step == "PostgreSQL readiness":
            # Real timeout after creation: the fresh container's first healthcheck
            # runs at 5s, beyond this readiness deadline. Keep the trusted config.
            self.fault = None
            args[args.index("--wait-timeout") + 1] = "1"
            return super().run(args, step=step, timeout=timeout, input_text=input_text)
        matched = (
            fault == "build"
            and step == "build candidate"
            or fault in {"migration", "slow-migration"}
            and step == "apply migrations"
            or fault == "health"
            and step == "backend readiness"
            or fault == "smoke"
            and step == "application smoke"
        )
        if matched:
            self.fault = None
            if fault in {"build", "health"}:
                override = self.directory / f"fault-{fault}.json"
                services = {
                    "backend": {"build": {"dockerfile": "Dockerfile.synthetic-missing"}}
                }
                if fault == "health":
                    services = {
                        "backend": {
                            "healthcheck": {
                                "test": ["CMD", "python", "-c", "raise SystemExit(17)"],
                                "interval": "1s",
                                "timeout": "1s",
                                "retries": 1,
                                "start_period": "0s",
                            }
                        }
                    }
                atomic_json(override, {"services": services})
                position = args.index("build" if fault == "build" else "up")
                args[position:position] = ["--file", str(override)]
            elif fault in {"migration", "slow-migration"}:
                code = (
                    "import os,psycopg; "
                    "connection=psycopg.connect(os.environ['DATABASE_URL']); "
                    "connection.execute('SELECT 1/0')"
                )
                if fault == "slow-migration":
                    code = (
                        "import os,psycopg,time; "
                        "connection=psycopg.connect("
                        "os.environ['DATABASE_URL'],autocommit=True); "
                        "connection.execute('SELECT pg_advisory_lock(7347319119)'); "
                        "time.sleep(8)"
                    )
                args.extend(["python", "-c", code])
            else:
                args[args.index("--expected-api-origin") + 1] = (
                    "http://wrong.internal.example"
                )
        return super().run(args, step=step, timeout=timeout, input_text=input_text)


class Drill:
    def __init__(self, directory: Path, *, root: Path = ROOT) -> None:
        self.directory = directory
        self.root = root
        self.runner = FaultRunner(directory, root=root)
        self.revision = self.runner.run(
            ["git", "rev-parse", "HEAD"], step="drill revision"
        ).strip()
        self.cases: list[dict] = []
        self.environments: list[Deployment] = []
        self.private_values: list[str] = []

    @contextmanager
    def case(self, identifier: str):
        print(f"deploy drill: {identifier}", flush=True)
        started = time.monotonic()
        result = {"id": identifier, "status": "failed"}
        self.cases.append(result)
        try:
            yield
        except BaseException:
            raise
        else:
            result["status"] = "passed"
        finally:
            result["seconds"] = round(time.monotonic() - started, 3)

    def environment(self) -> RecoveryWorkflow:
        project = f"synergia-check-{secrets.token_hex(6)}"
        directory = self.directory / project
        directory.mkdir(mode=0o700)
        password = f"synthetic-{secrets.token_hex(20)}-$literal:${{not_expanded}}"
        signing = f"synthetic-{secrets.token_hex(32)}"
        rate = f"synthetic-{secrets.token_hex(32)}"
        self.private_values.extend((password, signing, rate))
        env = directory / "homologation.env"
        content = "\n".join(
            (
                "SYNERGIA_ENV=homologation",
                f"POSTGRES_PASSWORD='{password}'",
                f"AUTH_JWT_SIGNING_KEY={signing}",
                f"RATE_LIMIT_KEY_SECRET={rate}",
                "AUTH_ALLOWED_ORIGINS=http://web.internal.example",
                "SYNERGIA_API_ORIGIN=http://api.internal.example",
                "SYNERGIA_LOCAL_AUTH_ENABLED=false",
                "EMAIL_DELIVERY_ENABLED=false",
                f"POSTGRES_PORT={available_port()}",
                f"BACKEND_PORT={available_port()}",
                f"WEB_PORT={available_port()}",
            )
        )
        descriptor = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(content + "\n")
        deployment = Deployment(
            project=project,
            env_file=env,
            state_dir=directory / "history",
            runner=self.runner,
        )
        report = deployment.diagnose()
        require(
            not report["services"] and not any(report["volumes_present"].values()),
            "new project must have no existing resources",
        )
        self.environments.append(deployment)
        return RecoveryWorkflow(deployment, OperationStore)

    def sql(self, flow, sql):
        flow.inventory(allow_operations=True)
        return self.runner.run(
            [
                "docker",
                "exec",
                flow.containers["postgres"]["ID"],
                "psql",
                "-X",
                "-qAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "synergia",
                "-d",
                "synergia",
                "-c",
                sql,
            ],
            step="synthetic database fixture",
        ).strip()

    def seed(self, flow):
        self.sql(
            flow,
            f"INSERT INTO synergia.identity_users(id,display_name) "
            f"VALUES ('{USER_ID}', 'Synthetic deployment checkpoint');",
        )
        self.runner.run(
            [
                "docker",
                "exec",
                flow.containers["backend"]["ID"],
                "python",
                "-c",
                "from pathlib import Path; "
                "Path('/var/lib/synergia/imports/deploy-checkpoint.txt').write_text('synthetic')",
            ],
            step="synthetic storage fixture",
        )

    def data_snapshot(self, flow):
        ledger = self.sql(
            flow,
            "SELECT json_agg(row_to_json(m) ORDER BY filename) "
            "FROM public.synergia_schema_migrations m;",
        )
        count = self.sql(
            flow, f"SELECT count(*) FROM synergia.identity_users WHERE id='{USER_ID}';"
        )
        marker = self.runner.run(
            [
                "docker",
                "exec",
                flow.containers["backend"]["ID"],
                "python",
                "-c",
                "from pathlib import Path; "
                "print(Path('/var/lib/synergia/imports/deploy-checkpoint.txt').read_text())",
            ],
            step="synthetic storage verification",
        ).strip()
        return ledger, count, marker, flow.containers["postgres"]["ID"]

    def runtime_snapshot(self, flow):
        flow.inventory()
        return {
            name: item["ID"]
            for name, item in flow.containers.items()
            if name in {"postgres", "backend", "web"}
        }

    def history_snapshot(self, flow):
        path = flow.deployment.state_dir
        return (
            {
                str(item.relative_to(path)): hashlib.sha256(
                    item.read_bytes()
                ).hexdigest()
                for item in path.rglob("*")
                if item.is_file()
            }
            if path.exists()
            else {}
        )

    def expect_block(self, action: Callable, reason: str):
        try:
            action()
        except DeploymentError:
            return
        raise DeploymentError(f"synthetic drill expected a blocking failure: {reason}")

    def fault_case(self, flow, fault):
        active = flow.read_active()
        runtime = self.runtime_snapshot(flow)
        self.runner.fault = fault
        self.expect_block(lambda: flow.apply(self.revision), fault)
        require(self.runner.fault is None, "the real failure injection must execute")
        require(flow.read_active() == active, "failed candidate must not be promoted")
        record = private_json(flow.deployment.state_dir / "operation.json")
        if fault == "build":
            require(
                record["status"] == "failed", "build failure must precede maintenance"
            )
            require(
                self.runtime_snapshot(flow) == runtime,
                "build failure must preserve runtime",
            )
        else:
            require(
                record["status"] == "uncertain",
                "post-maintenance failure blocks retries",
            )
            self.expect_block(lambda: flow.apply(self.revision), "uncertain retry")
            process = flow.reconcile(record["id"])
            if fault == "migration":
                require(
                    process["migration"]["state"] == "failed",
                    "SQL failure must be observable",
                )
            flow.reconcile(record["id"], resolution="rollback")
        require(
            flow.verify_active()["verified"],
            "last confirmed version must remain usable",
        )

    def child(self, flow, *, slow=False):
        # Run a separate client so SIGTERM really interrupts the journal/lock owner.
        code = (
            "import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
            "from deploy import Deployment,OperationStore; "
            "from deploy_recovery import RecoveryWorkflow; "
            "from validate_deploy import FaultRunner; "
            "runner=FaultRunner(Path(sys.argv[2])); "
            "runner.fault='slow-migration' if sys.argv[7]=='slow' else None; "
            "flow=RecoveryWorkflow(Deployment(project=sys.argv[3],env_file=Path(sys.argv[4]),"
            "state_dir=Path(sys.argv[5]),runner=runner),OperationStore); "
            "flow.apply(sys.argv[6])"
        )
        output = tempfile.TemporaryFile(mode="w+")
        process = subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-S",
                "-c",
                code,
                str(self.root / "scripts"),
                str(self.directory),
                flow.deployment.project,
                str(flow.deployment.env_file),
                str(flow.deployment.state_dir),
                self.revision,
                "slow" if slow else "normal",
            ],
            cwd=self.root,
            env=self.runner.environment,
            stdout=output,
            stderr=output,
            start_new_session=True,
        )
        return process, output

    def interrupted(self, flow, *, resolution="resume", slow=False):
        process, output = self.child(flow, slow=slow)
        try:
            deadline = time.monotonic() + 300
            identifier = None
            while time.monotonic() < deadline:
                require(
                    process.poll() is None,
                    "client must reach the interruption checkpoint",
                )
                record = private_json(flow.deployment.state_dir / "operation.json")
                reached = record["status"] == "running" and record["stage"] == (
                    "migrate" if slow else "start"
                )
                if reached and (not slow or flow.lock_held()):
                    identifier = record["id"]
                    break
                time.sleep(0.05)
            require(identifier is not None, "interruption checkpoint timeout")
            os.killpg(process.pid, signal.SIGKILL if slow else signal.SIGTERM)
            process.wait(timeout=15)
            report = flow.reconcile(identifier)
            if slow:
                require(
                    report["migration_lock_held"],
                    "live migration lock must remain observable",
                )
                self.expect_block(
                    lambda: flow.reconcile(identifier, resolution="resume"),
                    "live migration reconciliation",
                )
                deadline = time.monotonic() + 30
                while (
                    report["migration_lock_held"]
                    or report["active_operations"]
                    or report["migration"]["state"] in {"running", "unknown"}
                ) and time.monotonic() < deadline:
                    time.sleep(0.25)
                    report = flow.reconcile(identifier)
                require(
                    not report["migration_lock_held"],
                    "migration connection must release its lock",
                )
            else:
                require(
                    report["migration"]["state"] == "completed",
                    "completed migration must be observable",
                )
            before = self.migration_ids(flow)
            self.expect_block(lambda: flow.apply(self.revision), "interrupted retry")
            flow.reconcile(identifier, resolution=resolution)
            require(
                self.migration_ids(flow) == before,
                "reconciliation must not rerun migrations",
            )
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=15)
            output.close()

    def migration_ids(self, flow):
        return self.runner.run(
            [
                "docker",
                "ps",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={flow.deployment.project}",
                "--filter",
                "label=com.docker.compose.service=migrate",
            ],
            step="migration execution inventory",
        ).splitlines()

    def legacy(self, previous_revision):
        revision = self.runner.run(
            [
                "git",
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{previous_revision}^{{commit}}",
            ],
            step="previous source revision",
        ).strip()
        require(
            re.fullmatch(r"[0-9a-f]{40}", revision) is not None,
            "previous commit must be explicit",
        )
        source = self.directory / "previous-source"
        source.mkdir(mode=0o700)
        archive = subprocess.run(
            [
                "git",
                "archive",
                revision,
                "backend",
                "web",
                "scripts",
                "database",
                ".dockerignore",
            ],
            cwd=self.root,
            env=self.runner.environment,
            capture_output=True,
            check=False,
        )
        require(archive.returncode == 0, "previous source archive must exist locally")
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as bundle:
            bundle.extractall(source, filter="data")
        flow = self.environment()
        flow.deployment.precheck()
        flow.config = flow.deployment.config
        images = {}
        for name in ("backend", "web"):
            tag = f"synergia-check-{name}:{flow.deployment.project}-previous"
            self.runner.run(
                [
                    "docker",
                    "build",
                    "--label",
                    f"org.opencontainers.image.revision={revision}",
                    "--build-arg",
                    f"SYNERGIA_BUILD_REVISION={revision}",
                    "--tag",
                    tag,
                    "--file",
                    str(source / name / "Dockerfile"),
                    str(source if name == "backend" else source / "web"),
                ],
                step="build previous version",
                timeout=1800,
            )
            images[name] = flow.inspect_image(tag, revision=revision)
        self.runner.run(
            ["docker", "pull", flow.config["services"]["postgres"]["image"]],
            step="prepare previous database image",
            timeout=300,
        )
        images["postgres"] = flow.inspect_image(
            flow.config["services"]["postgres"]["image"]
        )
        for name, service in flow.config["services"].items():
            service.pop("build", None)
            service["image"] = images[
                "postgres"
                if name == "postgres"
                else "web"
                if name == "web"
                else "backend"
            ]
        flow.compose_file = flow.deployment.env_file.parent / "previous-compose.json"
        atomic_json(flow.compose_file, compose_literals(flow.config))
        flow.compose(
            "run",
            "--rm",
            "--no-deps",
            "--pull",
            "never",
            "-T",
            "config-check",
            step="previous configuration check",
        )
        flow.compose(
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--pull",
            "never",
            "--wait",
            "--wait-timeout",
            "90",
            "postgres",
            step="previous database readiness",
            timeout=120,
        )
        flow.compose(
            "run",
            "--rm",
            "--no-deps",
            "--pull",
            "never",
            "-T",
            "migrate",
            step="previous migrations",
            timeout=600,
        )
        for name in ("backend", "web"):
            flow.compose(
                "up",
                "-d",
                "--no-deps",
                "--no-build",
                "--pull",
                "never",
                "--wait",
                "--wait-timeout",
                "150",
                name,
                step="previous application readiness",
                timeout=180,
            )
        flow.inventory()
        self.seed(flow)
        before = self.data_snapshot(flow)
        legacy_ledger = flow.ledger()
        with self.case("unmanaged_stopped_postgres_update"):
            self.runner.run(
                ["docker", "stop", "--time", "30", flow.containers["postgres"]["ID"]],
                step="stop synthetic previous PostgreSQL",
            )
            deployed = flow.apply(self.revision)
            require(
                flow.containers["postgres"]["ID"] == before[3],
                "adoption must restart the same PostgreSQL container",
            )
        baseline = flow.read_release(deployed["previous"])
        require(
            baseline["images"] == images, "baseline must capture previous exact images"
        )
        require(
            images["backend"] != deployed["images"]["backend"],
            "previous and current images must be distinct",
        )
        if deployed["migrations"] != legacy_ledger:
            self.expect_block(flow.rollback, "changed schema blocks previous code")
            return revision, "schema_change_blocked"
        restored = flow.rollback()
        require(restored["images"] == images, "rollback must use exact previous IDs")
        require(
            self.data_snapshot(flow) == before,
            "legacy rollback must preserve data and application dates",
        )
        flow.verify_active()
        return revision, "restored"

    def privacy(self):
        for deployment in self.environments:
            for path in deployment.state_dir.rglob("*"):
                if path.is_file():
                    require(
                        stat.S_IMODE(path.stat().st_mode) == 0o600,
                        "private artifact permissions",
                    )
                    if (
                        path.name
                        in {"operation.json", "release.json", "candidate.json"}
                        or path.parent.name == "reconciliations"
                    ):
                        text = path.read_text()
                        require(
                            not any(
                                value in text or value.replace("$", "$$") in text
                                for value in self.private_values
                            ),
                            "public journal must exclude secrets",
                        )

    def cleanup(self):
        # Cleanup is exclusive to this synthetic runner, never part of deploy.py.
        for deployment in self.environments:
            require(
                re.fullmatch(r"synergia-check-[0-9a-f]{12}", deployment.project)
                is not None,
                "cleanup project ownership",
            )
            identifiers = self.runner.run(
                [
                    "docker",
                    "ps",
                    "--all",
                    "--quiet",
                    "--no-trunc",
                    "--filter",
                    f"label=com.docker.compose.project={deployment.project}",
                ],
                step="synthetic cleanup inventory",
            ).splitlines()
            require(
                all(re.fullmatch(r"[0-9a-f]{64}", item) for item in identifiers),
                "cleanup container identity",
            )
            if identifiers:
                self.runner.run(
                    ["docker", "rm", "--force", "--volumes", *identifiers],
                    step="synthetic container cleanup",
                    timeout=90,
                )
            for key in ("synergia-postgres", "synergia-application-data"):
                name = f"{deployment.project}_{key}"
                present = self.runner.run(
                    ["docker", "volume", "ls", "--quiet", "--filter", f"name=^{name}$"],
                    step="synthetic volume inventory",
                ).splitlines()
                if present:
                    require(present == [name], "cleanup volume identity")
                    self.runner.run(
                        ["docker", "volume", "rm", name],
                        step="synthetic volume cleanup",
                    )
            networks = self.runner.run(
                [
                    "docker",
                    "network",
                    "ls",
                    "--quiet",
                    "--no-trunc",
                    "--filter",
                    f"label=com.docker.compose.project={deployment.project}",
                ],
                step="synthetic network inventory",
            ).splitlines()
            if networks:
                self.runner.run(
                    ["docker", "network", "rm", *networks],
                    step="synthetic network cleanup",
                )

    def resource_inventory(self):
        # Only identifiers in memory; do not publish other projects' names.
        return {
            resource: set(
                self.runner.run(command, step="host resource inventory").splitlines()
            )
            for resource, command in (
                ("containers", ["docker", "ps", "--all", "--quiet", "--no-trunc"]),
                ("volumes", ["docker", "volume", "ls", "--quiet"]),
                ("networks", ["docker", "network", "ls", "--quiet", "--no-trunc"]),
            )
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="sanitized JSON report only"
    )
    parser.add_argument(
        "--previous-revision", default="HEAD^", help="locally available prior commit"
    )
    args = parser.parse_args(argv)
    private = Path(tempfile.mkdtemp(prefix="synergia-deploy-check-"))
    drill = Drill(private)
    result = {
        "format": 1,
        "environment": "homologation",
        "synthetic_only": True,
        "started_at": datetime.now(UTC).isoformat(),
        "source_revision": drill.revision,
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCE_FILES
        },
        "cases": drill.cases,
        "result": "failed",
        "cleanup": "pending",
    }
    exit_code = 1
    before_resources = drill.resource_inventory()
    try:
        flow = drill.environment()
        with drill.case("diagnosis_read_only_empty"):
            before = drill.history_snapshot(flow)
            flow.deployment.diagnose()
            require(
                drill.history_snapshot(flow) == before
                and not flow.deployment.state_dir.exists(),
                "diagnosis must not create state",
            )
        with drill.case("invalid_configuration_blocked"):
            config = flow.deployment.env_file
            original = config.read_text()
            try:
                config.write_text(
                    original.replace(
                        "SYNERGIA_ENV=homologation", "SYNERGIA_ENV=invalid"
                    )
                )
                drill.expect_block(flow.deployment.diagnose, "invalid configuration")
            finally:
                config.write_text(original)
            require(
                not flow.deployment.state_dir.exists(),
                "invalid configuration must not create history",
            )
        with drill.case("initial_readiness_failure_after_creation"):
            drill.runner.fault = "initial-readiness"
            drill.expect_block(
                lambda: flow.apply(drill.revision, initialize=True),
                "initial readiness timeout after resource creation",
            )
            record = private_json(flow.deployment.state_dir / "operation.json")
            require(
                record["status"] == "uncertain", "initial failure must be reconcilable"
            )
            flow.inventory()
            pg = flow.containers["postgres"]["ID"]
            volumes = dict(flow.deployment.precheck()["volumes_present"])
            require(any(volumes.values()), "PostgreSQL volume must really exist")
            require(flow.read_active() is None, "initial failure must not promote")
            for initialize in (False, True):
                drill.expect_block(
                    lambda: flow.apply(drill.revision, initialize=initialize),
                    "unresolved initial operation must block blind retries",
                )
            require(
                flow.reconcile(record["id"])["initialization_pending"],
                "read-only reconciliation must identify pending initialization",
            )
            flow.reconcile(record["id"], resolution="resume")
            require(
                flow.containers["postgres"]["ID"] == pg,
                "explicit resume must preserve PostgreSQL container",
            )
            require(
                flow.read_active()["id"] == record["id"],
                "initial resume must retain operation identity",
            )
        flow = drill.environment()
        with drill.case("initial_installation"):
            flow.apply(drill.revision, initialize=True)
            flow.verify_active()
            drill.seed(flow)
        with drill.case("source_metadata_non_root_and_worker_opt_in"):
            flow.inventory()
            runtime = flow.runtime(flow.containers["backend"])
            require(
                runtime["environment"].get("SYNERGIA_BUILD_REVISION") == drill.revision,
                "startup source revision must match the deployed commit",
            )
            for name in ("backend", "web"):
                user = drill.runner.run(
                    ["docker", "exec", flow.containers[name]["ID"], "id", "-u"],
                    step="runtime user identity",
                ).strip()
                require(user != "0", "application containers must not run as root")
            require(
                all(
                    item["Service"] != "email-worker"
                    for item in flow.deployment.containers
                ),
                "deployment must not create the email worker",
            )
        data = drill.data_snapshot(flow)
        with drill.case("repeat_update_preserves_data"):
            flow.apply(drill.revision)
            require(
                drill.data_snapshot(flow) == data,
                "repeat update must preserve ledger dates, user, file and PostgreSQL",
            )
        with drill.case("postgres_port_change_blocked"):
            config = flow.deployment.env_file
            original = config.read_text()
            active = flow.read_active()
            runtime = drill.runtime_snapshot(flow)
            try:
                config.write_text(
                    re.sub(
                        r"(?m)^POSTGRES_PORT=.*$",
                        f"POSTGRES_PORT={available_port()}",
                        original,
                    )
                )
                drill.expect_block(
                    lambda: flow.apply(drill.revision), "database port drift"
                )
                require(
                    flow.read_active() == active
                    and drill.runtime_snapshot(flow) == runtime,
                    "database port drift must precede build and shutdown",
                )
            finally:
                config.write_text(original)
            flow.verify_active()
        with drill.case("diagnosis_read_only_running"):
            history = drill.history_snapshot(flow)
            runtime = drill.runtime_snapshot(flow)
            flow.deployment.diagnose()
            require(
                drill.history_snapshot(flow) == history
                and drill.runtime_snapshot(flow) == runtime,
                "live diagnosis must not alter resources",
            )
        with drill.case("concurrent_client_blocked"):
            report = flow.inventory()
            store = OperationStore(
                flow.deployment.state_dir,
                identity=f"{report['daemon_id']}:{report['project']}",
            )
            with store.lock():
                process, output = drill.child(flow)
                try:
                    require(
                        process.wait(timeout=30) != 0, "concurrent client must fail"
                    )
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=15)
                    output.close()
        for fault in ("build", "migration", "health", "smoke"):
            with drill.case(f"real_{fault}_failure"):
                drill.fault_case(flow, fault)
                require(
                    drill.data_snapshot(flow) == data,
                    "failure recovery must preserve data",
                )
        for resolution in ("resume", "rollback"):
            with drill.case(f"interrupted_client_{resolution}"):
                drill.interrupted(flow, resolution=resolution)
                require(
                    drill.data_snapshot(flow) == data,
                    "interrupted recovery must preserve data",
                )
        with drill.case("interrupted_live_migration"):
            drill.interrupted(flow, slow=True)
            require(
                drill.data_snapshot(flow) == data,
                "live migration recovery must preserve data",
            )
        with drill.case("schema_divergence_blocks_rollback"):
            runtime = drill.runtime_snapshot(flow)
            drill.sql(
                flow,
                "INSERT INTO public.synergia_schema_migrations(filename,sha256) "
                "VALUES ('9999_synthetic_guard.sql',repeat('b',64));",
            )
            try:
                drill.expect_block(flow.rollback, "schema divergence")
                require(
                    drill.runtime_snapshot(flow) == runtime,
                    "incompatible rollback must precede shutdown",
                )
            finally:
                drill.sql(
                    flow,
                    "DELETE FROM public.synergia_schema_migrations "
                    "WHERE filename='9999_synthetic_guard.sql';",
                )
        with drill.case("altered_recovery_artifact_blocked"):
            active = flow.read_active()
            path = flow.deployment.state_dir / active["previous"] / "compose.json"
            original = path.read_bytes()
            runtime = drill.runtime_snapshot(flow)
            try:
                path.write_bytes(original + b" ")
                drill.expect_block(flow.rollback, "altered recovery configuration")
                require(
                    drill.runtime_snapshot(flow) == runtime,
                    "artifact failure must precede shutdown",
                )
            finally:
                path.write_bytes(original)
        with drill.case("legacy_previous_version"):
            previous, outcome = drill.legacy(args.previous_revision)
            result["previous_revision"] = previous
            result["previous_version_outcome"] = outcome
        with drill.case("private_artifact_and_journal_hygiene"):
            drill.privacy()
        with drill.case("missing_application_volume_blocks_recovery"):
            # Destructive infrastructure fault only in our disposable project,
            # after every preservation check; never reproduce this on real data.
            flow.inventory()
            require(
                re.fullmatch(r"synergia-check-[0-9a-f]{12}", flow.deployment.project)
                is not None,
                "storage fault requires a synthetic project",
            )
            active = flow.read_active()
            web = flow.containers["web"]["ID"]
            volume = f"{flow.deployment.project}_synergia-application-data"
            drill.runner.run(
                ["docker", "rm", "--force", flow.containers["backend"]["ID"]],
                step="synthetic missing backend fixture",
            )
            drill.runner.run(
                ["docker", "volume", "rm", volume],
                step="synthetic missing volume fixture",
            )
            drill.expect_block(flow.rollback, "missing persistent storage")
            report = flow.deployment.diagnose()
            require(
                not report["volumes_present"]["synergia-application-data"],
                "recovery must not create an empty replacement volume",
            )
            require(
                flow.read_active() == active and flow.containers["web"]["ID"] == web,
                "missing storage must block before stopping remaining writers",
            )
        result["result"] = "passed"
        exit_code = 0
    except (Exception, KeyboardInterrupt) as exc:
        result["failure"] = (
            str(exc)
            if isinstance(exc, DeploymentError)
            else "unexpected infrastructure failure"
        )
        print(
            f"deploy drill failed: {result['failure']}",
            file=sys.stderr,
        )
    finally:
        try:
            drill.cleanup()
            require(
                drill.resource_inventory() == before_resources,
                "all pre-existing resources must be preserved",
            )
            result["cleanup"] = "passed"
            result["preexisting_resources_preserved"] = True
        except Exception:
            result["cleanup"] = "failed"
            result["result"] = "failed"
            exit_code = 1
        result["finished_at"] = datetime.now(UTC).isoformat()
        public = json.dumps(result)
        if any(
            value in public or value.replace("$", "$$") in public
            for value in drill.private_values
        ):
            result = {
                "format": 1,
                "result": "failed",
                "cleanup": result["cleanup"],
                "failure": "public report hygiene failed",
            }
            exit_code = 1
        args.output.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(args.output, result)
    print(f"deploy drill: result={result['result']} cleanup={result['cleanup']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
