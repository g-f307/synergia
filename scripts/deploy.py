"""Host-side deployment tools. Diagnose/precheck never write installation state."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from deploy_common import (  # noqa: E402
    DeploymentError,
    atomic_json,
    compose_values,
    parse_json,
)

from app.deployment_environment import validate_deployment_environment  # noqa: E402

PROJECT_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}")
SERVICES = ("config-check", "postgres", "migrate", "backend", "email-worker", "web")
VOLUMES = ("synergia-postgres", "synergia-application-data")
# Deliberately do not inherit COMPOSE_*, SYNERGIA_*, passwords or .env overrides.
HOST_VARIABLES = (
    "PATH",
    "HOME",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
    "DOCKER_TLS_VERIFY",
    "DOCKER_CERT_PATH",
    "XDG_RUNTIME_DIR",
    "SSH_AUTH_SOCK",
)


class CommandRunner:
    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self.environment = {
            name: os.environ[name] for name in HOST_VARIABLES if name in os.environ
        }
        self.environment["COMPOSE_DISABLE_ENV_FILE"] = "1"
        self.environment["GIT_OPTIONAL_LOCKS"] = "0"

    def run(self, args: Sequence[str], *, step: str, timeout: int = 60) -> str:
        try:
            result = subprocess.run(
                list(args),
                cwd=self.root,
                env=self.environment,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DeploymentError(
                f"{step}: timeout; inspect the operation before retrying"
            ) from exc
        except OSError as exc:
            raise DeploymentError(
                f"{step}: executable unavailable; check Git/Docker installation"
            ) from exc
        if result.returncode:
            # Compose stderr/config and process exceptions can contain credentials.
            raise DeploymentError(
                f"{step}: command failed (exit {result.returncode}); "
                "check tooling, permissions and external configuration locally"
            )
        return result.stdout


def external_path(path: Path, root: Path, *, configuration: bool = False) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(root.resolve()):
        raise DeploymentError(
            "configuration and deployment history must be outside Git"
        )
    if configuration:
        try:
            details = resolved.stat()
        except OSError as exc:
            raise DeploymentError("external configuration file is unavailable") from exc
        if not stat.S_ISREG(details.st_mode) or details.st_mode & 0o077:
            raise DeploymentError(
                "external configuration must be a private file (0600)"
            )
        if details.st_uid != os.getuid():
            raise DeploymentError("external configuration must belong to this operator")
    return resolved


class Deployment:
    def __init__(
        self,
        *,
        project: str,
        env_file: Path,
        state_dir: Path,
        runner: CommandRunner | None = None,
    ) -> None:
        if not PROJECT_NAME.fullmatch(project):
            raise DeploymentError("project must use 1-63 lowercase letters/digits/_/-")
        self.runner = runner or CommandRunner()
        self.project = project
        self.env_file = external_path(env_file, self.runner.root, configuration=True)
        self.state_dir = external_path(state_dir, self.runner.root)
        self.compose = [
            "docker",
            "compose",
            "--project-name",
            project,
            "--env-file",
            str(self.env_file),
            "--file",
            str(self.runner.root / "docker-compose.yml"),
        ]

    def command(self, *args: str, step: str) -> str:
        return self.runner.run([*self.compose, *args], step=step)

    def _configuration_report(self) -> dict:
        revision = self.runner.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"], step="source revision"
        ).strip()
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise DeploymentError("source revision: expected a full Git commit")
        changes = self.runner.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            step="source worktree",
        )
        if changes.strip():
            raise DeploymentError("source worktree is dirty; commit or isolate changes")
        self.command("version", "--short", step="Docker Compose availability")
        daemon = self.runner.run(
            ["docker", "info", "--format", "{{json .ID}}"], step="Docker daemon"
        )
        daemon_id = parse_json(daemon, "Docker daemon")
        if not isinstance(daemon_id, str) or not re.fullmatch(
            r"[A-Za-z0-9:._-]{1,128}", daemon_id
        ):
            raise DeploymentError("Docker daemon: missing installation identity")
        config = compose_values(
            parse_json(
                self.command(
                    "config", "--format", "json", step="Compose configuration"
                ),
                "Compose configuration",
            )
        )
        try:
            services = config["services"]
            if set(services) - set(SERVICES) or not all(
                name in services for name in ("postgres", "backend", "web", "migrate")
            ):
                raise DeploymentError(
                    "unexpected Compose services; review deployment contract"
                )
            environment = services["backend"]["environment"]
            selected = validate_deployment_environment(environment)
            if not environment.get("PGPASSWORD", "").strip():
                raise DeploymentError("POSTGRES_PASSWORD must be explicitly configured")
            if (
                services["postgres"]["environment"]["POSTGRES_PASSWORD"]
                != environment["PGPASSWORD"]
            ):
                raise DeploymentError("PostgreSQL and backend passwords must agree")
            volumes = {key: config["volumes"][key]["name"] for key in VOLUMES}
            if any(volumes[key] != f"{self.project}_{key}" for key in VOLUMES):
                raise DeploymentError(
                    "unexpected volume identity; review project selection"
                )
            if environment.get("MIGRATION_BASELINE_THROUGH", "").strip():
                raise DeploymentError(
                    "legacy migration adoption requires a separate controlled procedure"
                )
        except (KeyError, TypeError, AttributeError) as exc:
            raise DeploymentError(
                "Compose configuration: unsupported service contract"
            ) from exc
        except ValueError as exc:
            # Third-party URL parsers may put supplied values in ValueError text.
            # Only report a recognized field name, never the original exception.
            field = str(exc).partition(" ")[0]
            if not re.fullmatch(
                r"(?:SYNERGIA_[A-Z_]+|AUTH_[A-Z_]+|PGPASSWORD|RATE_LIMIT_KEY_SECRET)",
                field,
            ):
                field = "environment profile"
            raise DeploymentError(
                f"deployment configuration invalid: {field}; "
                "check the documented environment requirements"
            ) from exc
        self.config = config
        report = {
            "project": self.project,
            "revision": revision,
            "environment": selected,
            "daemon_id": daemon_id,
            "volumes": volumes,
        }
        report["operation"] = OperationStore(
            self.state_dir, identity=f"{daemon_id}:{self.project}"
        ).read()
        return report

    def diagnose(self) -> dict:
        report = self._configuration_report()
        # docker inspect/ps do not start services, create volumes or invoke health.
        raw = self.runner.run(
            [
                "docker",
                "ps",
                "--all",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={self.project}",
                "--format",
                '{"ID":{{json .ID}},"Service":'
                '{{json (.Label "com.docker.compose.service")}},'
                '"State":{{json .State}},"OneOff":'
                '{{json (.Label "com.docker.compose.oneoff")}}}',
            ],
            step="installation inventory",
        ).strip()
        if not raw:
            containers = []
        elif raw.startswith("["):
            containers = parse_json(raw, "installation inventory")
        else:
            containers = [
                parse_json(line, "installation inventory") for line in raw.splitlines()
            ]
        if not isinstance(containers, list) or not all(
            isinstance(item, dict) and item.get("Service") in SERVICES
            for item in containers
        ):
            raise DeploymentError("installation inventory: unsupported response")
        self.containers = containers
        # Do not echo arbitrary container names, commands, labels or logs.
        report["services"] = [
            {"service": item["Service"], "running": item.get("State") == "running"}
            for item in containers
        ]
        available = self.runner.run(
            ["docker", "volume", "ls", "--format", "{{.Name}}"],
            step="persistent volume inventory",
        ).splitlines()
        report["volumes_present"] = {
            key: name in available for key, name in report["volumes"].items()
        }
        expected_mounts = {
            "postgres": (
                "/var/lib/postgresql/data",
                report["volumes"]["synergia-postgres"],
            ),
            "backend": (
                "/var/lib/synergia",
                report["volumes"]["synergia-application-data"],
            ),
        }
        for item in containers:
            service = item["Service"]
            if service not in expected_mounts:
                continue
            container_id = item.get("ID", "")
            if not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
                raise DeploymentError("installation inventory: invalid container ID")
            mounts = parse_json(
                self.runner.run(
                    ["docker", "inspect", "--format", "{{json .Mounts}}", container_id],
                    step="persistent mount identity",
                ),
                "persistent mount identity",
            )
            destination, volume_name = expected_mounts[service]
            if not isinstance(mounts, list) or not any(
                isinstance(mount, dict)
                and mount.get("Type") == "volume"
                and mount.get("Destination") == destination
                and mount.get("Name") == volume_name
                for mount in mounts
            ):
                raise DeploymentError(
                    "existing container uses unexpected persistent storage; "
                    "reconcile the project before updating"
                )
        images = self.runner.run(
            ["docker", "image", "ls", "--no-trunc", "--format", "{{json .}}"],
            step="image inventory",
        )
        inventory = [
            parse_json(line, "image inventory") for line in images.splitlines()
        ]
        if not all(isinstance(item, dict) for item in inventory):
            raise DeploymentError("image inventory: unsupported response")
        report["images_present"] = {
            service: any(
                f"{item.get('Repository')}:{item.get('Tag')}"
                == self.config["services"][service]["image"]
                for item in inventory
            )
            for service in ("backend", "web")
        }
        return report

    def precheck(self) -> dict:
        return self.diagnose()


class OperationStore:
    """Private atomic journal; exclusive flock survives CLI crashes safely.

    Only fixed stage names and status codes are persisted, never command output,
    exception strings, environment values or credentials.
    """

    def __init__(self, directory: Path, *, identity: str) -> None:
        self.directory = directory
        self.path = directory / "operation.json"
        self.identity = hashlib.sha256(identity.encode()).hexdigest()

    def read(self) -> dict | None:
        if not self.directory.exists():
            return None
        details = self.directory.stat()
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_mode & 0o077
        ):
            raise DeploymentError(
                "deployment history must be private (0700) and operator-owned"
            )
        if not self.path.exists():
            return None
        try:
            if self.path.is_symlink() or self.path.stat().st_mode & 0o077:
                raise ValueError
            record = json.loads(self.path.read_text())
            if set(record) != {
                "id",
                "installation",
                "action",
                "stage",
                "status",
                "updated_at",
            }:
                raise ValueError
            if record["installation"] != self.identity:
                raise ValueError
            if record["action"] not in {"apply", "rollback"}:
                raise ValueError
            if record["stage"] not in {
                "precheck",
                "build",
                "maintenance",
                "migrate",
                "start",
                "verify",
                "confirm",
            }:
                raise ValueError
            if record["status"] not in {"running", "succeeded", "failed", "uncertain"}:
                raise ValueError
            UUID(record["id"])
            datetime.fromisoformat(record["updated_at"])
            return record
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise DeploymentError(
                "deployment journal invalid; reconcile before retrying"
            ) from exc

    def write(self, record: Mapping) -> None:
        atomic_json(self.path, record)

    def stage(self, record: dict, name: str) -> None:
        record["stage"] = name
        record["updated_at"] = datetime.now(UTC).isoformat()
        self.write(record)
        print(f"deployment stage: {name}", file=sys.stderr, flush=True)

    @contextmanager
    def operation(self, action: str) -> Iterator[dict]:
        if action not in {"apply", "rollback"}:
            raise DeploymentError("unsupported deployment operation")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.read()  # Check ownership/permissions before opening anything writable.
        # Same Docker daemon/project shares a lock even with different state dirs.
        lock_dir = Path("/tmp") / f"synergia-deploy-{self.identity}"
        lock_dir.mkdir(mode=0o700, exist_ok=True)
        details = lock_dir.lstat()
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_mode & 0o077
        ):
            raise DeploymentError(
                "deployment lock directory must be private and operator-owned"
            )
        lock_fd = os.open(
            lock_dir / f"{self.identity}.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
        )
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DeploymentError(
                    "another deployment is running; wait and diagnose"
                ) from exc
            previous = self.read()
            if previous and previous["status"] in {"running", "uncertain"}:
                raise DeploymentError(
                    "previous operation is unresolved; "
                    "reconcile containers and migrations"
                )
            record = {
                "id": str(uuid4()),
                "installation": self.identity,
                "action": action,
                "stage": "precheck",
                "status": "running",
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self.write(record)
            try:
                yield record
            except BaseException:
                # A failed client does not prove that Docker stopped the operation.
                if record["status"] != "failed":
                    record["status"] = "uncertain"
                raise
            else:
                record["status"] = "succeeded"
            finally:
                record["updated_at"] = datetime.now(UTC).isoformat()
                self.write(record)
        finally:
            os.close(lock_fd)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("diagnose", "precheck", "apply", "verify"))
    parser.add_argument(
        "--revision", help="commit/tag already checked out; required by apply"
    )
    parser.add_argument(
        "--initialize", action="store_true", help="allow an empty installation"
    )
    parser.add_argument(
        "--project", required=True, help="existing stable Compose project name"
    )
    parser.add_argument(
        "--env-file", required=True, type=Path, help="private external env file"
    )
    parser.add_argument(
        "--state-dir",
        required=True,
        type=Path,
        help="private external history directory",
    )
    args = parser.parse_args(argv)
    try:
        deployment = Deployment(
            project=args.project, env_file=args.env_file, state_dir=args.state_dir
        )
        if args.action in {"apply", "verify"}:
            from deploy_flow import ApplyWorkflow

            flow = ApplyWorkflow(deployment, OperationStore)
            if args.action == "apply":
                if not args.revision:
                    raise DeploymentError(
                        "apply requires --revision with the chosen commit/tag"
                    )
                report = flow.apply(args.revision, initialize=args.initialize)
            else:
                report = flow.verify_active()
        else:
            if args.revision or args.initialize:
                raise DeploymentError("revision/initialize are only used by apply")
            report = getattr(deployment, args.action)()
    except (DeploymentError, OSError) as exc:
        message = (
            str(exc)
            if isinstance(exc, DeploymentError)
            else "cannot access deployment files"
        )
        print(f"deployment blocked: {message}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
