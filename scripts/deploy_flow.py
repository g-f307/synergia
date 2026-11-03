"""Controlled application update. Database downgrades are never executed."""

from __future__ import annotations

import copy
import hashlib
import re
import sys
from datetime import UTC, datetime
from uuid import UUID

from deploy_common import (
    DeploymentError,
    atomic_json,
    compose_literals,
    compose_values,
    parse_json,
    private_json,
    published_ports_match,
)

IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
MIGRATION_NAME = re.compile(r"[0-9]{4}_[a-z0-9_]+\.sql")
INSPECT_RUNTIME = (
    '{"image":{{json .Image}},"environment":{{json .Config.Env}},'
    '"command":{{json .Config.Cmd}},"entrypoint":{{json .Config.Entrypoint}},'
    '"ports":{{json .HostConfig.PortBindings}},"labels":{{json .Config.Labels}},'
    '"user":{{json (index .Config "User")}},'
    '"healthcheck":{{json (index .Config "Healthcheck")}},'
    '"restart":{{json .HostConfig.RestartPolicy}},"mounts":{{json .Mounts}}}'
)


class ApplyWorkflow:
    def __init__(self, deployment, store_type) -> None:
        self.deployment = deployment
        self.runner = deployment.runner
        self.store_type = store_type

    def run(self, args, step, timeout=60, *, input_text=None):
        kwargs = {"step": step, "timeout": timeout}
        if input_text is not None:
            kwargs["input_text"] = input_text
        return self.runner.run(args, **kwargs)

    def inventory(self, *, allow_operations=False):
        report = self.deployment.precheck()
        containers = {}
        self.active_operations = []
        for item in self.deployment.containers:
            if item["State"] not in {"exited", "created", "dead"} and (
                item["Service"] in {"email-worker", "migrate", "config-check"}
                or item.get("OneOff", "").lower() == "true"
            ):
                self.active_operations.append(item)
                if not allow_operations:
                    raise DeploymentError(
                        "a worker or one-off operation is active; "
                        "wait and reconcile before deploying"
                    )
            if item.get("OneOff", "").lower() == "true":
                continue
            name = item["Service"]
            if name in containers:
                raise DeploymentError("multiple containers per service are unsupported")
            if not re.fullmatch(r"[0-9a-f]{12,64}", item.get("ID", "")):
                raise DeploymentError("installation inventory: invalid container ID")
            containers[name] = item
        self.containers = containers
        return report

    def runtime(self, container):
        value = parse_json(
            self.run(
                ["docker", "inspect", "--format", INSPECT_RUNTIME, container["ID"]],
                "capture current runtime",
            ),
            "capture current runtime",
        )
        try:
            if not IMAGE_ID.fullmatch(value["image"]):
                raise ValueError
            value["environment"] = dict(
                item.split("=", 1) for item in value["environment"]
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise DeploymentError("current runtime cannot be preserved safely") from exc
        return value

    def compose(self, *args, step, timeout=60):
        return self.run(
            [
                "docker",
                "compose",
                "--project-name",
                self.deployment.project,
                "--env-file",
                "/dev/null",
                "--file",
                str(self.compose_file),
                *args,
            ],
            step,
            timeout,
        )

    def save_config(self):
        atomic_json(self.compose_file, compose_literals(self.config))

    def inspect_image(self, reference, *, revision=None):
        info = parse_json(
            self.run(
                [
                    "docker",
                    "image",
                    "inspect",
                    "--format",
                    '{"id":{{json .Id}},"labels":{{json (index .Config "Labels")}}}',
                    reference,
                ],
                "resolve immutable image",
            ),
            "resolve immutable image",
        )
        try:
            if not IMAGE_ID.fullmatch(info["id"]):
                raise ValueError
            if (
                revision is not None
                and (info.get("labels") or {}).get("org.opencontainers.image.revision")
                != revision
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise DeploymentError(
                "image identity or source revision does not match"
            ) from exc
        return info["id"]

    def ledger(self):
        pg = self.containers["postgres"]
        environment = self.runtime(pg)["environment"]
        args = [
            "docker",
            "exec",
            pg["ID"],
            "psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            environment.get("POSTGRES_USER", "postgres"),
            "-d",
            environment.get("POSTGRES_DB", "postgres"),
            "-c",
        ]
        exists = self.run(
            [
                *args,
                "BEGIN READ ONLY; SELECT "
                "(to_regclass('public.synergia_schema_migrations') "
                "IS NOT NULL)::text; COMMIT;",
            ],
            "inspect migration ledger",
        ).strip()
        if exists == "false":
            return None
        if exists != "true":
            raise DeploymentError("migration ledger: unexpected database response")
        value = parse_json(
            self.run(
                [
                    *args,
                    "BEGIN READ ONLY; SELECT "
                    "COALESCE(json_object_agg(filename, sha256), "
                    "'{}'::json) FROM public.synergia_schema_migrations; COMMIT;",
                ],
                "read migration ledger",
            ),
            "read migration ledger",
        )
        if not isinstance(value, dict) or not all(
            isinstance(name, str)
            and MIGRATION_NAME.fullmatch(name)
            and isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest)
            for name, digest in value.items()
        ):
            raise DeploymentError("migration ledger: invalid inventory")
        return value

    def expected_ledger(self):
        files = sorted((self.runner.root / "database/migrations").glob("*.sql"))
        if not files or any(not MIGRATION_NAME.fullmatch(path.name) for path in files):
            raise DeploymentError("source migration inventory is invalid")
        return {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files
        }

    def read_release(self, release_id):
        try:
            if not isinstance(release_id, str) or str(UUID(release_id)) != release_id:
                raise ValueError
        except (KeyError, ValueError, TypeError) as exc:
            raise DeploymentError("active deployment reference invalid") from exc
        manifest = private_json(self.deployment.state_dir / release_id / "release.json")
        return self.validate_manifest(manifest, release_id)

    def validate_manifest(self, manifest, release_id):
        try:
            if (
                manifest["id"] != release_id
                or manifest["format"] != 1
                or not (
                    manifest["revision"] is None
                    and manifest.get("kind") == "baseline"
                    or isinstance(manifest["revision"], str)
                    and REVISION.fullmatch(manifest["revision"])
                )
                or set(manifest["images"]) != {"backend", "web", "postgres"}
                or not all(
                    IMAGE_ID.fullmatch(value) for value in manifest["images"].values()
                )
                or not re.fullmatch(r"[0-9a-f]{64}", manifest["compose_sha256"])
                or manifest["project"] != self.deployment.project
                or not isinstance(manifest["daemon_id"], str)
                or manifest["environment"]
                not in {"development", "test", "homologation", "production"}
                or not valid_migrations(manifest["migrations"])
            ):
                raise ValueError
            if manifest["previous"] is not None:
                if str(UUID(manifest["previous"])) != manifest["previous"]:
                    raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise DeploymentError("active deployment identity invalid") from exc
        return manifest

    def read_active(self):
        pointer = self.deployment.state_dir / "active.json"
        if pointer.is_symlink():
            raise DeploymentError("active deployment reference invalid")
        if not pointer.exists():
            return None
        return self.read_release(private_json(pointer).get("release"))

    def apply(self, revision, *, initialize=False):
        report = self.inventory()
        chosen = self.run(
            [
                "git",
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{revision}^{{commit}}",
            ],
            "chosen revision",
        ).strip()
        if not REVISION.fullmatch(chosen) or chosen != report["revision"]:
            raise DeploymentError("checkout must match --revision before deploying")
        identity = f"{report['daemon_id']}:{report['project']}"
        store = self.store_type(self.deployment.state_dir, identity=identity)
        maintenance = False
        with store.operation("apply") as operation:
            try:
                # Recheck after taking the lock, before touching application resources.
                report = self.inventory()
                if report["revision"] != chosen:
                    raise DeploymentError("source revision changed during precheck")
                active = self.read_active()
                if active and active["daemon_id"] != report["daemon_id"]:
                    raise DeploymentError("active deployment belongs to another daemon")
                present = report["volumes_present"]
                empty = not self.containers and not any(present.values())
                if empty != initialize:
                    raise DeploymentError(
                        "empty installation requires --initialize; "
                        "existing installations must omit it"
                    )
                if not empty and (
                    not all(present.values())
                    or not all(
                        name in self.containers
                        for name in ("postgres", "backend", "web")
                    )
                ):
                    raise DeploymentError(
                        "partial installation; reconcile resources before updating"
                    )
                if empty and active:
                    raise DeploymentError(
                        "active history exists but installation is absent"
                    )
                self.release_dir = self.deployment.state_dir / operation["id"]
                self.release_dir.mkdir(mode=0o700)
                self.compose_file = self.release_dir / "compose.json"
                self.config = copy.deepcopy(self.deployment.config)
                original_config = copy.deepcopy(self.config)
                self.before = {
                    name: self.runtime(self.containers[name])
                    for name in ("postgres", "backend", "web")
                    if name in self.containers
                }
                if self.before:
                    current_pg = self.before["postgres"]["environment"]
                    proposed_pg = self.config["services"]["postgres"]["environment"]
                    if any(
                        current_pg.get(key) != proposed_pg.get(key)
                        for key in ("POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD")
                    ):
                        raise DeploymentError(
                            "database credentials/identity changed; "
                            "use a separate database procedure"
                        )
                    if not published_ports_match(
                        self.config["services"]["postgres"].get("ports"),
                        self.before["postgres"].get("ports"),
                    ):
                        raise DeploymentError(
                            "PostgreSQL published ports changed; "
                            "use a separate database procedure"
                        )
                atomic_json(self.release_dir / "before-runtime.json", self.before)
                for name in ("backend", "web"):
                    if name in self.before:
                        self.run(
                            [
                                "docker",
                                "image",
                                "tag",
                                self.before[name]["image"],
                                f"synergia-{name}:retained-{operation['id']}",
                            ],
                            "retain previous image",
                        )
                services = self.config["services"]
                for name in (
                    "config-check",
                    "migrate",
                    "backend",
                    "email-worker",
                    "web",
                ):
                    if name not in services:
                        continue
                    kind = "web" if name == "web" else "backend"
                    services[name]["image"] = (
                        f"synergia-{kind}:deploy-{operation['id']}"
                    )
                    if "build" in services[name]:
                        services[name]["build"].setdefault("args", {})[
                            "SYNERGIA_BUILD_REVISION"
                        ] = chosen
                self.save_config()
                store.stage(operation, "build")
                self.compose(
                    "build", "backend", "web", step="build candidate", timeout=1800
                )
                images = {
                    name: self.inspect_image(services[name]["image"], revision=chosen)
                    for name in ("backend", "web")
                }
                if not self.before:
                    self.run(
                        ["docker", "pull", services["postgres"]["image"]],
                        "prepare PostgreSQL image",
                        timeout=300,
                    )
                images["postgres"] = (
                    self.before["postgres"]["image"]
                    if self.before
                    else self.inspect_image(services["postgres"]["image"])
                )
                for name, service in services.items():
                    service.pop("build", None)
                    service["image"] = images[
                        "web"
                        if name == "web"
                        else ("postgres" if name == "postgres" else "backend")
                    ]
                self.save_config()
                # Catch source edits while Docker was reading the build contexts.
                if self.inventory()["revision"] != chosen:
                    raise DeploymentError("source revision changed during build")
                if self.deployment.config != original_config:
                    raise DeploymentError("external configuration changed during build")
                self.compose(
                    "run",
                    "--no-deps",
                    "--pull",
                    "never",
                    "--rm",
                    "-T",
                    "config-check",
                    step="candidate configuration",
                )
                self.compose(
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-build",
                    "--no-recreate",
                    "--pull",
                    "never",
                    "--wait",
                    "--wait-timeout",
                    "90",
                    "postgres",
                    step="PostgreSQL readiness",
                    timeout=120,
                )
                self.inventory()
                previous = active
                if not previous and self.before:
                    from deploy_recovery import RecoveryWorkflow

                    previous = RecoveryWorkflow(
                        self.deployment, self.store_type
                    ).capture_baseline(
                        report, original_config, self.before, self.ledger()
                    )
                expected = self.expected_ledger()
                candidate = {
                    "format": 1,
                    "id": operation["id"],
                    "project": report["project"],
                    "daemon_id": report["daemon_id"],
                    "revision": chosen,
                    "environment": report["environment"],
                    "images": images,
                    "migrations": expected,
                    "previous": previous["id"] if previous else None,
                    "created_at": datetime.now(UTC).isoformat(),
                    "compose_sha256": hashlib.sha256(
                        self.compose_file.read_bytes()
                    ).hexdigest(),
                }
                atomic_json(self.release_dir / "candidate.json", candidate)
                store.stage(operation, "maintenance")
                maintenance = True
                writers = [
                    item["ID"]
                    for name, item in self.containers.items()
                    if name in {"web", "backend"}
                ]
                if writers:
                    self.run(
                        ["docker", "stop", "--time", "30", *writers],
                        "stop application writers",
                        timeout=90,
                    )
                self.inventory()
                if any(
                    item["State"] != "exited"
                    for name, item in self.containers.items()
                    if name in {"web", "backend"}
                ):
                    raise DeploymentError("application writers did not stop")
                before_ledger = self.ledger()
                if previous and before_ledger != previous["migrations"]:
                    raise DeploymentError(
                        "migration history changed since the previous deployment"
                    )
                if before_ledger and any(
                    expected.get(name) != digest
                    for name, digest in before_ledger.items()
                ):
                    raise DeploymentError(
                        "published migration history differs from candidate"
                    )
                atomic_json(
                    self.release_dir / "migration-before.json",
                    {
                        "migrations": before_ledger,
                    },
                )
                store.stage(operation, "migrate")
                # Keep the named container as evidence if the client times out.
                self.compose(
                    "run",
                    "--no-deps",
                    "--pull",
                    "never",
                    "-T",
                    "--name",
                    f"{self.deployment.project}-migration-{operation['id']}",
                    "migrate",
                    step="apply migrations",
                    timeout=600,
                )
                after_ledger = self.ledger()
                if after_ledger != expected:
                    raise DeploymentError(
                        "migration ledger does not match candidate source"
                    )
                print(
                    "migrations verified: "
                    f"applied={len(expected) - len(before_ledger or {})} "
                    f"total={len(expected)}",
                    file=sys.stderr,
                    flush=True,
                )
                atomic_json(
                    self.release_dir / "migration-after.json",
                    {
                        "migrations": after_ledger,
                    },
                )
                store.stage(operation, "start")
                for name in ("backend", "web"):
                    self.compose(
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
                        step=f"{name} readiness",
                        timeout=180,
                    )
                store.stage(operation, "verify")
                self.verify(images, after_ledger)
                manifest = candidate
                atomic_json(self.release_dir / "release.json", manifest)
                store.stage(operation, "confirm")
                atomic_json(
                    self.deployment.state_dir / "active.json",
                    {"release": operation["id"]},
                )
                print(
                    f"deployment confirmed: revision={chosen}",
                    file=sys.stderr,
                    flush=True,
                )
                return manifest
            except BaseException:
                if not maintenance:
                    operation["status"] = "failed"
                raise

    def verify(self, images, migrations):
        self.inventory()
        for name in ("postgres", "backend", "web"):
            if (
                name not in self.containers
                or self.containers[name]["State"] != "running"
            ):
                raise DeploymentError(f"verification: {name} is not running")
            runtime = self.runtime(self.containers[name])
            if runtime["image"] != images[name]:
                raise DeploymentError(
                    f"verification: {name} image differs from candidate"
                )
            expected_environment = self.config["services"][name].get("environment", {})
            if any(
                runtime["environment"].get(key) != value
                for key, value in expected_environment.items()
            ):
                raise DeploymentError(
                    f"verification: {name} environment differs from release"
                )
            if not published_ports_match(
                self.config["services"][name].get("ports"), runtime.get("ports")
            ):
                raise DeploymentError(
                    f"verification: {name} published ports differ from release"
                )
        if self.ledger() != migrations:
            raise DeploymentError(
                "verification: migration history differs from release"
            )
        # Use the existing smoke protocol inside the exact new images. This also
        # avoids host proxy settings and ambiguous published ports.
        self.run(
            [
                "docker",
                "exec",
                "-i",
                self.containers["backend"]["ID"],
                "python",
                "-",
                "--backend-url",
                "http://127.0.0.1:8000",
                "--web-url",
                "http://web:8080",
                "--expected-api-origin",
                self.config["services"]["web"]["environment"]["SYNERGIA_API_ORIGIN"],
            ],
            "application smoke",
            timeout=540,
            input_text=(self.runner.root / "scripts/smoke_containers.py").read_text(),
        )
        self.compose(
            "exec",
            "-T",
            "web",
            "wget",
            "-q",
            "-O",
            "/dev/null",
            "http://127.0.0.1:8080/",
            step="web smoke",
        )

    def verify_active(self):
        report = self.inventory()
        if report["operation"] and report["operation"]["status"] in {
            "running",
            "uncertain",
        }:
            raise DeploymentError(
                "operation unresolved; diagnose and reconcile before verifying"
            )
        active = self.read_active()
        if not active:
            raise DeploymentError(
                "no confirmed deployment; run diagnose and reconcile history"
            )
        if (active.get("daemon_id"), active.get("project")) != (
            report["daemon_id"],
            report["project"],
        ):
            raise DeploymentError("active deployment belongs to another installation")
        self.compose_file = self.deployment.state_dir / active["id"] / "compose.json"
        if (
            hashlib.sha256(self.compose_file.read_bytes()).hexdigest()
            != active["compose_sha256"]
        ):
            raise DeploymentError("confirmed deployment configuration changed")
        self.config = compose_values(private_json(self.compose_file))
        self.verify(active["images"], active["migrations"])
        return {"revision": active["revision"], "verified": True}


def valid_migrations(value):
    return isinstance(value, dict) and all(
        isinstance(name, str)
        and MIGRATION_NAME.fullmatch(name)
        and isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest)
        for name, digest in value.items()
    )
