"""Explicit application recovery, without migrations or database restores."""

from __future__ import annotations

import copy
import hashlib
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from deploy_common import (
    DeploymentError,
    atomic_json,
    compose_literals,
    compose_values,
    parse_json,
    private_json,
)
from deploy_flow import IMAGE_ID, REVISION, ApplyWorkflow, valid_migrations

from app.deployment_environment import validate_deployment_environment


class RecoveryWorkflow(ApplyWorkflow):
    def capture_baseline(self, report, original, runtime, migrations):
        if not valid_migrations(migrations):
            raise DeploymentError(
                "unmanaged installation requires a validated migration ledger"
            )
        identifier = str(uuid4())
        directory = self.deployment.state_dir / identifier
        directory.mkdir(mode=0o700)
        config = copy.deepcopy(original)
        config["services"] = {
            name: runtime_service(config["services"][name], runtime[name], config)
            for name in ("postgres", "backend", "web")
        }
        path = directory / "compose.json"
        atomic_json(path, compose_literals(config))
        self.compose_file = path
        self.compose("config", "--quiet", step="baseline Compose validation")
        revision = (runtime["backend"].get("labels") or {}).get(
            "org.opencontainers.image.revision"
        )
        if not isinstance(revision, str) or not REVISION.fullmatch(revision):
            revision = None
        manifest = {
            "format": 1,
            "kind": "baseline",
            "id": identifier,
            "project": report["project"],
            "daemon_id": report["daemon_id"],
            "revision": revision,
            "environment": runtime["backend"]["environment"].get(
                "SYNERGIA_ENV", report["environment"]
            ),
            "images": {name: item["image"] for name, item in runtime.items()},
            "migrations": migrations,
            "previous": None,
            "created_at": datetime.now(UTC).isoformat(),
            "compose_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        atomic_json(directory / "release.json", manifest)
        return manifest

    def select(self, manifest, report):
        if (manifest.get("project"), manifest.get("daemon_id")) != (
            report["project"],
            report["daemon_id"],
        ):
            raise DeploymentError("recovery artifact belongs to another installation")
        self.release_dir = self.deployment.state_dir / manifest["id"]
        self.compose_file = self.release_dir / "compose.json"
        self.config = compose_values(private_json(self.compose_file))
        if (
            hashlib.sha256(self.compose_file.read_bytes()).hexdigest()
            != manifest["compose_sha256"]
        ):
            raise DeploymentError(
                "recovery configuration changed; restore trusted artifacts"
            )
        self.compose("config", "--quiet", step="recovery Compose validation")
        try:
            services = self.config["services"]
            if any(
                services[name]["image"] != manifest["images"][name]
                for name in ("postgres", "backend", "web")
            ):
                raise ValueError
            if any(
                self.config["volumes"][key]["name"] != expected
                for key, expected in report["volumes"].items()
            ):
                raise ValueError
            validate_deployment_environment(services["backend"]["environment"])
        except (KeyError, ValueError, TypeError) as exc:
            raise DeploymentError(
                "recovery configuration invalid; review protected artifacts"
            ) from exc
        for name, image in manifest["images"].items():
            if not IMAGE_ID.fullmatch(image) or self.inspect_image(image) != image:
                raise DeploymentError(
                    "retained image is unavailable; restore exact artifacts"
                )
        if (
            "postgres" not in self.containers
            or self.containers["postgres"]["State"] != "running"
        ):
            raise DeploymentError(
                "PostgreSQL must already be running; recovery never recreates it"
            )
        pg = self.runtime(self.containers["postgres"])
        if pg["image"] != manifest["images"]["postgres"]:
            raise DeploymentError(
                "PostgreSQL image changed; "
                "database recovery requires a separate procedure"
            )
        if any(
            pg["environment"].get(key) != value
            for key, value in services["postgres"].get("environment", {}).items()
        ):
            raise DeploymentError(
                "PostgreSQL configuration changed; reconcile database access"
            )
        if self.lock_held():
            raise DeploymentError(
                "database migration lock is held; wait and inspect the owner"
            )
        if self.ledger() != manifest["migrations"]:
            raise DeploymentError(
                "migration history differs from recovery target; "
                "application rollback blocked; use the database recovery procedure"
            )

    def lock_held(self):
        pg = self.containers.get("postgres")
        if not pg or pg["State"] != "running":
            raise DeploymentError("database unavailable for reconciliation")
        environment = self.runtime(pg)["environment"]
        sql = (
            "BEGIN READ ONLY; SELECT EXISTS (SELECT 1 FROM pg_locks "
            "WHERE locktype='advisory' AND classid=1 AND objid=3052351823 "
            "AND database=(SELECT oid FROM pg_database "
            "WHERE datname=current_database()) "
            "AND granted)::text; COMMIT;"
        )
        value = self.run(
            [
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
                sql,
            ],
            "inspect migration lock",
        ).strip()
        if value not in {"true", "false"}:
            raise DeploymentError("migration lock response unknown; reconcile database")
        return value == "true"

    def start_recovery(self, manifest, report):
        self.select(manifest, report)
        writers = [
            item["ID"]
            for name, item in self.containers.items()
            if name in {"backend", "web"}
        ]
        if writers:
            self.run(
                ["docker", "stop", "--time", "30", *writers],
                "stop application writers",
                timeout=90,
            )
        self.inventory()
        # Recheck after draining writers, immediately before starting old code.
        if self.lock_held() or self.ledger() != manifest["migrations"]:
            raise DeploymentError(
                "migration state changed during recovery; keep maintenance"
            )
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
        self.verify(manifest["images"], manifest["migrations"])

    def rollback(self):
        report = self.inventory()
        active = self.read_active()
        if not active or not active["previous"]:
            raise DeploymentError("no previous deployment is available for rollback")
        target = self.read_release(active["previous"])
        self.select(
            target, report
        )  # Validate all artifacts before touching the application.
        store = self.store_type(
            self.deployment.state_dir,
            identity=f"{report['daemon_id']}:{report['project']}",
        )
        maintenance = False
        with store.operation("rollback") as operation:
            try:
                report = self.inventory()
                if self.read_active() != active:
                    raise DeploymentError(
                        "active deployment changed; diagnose before rollback"
                    )
                self.select(target, report)
                directory = self.deployment.state_dir / operation["id"]
                directory.mkdir(mode=0o700)
                self.compose_file = directory / "compose.json"
                self.save_config()
                candidate = dict(target) | {
                    "id": operation["id"],
                    "previous": active["id"],
                    "created_at": datetime.now(UTC).isoformat(),
                    "compose_sha256": hashlib.sha256(
                        self.compose_file.read_bytes()
                    ).hexdigest(),
                }
                atomic_json(directory / "candidate.json", candidate)
                store.stage(operation, "maintenance")
                maintenance = True
                self.start_recovery(candidate, report)
                store.stage(operation, "confirm")
                self.promote(candidate)
                return candidate
            except BaseException:
                if not maintenance:
                    operation["status"] = "failed"
                raise

    def promote(self, manifest):
        atomic_json(
            self.deployment.state_dir / manifest["id"] / "release.json", manifest
        )
        atomic_json(
            self.deployment.state_dir / "active.json", {"release": manifest["id"]}
        )

    def migration_process(self, operation_id, *, expected_image=None):
        identifier = self.run(
            [
                "docker",
                "ps",
                "--all",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={self.deployment.project}",
                "--filter",
                f"name=^/{self.deployment.project}-migration-{operation_id}$",
                "--format",
                "{{.ID}}",
            ],
            "find interrupted migration",
        ).strip()
        if not identifier:
            return {"state": "not_found"}
        if not re.fullmatch(r"[0-9a-f]{64}", identifier):
            raise DeploymentError("migration container identity is unknown")
        state = parse_json(
            self.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{"status":{{json .State.Status}},'
                    '"exit_code":{{json .State.ExitCode}},'
                    '"image":{{json .Image}},"service":'
                    '{{json (index .Config.Labels "com.docker.compose.service")}}}',
                    identifier,
                ],
                "inspect interrupted migration",
            ),
            "inspect interrupted migration",
        )
        if not isinstance(state, dict) or state.get("service") != "migrate":
            raise DeploymentError("migration container identity is unknown")
        if expected_image is not None and state.get("image") != expected_image:
            raise DeploymentError("migration container image differs from candidate")
        if state.get("status") == "exited" and type(state.get("exit_code")) is int:
            return {
                "state": "completed" if state["exit_code"] == 0 else "failed",
                "exit_code": state["exit_code"],
            }
        return {
            "state": "running"
            if state.get("status") in {"running", "paused", "restarting"}
            else "unknown"
        }

    def reconcile(self, operation_id, *, resolution=None):
        try:
            if str(UUID(operation_id)) != operation_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError) as exc:
            raise DeploymentError(
                "reconciliation requires a canonical operation UUID"
            ) from exc
        report = self.inventory(allow_operations=True)
        record = report["operation"]
        if not record or record["id"] != operation_id:
            raise DeploymentError("operation does not match current journal")
        directory = self.deployment.state_dir / operation_id
        candidate_path = directory / "candidate.json"
        candidate = private_json(candidate_path) if candidate_path.exists() else None
        if candidate is not None:
            self.validate_manifest(candidate, operation_id)
        process = self.migration_process(
            operation_id,
            expected_image=candidate["images"]["backend"] if candidate else None,
        )
        pg = self.containers.get("postgres")
        available = bool(pg and pg["State"] == "running")
        locked = self.lock_held() if available else None
        ledger = self.ledger() if available else None
        result = {
            "operation": operation_id,
            "status": record["status"],
            "migration": process,
            "active_operations": len(self.active_operations),
            "database_available": available,
            "migration_lock_held": locked,
            "candidate_ledger_matches": ledger == candidate["migrations"]
            if candidate
            else None,
        }
        if resolution is None:
            return result  # No lock file, journal, readiness or runtime writes.
        if (
            self.active_operations
            or locked
            or not available
            or process["state"] in {"running", "unknown"}
        ):
            raise DeploymentError(
                "active or unknown database operation; reconciliation blocked"
            )
        if not candidate:
            raise DeploymentError(
                "candidate recovery artifact absent; follow manual recovery procedure"
            )
        # Validate the manifest with the same contract as a confirmed release,
        # without pretending it was confirmed or writing release.json.
        self.validate_manifest(candidate, operation_id)
        target = (
            candidate
            if resolution == "resume"
            else (
                self.read_release(candidate["previous"])
                if candidate.get("previous")
                else None
            )
        )
        if target is None:
            raise DeploymentError(
                "initial installation has no previous application to restore"
            )
        self.select(target, report)
        store = self.store_type(
            self.deployment.state_dir,
            identity=f"{report['daemon_id']}:{report['project']}",
        )
        with store.recovery(operation_id, resolution) as journal:
            report = self.inventory()
            self.start_recovery(target, report)
            store.stage(journal, "confirm")
            if resolution == "resume":
                self.promote(candidate)
                journal["status"] = "succeeded"
            else:
                atomic_json(
                    self.deployment.state_dir / "active.json", {"release": target["id"]}
                )
                journal["status"] = "reconciled"
        return {
            "operation": operation_id,
            "resolution": resolution,
            "revision": target["revision"],
            "verified": True,
        }


def runtime_service(original, runtime, config):
    """Preserve the actual pre-automation runtime, rather than new env-file values."""
    service = copy.deepcopy(original)
    for key in ("build", "depends_on", "profiles"):
        service.pop(key, None)
    service.update(
        {
            "image": runtime["image"],
            "environment": runtime["environment"],
            "command": runtime["command"],
            "entrypoint": runtime["entrypoint"],
        }
    )
    service["ports"] = []
    for port, bindings in (runtime.get("ports") or {}).items():
        target, protocol = port.split("/")
        by_published = {}
        for binding in bindings or []:
            by_published.setdefault(binding["HostPort"], set()).add(binding["HostIp"])
        for published, addresses in by_published.items():
            if addresses in ({""}, {"0.0.0.0", "::"}):
                service["ports"].append(
                    {
                        "target": int(target),
                        "published": published,
                        "protocol": protocol,
                    }
                )
                continue
            for address in sorted(addresses):
                service["ports"].append(
                    {
                        "target": int(target),
                        "published": published,
                        "protocol": protocol,
                        "host_ip": address,
                    }
                )
    if "mounts" in runtime:
        service["volumes"] = []
        for mount in runtime["mounts"]:
            kind = mount["Type"]
            if kind not in {"volume", "bind"}:
                raise DeploymentError(
                    "unsupported runtime mount; capture baseline manually"
                )
            source = mount["Name"] if kind == "volume" else mount["Source"]
            if kind == "volume":
                # Preserve physical volume identities, including additional volumes.
                config.setdefault("volumes", {}).setdefault(
                    source, {"name": source, "external": True}
                )
            service["volumes"].append(
                {
                    "type": kind,
                    "source": source,
                    "target": mount["Destination"],
                    "read_only": not mount["RW"],
                }
            )
    if "user" in runtime:
        service["user"] = runtime["user"] or ""
    if "healthcheck" in runtime:
        health = runtime["healthcheck"] or {}
        service["healthcheck"] = {"test": health.get("Test", ["NONE"])}
        for docker, compose in (
            ("Interval", "interval"),
            ("Timeout", "timeout"),
            ("StartPeriod", "start_period"),
            ("StartInterval", "start_interval"),
        ):
            if health.get(docker):
                service["healthcheck"][compose] = f"{health[docker]}ns"
        if health.get("Retries"):
            service["healthcheck"]["retries"] = health["Retries"]
    restart = runtime.get("restart", {})
    if restart:
        service["restart"] = restart["Name"] or "no"
        if restart["Name"] == "on-failure" and restart.get("MaximumRetryCount"):
            service["restart"] += f":{restart['MaximumRetryCount']}"
    return service
