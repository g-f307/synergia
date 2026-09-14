from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_ROOT = ROOT / "database" / "migrations"
FORMAT_VERSION = "1.0"
BACKUP_TEMP_FORMAT_VERSION = "1.0"
BACKUP_TEMP_MAX_AGE = timedelta(hours=24)
BACKUP_TEMP_MARKER = ".synergia-backup-owner.json"
SAFE_ACTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
SAFE_STEM = re.compile(r"^[0-9a-f]{48}$")
ALLOWED_PURGE_DATASETS = frozenset({"quarantine", "security_transient"})
PIPELINE_ARTIFACTS = (
    "validation-report.json",
    "pipeline-summary.json",
    "normalized-data.json",
)
TERMINAL_EXECUTION_STATES = frozenset(
    {
        "validation_failed",
        "completed",
        "completed_with_errors",
        "failed",
        "duplicate",
        "cancelled",
    }
)
PROTECTED_PURGE_DATASETS = frozenset(
    {
        "audit",
        "approvals",
        "accepted_uploads",
        "avatars",
        "notifications",
        "reports",
    }
)


class DataOperationError(RuntimeError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class DataOperationConfig:
    database_url: str
    import_storage_root: Path
    avatar_storage_root: Path
    actor_identifier: str

    @classmethod
    def from_env(cls) -> DataOperationConfig:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise DataOperationError(
                "database_not_configured", "DATABASE_URL is required"
            )
        actor = os.getenv("DATA_OPERATIONS_ACTOR", "synergia-operator").strip()
        if not SAFE_ACTOR.fullmatch(actor):
            raise DataOperationError(
                "actor_invalid", "DATA_OPERATIONS_ACTOR is invalid"
            )
        imports = Path(
            os.getenv("IMPORT_STORAGE_DIR", str(ROOT / "data" / "imports"))
        ).resolve()
        avatars = Path(
            os.getenv("PROFILE_AVATAR_STORAGE_ROOT", str(ROOT / ".data" / "avatars"))
        ).resolve()
        if (
            imports == avatars
            or imports in avatars.parents
            or avatars in imports.parents
        ):
            raise DataOperationError(
                "storage_roots_overlap", "Storage roots must not overlap"
            )
        return cls(database_url, imports, avatars, actor)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _migration_inventory() -> list[dict[str, Any]]:
    return [
        {"name": path.name, "sha256": _sha256(path), "size_bytes": path.stat().st_size}
        for path in sorted(MIGRATIONS_ROOT.glob("*.sql"))
    ]


def _safe_target(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    unsafe_part = any(part in {"", ".", ".."} for part in pure.parts)
    if pure.is_absolute() or not pure.parts or unsafe_part:
        raise DataOperationError("storage_key_invalid", "Unsafe storage key")
    resolved_root = root.resolve()
    current = resolved_root
    for part in pure.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise DataOperationError(
                "storage_key_invalid", "Symbolic storage path is forbidden"
            )
    return resolved_root.joinpath(*pure.parts)


def _database_command(database_url: str) -> tuple[str, dict[str, str]]:
    parameters = conninfo_to_dict(database_url)
    password = parameters.pop("password", None)
    allowed = {
        key: value
        for key, value in parameters.items()
        if key
        in {
            "host",
            "hostaddr",
            "port",
            "dbname",
            "user",
            "sslmode",
            "sslrootcert",
            "sslcert",
            "sslkey",
        }
    }
    environment = os.environ.copy()
    if password:
        environment["PGPASSWORD"] = password
    return make_conninfo(**allowed), environment


def _postgres_tool_command(
    executable: str, database_url: str, arguments: list[str]
) -> tuple[list[str], dict[str, str]]:
    connection, environment = _database_command(database_url)
    if shutil.which(executable):
        return [executable, *arguments, "--dbname", connection], environment
    if shutil.which("docker") is None:
        raise DataOperationError(
            "postgres_tool_unavailable", f"{executable} or Docker is required"
        )
    parameters = conninfo_to_dict(database_url)
    host = parameters.get("host", "")
    port = parameters.get("port", "5432")
    if host not in {"", "localhost", "127.0.0.1", "postgres"} or port != "5432":
        raise DataOperationError(
            "postgres_tool_unavailable",
            f"Native {executable} is required for a non-Compose database",
        )
    database = parameters.get("dbname", os.getenv("PGDATABASE", "synergia"))
    user = parameters.get("user", os.getenv("PGUSER", "synergia"))
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        f'PGPASSWORD="$POSTGRES_PASSWORD" exec {executable} "$@"',
        executable,
        *arguments,
        "--username",
        user,
        "--dbname",
        database,
    ]
    return command, environment


def _dump_database(database_url: str, snapshot: str, output: Path) -> None:
    command, environment = _postgres_tool_command(
        "pg_dump",
        database_url,
        [
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--schema=synergia",
            f"--snapshot={snapshot}",
        ],
    )
    with output.open("xb") as stream:
        completed = subprocess.run(
            command,
            check=False,
            stdout=stream,
            stderr=subprocess.PIPE,
            env=environment,
        )
    if completed.returncode:
        output.unlink(missing_ok=True)
        raise DataOperationError(
            "postgres_tool_failed", "pg_dump failed with a non-zero status"
        )


def _restore_database(database_url: str, dump: Path) -> None:
    command, environment = _postgres_tool_command(
        "pg_restore",
        database_url,
        [
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-privileges",
        ],
    )
    with dump.open("rb") as stream:
        completed = subprocess.run(
            command,
            check=False,
            stdin=stream,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=environment,
        )
    if completed.returncode:
        raise DataOperationError(
            "postgres_tool_failed", "pg_restore failed with a non-zero status"
        )


def record_operation_event(
    database_url: str,
    *,
    operation: str,
    outcome: str,
    dataset: str,
    actor_identifier: str,
    correlation_id: UUID,
    reason_code: str | None = None,
    record_count: int | None = None,
    artifact_count: int | None = None,
    duration_ms: int | None = None,
) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO synergia.data_operation_events (
                operation, outcome, dataset, actor_identifier, correlation_id,
                reason_code, record_count, artifact_count, duration_ms
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                operation,
                outcome,
                dataset,
                actor_identifier,
                correlation_id,
                reason_code,
                record_count,
                artifact_count,
                duration_ms,
            ),
        )


def _record_failure(
    config: DataOperationConfig,
    operation: str,
    correlation_id: UUID,
    reason_code: str,
    started_at: float,
    dataset: str = "combined",
) -> None:
    try:
        record_operation_event(
            config.database_url,
            operation=operation,
            outcome="failed",
            dataset=dataset,
            actor_identifier=config.actor_identifier,
            correlation_id=correlation_id,
            reason_code=reason_code,
            duration_ms=round((perf_counter() - started_at) * 1000),
        )
    except psycopg.Error:
        pass


def _table_counts(connection: psycopg.Connection[Any]) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'synergia' ORDER BY tablename
        """
    ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        name = row["tablename"] if isinstance(row, dict) else row[0]
        count_row = connection.execute(
            sql.SQL("SELECT count(*) FROM synergia.{}").format(sql.Identifier(name))
        ).fetchone()
        counts[name] = (
            count_row["count"] if isinstance(count_row, dict) else count_row[0]
        )
    return counts


def _file_inventory(
    connection: psycopg.Connection[Any], config: DataOperationConfig
) -> list[dict[str, Any]]:
    files: dict[tuple[str, str], dict[str, Any]] = {}
    sources = connection.execute(
        """
        SELECT source.storage_key, source.content_hash, source.size_bytes,
               execution.status
        FROM synergia.source_files source
        JOIN synergia.executions execution ON execution.id = source.execution_id
        WHERE source.storage_key IS NOT NULL ORDER BY source.storage_key
        """
    ).fetchall()
    for storage_key, digest, size, status in sources:
        if PurePosixPath(storage_key).parts[:1] != ("accepted",):
            raise DataOperationError(
                "storage_key_invalid", "Accepted upload key is outside its area"
            )
        files[("accepted_upload", storage_key)] = {
            "kind": "accepted_upload",
            "relative_path": storage_key,
            "sha256": digest,
            "size_bytes": size,
        }
        if status in TERMINAL_EXECUTION_STATES:
            for name in PIPELINE_ARTIFACTS:
                relative = str(PurePosixPath(storage_key).parent / name)
                path = _safe_target(config.import_storage_root, relative)
                if path.is_file() and not path.is_symlink():
                    files[("derived_artifact", relative)] = {
                        "kind": "derived_artifact",
                        "relative_path": relative,
                        "sha256": _sha256(path),
                        "size_bytes": path.stat().st_size,
                    }
    avatars = connection.execute(
        """
        SELECT avatar_storage_key, avatar_sha256, avatar_size_bytes
        FROM synergia.identity_users
        WHERE avatar_storage_key IS NOT NULL ORDER BY avatar_storage_key
        """
    ).fetchall()
    for storage_key, digest, size in avatars:
        if not re.fullmatch(r"[0-9a-f]{48}\.(?:png|jpe?g|webp)", storage_key):
            raise DataOperationError(
                "storage_key_invalid", "Avatar key has an invalid format"
            )
        relative = f"{storage_key[:2]}/{storage_key}"
        files[("avatar", relative)] = {
            "kind": "avatar",
            "relative_path": relative,
            "sha256": digest,
            "size_bytes": size,
        }
    return [files[key] for key in sorted(files)]


def _source_path(config: DataOperationConfig, entry: dict[str, Any]) -> Path:
    root = (
        config.import_storage_root
        if entry["kind"] in {"accepted_upload", "derived_artifact"}
        else config.avatar_storage_root
    )
    return _safe_target(root, entry["relative_path"])


def _archive_member_name(entry: dict[str, Any]) -> str:
    kind = entry["kind"]
    relative = entry["relative_path"]
    pure = PurePosixPath(relative)
    unsafe_part = any(part in {"", ".", ".."} for part in pure.parts)
    if pure.is_absolute() or not pure.parts or unsafe_part:
        raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
    if kind == "accepted_upload":
        valid = pure.parts[0] == "accepted"
        prefix = "imports"
    elif kind == "derived_artifact":
        valid = pure.parts[0] == "accepted" and pure.name in PIPELINE_ARTIFACTS
        prefix = "imports"
    else:
        match = re.fullmatch(
            r"([0-9a-f]{2})/([0-9a-f]{48}\.(?:png|jpe?g|webp))", relative
        )
        valid = match is not None and match[2].startswith(match[1])
        prefix = "avatars"
    if not valid:
        raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
    return f"{prefix}/{relative}"


def _verify_source_file(path: Path, entry: dict[str, Any]) -> None:
    if not path.is_file() or path.is_symlink():
        raise DataOperationError(
            "referenced_file_missing", "Referenced file is missing"
        )
    expected_size = entry["size_bytes"]
    size_mismatch = expected_size is not None and path.stat().st_size != expected_size
    if size_mismatch or _sha256(path) != entry["sha256"]:
        raise DataOperationError(
            "referenced_file_corrupted", "Referenced file integrity failed"
        )


def _write_storage_archive(
    archive_path: Path,
    config: DataOperationConfig,
    files: list[dict[str, Any]],
) -> None:
    with tarfile.open(archive_path, "w:gz") as archive:
        for entry in files:
            source = _source_path(config, entry)
            _verify_source_file(source, entry)
            archive.add(
                source,
                arcname=_archive_member_name(entry),
                recursive=False,
                filter=lambda info: _safe_tar_info(info),
            )


def _safe_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o600
    return info


def _backup_destination_key(destination: Path) -> str:
    return hashlib.sha256(str(destination).encode("utf-8")).hexdigest()


def _backup_temporary_prefix(destination: Path) -> str:
    return f".synergia-backup-{_backup_destination_key(destination)[:16]}-"


def _write_backup_temporary_marker(
    temporary: Path, destination: Path, correlation_id: UUID
) -> None:
    marker = {
        "format_version": BACKUP_TEMP_FORMAT_VERSION,
        "destination_key": _backup_destination_key(destination),
        "correlation_id": str(correlation_id),
        "created_at": datetime.now(UTC).isoformat(),
    }
    marker_path = temporary / BACKUP_TEMP_MARKER
    marker_path.write_text(
        json.dumps(marker, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    marker_path.chmod(0o600)


def _owned_stale_backup_temporary(
    candidate: Path,
    destination: Path,
    *,
    now: datetime,
) -> bool:
    if candidate.is_symlink() or not candidate.is_dir():
        return False
    marker_path = candidate / BACKUP_TEMP_MARKER
    try:
        if marker_path.is_symlink() or not marker_path.is_file():
            return False
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        created_at = datetime.fromisoformat(marker["created_at"])
        correlation_id = UUID(marker["correlation_id"])
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    if created_at.tzinfo is None:
        return False
    return (
        marker.get("format_version") == BACKUP_TEMP_FORMAT_VERSION
        and marker.get("destination_key") == _backup_destination_key(destination)
        and str(correlation_id) == marker["correlation_id"]
        and candidate.name
        == f"{_backup_temporary_prefix(destination)}{correlation_id}"
        and now - created_at.astimezone(UTC) >= BACKUP_TEMP_MAX_AGE
    )


def _cleanup_stale_backup_temporaries(
    destination: Path, *, now: datetime | None = None
) -> int:
    current_time = now or datetime.now(UTC)
    prefix = _backup_temporary_prefix(destination)
    removed = 0
    for candidate in destination.parent.glob(f"{prefix}*"):
        if _owned_stale_backup_temporary(
            candidate,
            destination,
            now=current_time,
        ):
            shutil.rmtree(candidate)
            removed += 1
    return removed


def create_backup(config: DataOperationConfig, destination: Path) -> dict[str, Any]:
    destination = destination.resolve()
    if destination.is_relative_to(ROOT.resolve()):
        raise DataOperationError(
            "destination_unsafe", "Backup destination must be outside the repository"
        )
    inside_imports = destination.is_relative_to(config.import_storage_root)
    inside_avatars = destination.is_relative_to(config.avatar_storage_root)
    if inside_imports or inside_avatars:
        raise DataOperationError(
            "destination_unsafe",
            "Backup destination must be outside application storage",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_backup_temporaries(destination)
    if destination.exists():
        return _finalize_published_backup(config, destination)
    correlation_id = uuid4()
    temporary = destination.parent / (
        f"{_backup_temporary_prefix(destination)}{correlation_id}"
    )
    temporary.mkdir(mode=0o700)
    _write_backup_temporary_marker(temporary, destination, correlation_id)
    started_at = perf_counter()
    try:
        record_operation_event(
            config.database_url,
            operation="backup",
            outcome="started",
            dataset="combined",
            actor_identifier=config.actor_identifier,
            correlation_id=correlation_id,
        )
        dump_path = temporary / "database.dump"
        archive_path = temporary / "storage.tar.gz"
        with psycopg.connect(config.database_url) as connection:
            connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            snapshot = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
            counts = _table_counts(connection)
            files = _file_inventory(connection, config)
            for entry in files:
                _verify_source_file(_source_path(config, entry), entry)
            _dump_database(config.database_url, snapshot, dump_path)
            _write_storage_archive(archive_path, config, files)
            for entry in files:
                _verify_source_file(_source_path(config, entry), entry)
        duration = round((perf_counter() - started_at) * 1000)
        manifest = {
            "format_version": FORMAT_VERSION,
            "bundle_id": str(uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "operation": {
                "correlation_id": str(correlation_id),
                "actor_identifier": config.actor_identifier,
                "record_count": sum(counts.values()),
                "artifact_count": len(files),
                "duration_ms": duration,
            },
            "database": {
                "dump_sha256": _sha256(dump_path),
                "table_counts": counts,
            },
            "storage": {
                "archive_sha256": _sha256(archive_path),
                "files": files,
                "excluded": ["quarantine", "email_capture", "technical_logs"],
            },
            "migrations": _migration_inventory(),
        }
        manifest_path = temporary / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        for path in temporary.iterdir():
            path.chmod(0o600)
        temporary.replace(destination)
        return _finalize_published_backup(config, destination)
    except (DataOperationError, OSError, psycopg.Error) as exc:
        reason = getattr(exc, "reason_code", "backup_failed")
        _record_failure(config, "backup", correlation_id, reason, started_at)
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def load_manifest(bundle: Path) -> dict[str, Any]:
    manifest_path = bundle / "manifest.json"
    try:
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise OSError
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise DataOperationError(
            "manifest_invalid", "Backup manifest is invalid"
        ) from exc
    if not isinstance(manifest, dict):
        raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
    if manifest.get("format_version") != FORMAT_VERSION:
        raise DataOperationError("manifest_version_unsupported", "Unsupported manifest")

    operation = manifest.get("operation")
    database = manifest.get("database")
    storage = manifest.get("storage")
    migrations = manifest.get("migrations")
    if not isinstance(database, dict) or not isinstance(storage, dict):
        raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
    if operation is not None:
        if not isinstance(operation, dict):
            raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
        try:
            operation_correlation_id = UUID(
                str(operation.get("correlation_id", ""))
            )
        except (TypeError, ValueError) as exc:
            raise DataOperationError(
                "manifest_invalid", "Backup manifest is invalid"
            ) from exc
        operation_numbers = (
            operation.get("record_count"),
            operation.get("artifact_count"),
            operation.get("duration_ms"),
        )
        if (
            str(operation_correlation_id) != operation.get("correlation_id")
            or not SAFE_ACTOR.fullmatch(str(operation.get("actor_identifier", "")))
            or any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in operation_numbers
            )
        ):
            raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(database.get("dump_sha256", ""))):
        raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
    table_counts = database.get("table_counts")
    if not isinstance(table_counts, dict) or not all(
        isinstance(name, str)
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
        for name, count in table_counts.items()
    ):
        raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(storage.get("archive_sha256", ""))):
        raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
    if not isinstance(storage.get("files"), list) or not isinstance(migrations, list):
        raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
    seen_files: set[str] = set()
    for entry in storage["files"]:
        if not isinstance(entry, dict) or entry.get("kind") not in {
            "accepted_upload",
            "derived_artifact",
            "avatar",
        }:
            raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
        relative_path = entry.get("relative_path")
        if not isinstance(relative_path, str):
            raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
        member_name = _archive_member_name(entry)
        if member_name in seen_files:
            raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
        seen_files.add(member_name)
        if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))):
            raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
        size = entry.get("size_bytes")
        if size is not None and (
            not isinstance(size, int) or isinstance(size, bool) or size < 0
        ):
            raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
    for entry in migrations:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("name"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", "")))
            or not isinstance(entry.get("size_bytes"), int)
            or isinstance(entry.get("size_bytes"), bool)
            or entry["size_bytes"] < 0
        ):
            raise DataOperationError("manifest_invalid", "Backup manifest is invalid")
    return manifest


def _record_published_backup_success(
    connection: psycopg.Connection[Any],
    operation: dict[str, Any],
    correlation_id: UUID,
) -> None:
    connection.execute(
        """
        INSERT INTO synergia.data_operation_events (
            operation, outcome, dataset, actor_identifier, correlation_id,
            record_count, artifact_count, duration_ms
        ) VALUES ('backup', 'succeeded', 'combined', %s, %s, %s, %s, %s)
        """,
        (
            operation["actor_identifier"],
            correlation_id,
            operation["record_count"],
            operation["artifact_count"],
            operation["duration_ms"],
        ),
    )


def _finalize_published_backup(
    config: DataOperationConfig, destination: Path
) -> dict[str, Any]:
    manifest = load_manifest(destination)
    _verify_bundle(destination, manifest)
    operation = manifest.get("operation")
    if not isinstance(operation, dict):
        raise DataOperationError(
            "destination_not_empty", "Backup destination already exists"
        )
    correlation_id = UUID(operation["correlation_id"])
    with psycopg.connect(config.database_url, row_factory=dict_row) as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"synergia:backup:{correlation_id}",),
        )
        events = connection.execute(
            """
            SELECT outcome, actor_identifier
            FROM synergia.data_operation_events
            WHERE operation = 'backup' AND dataset = 'combined'
              AND correlation_id = %s
            """,
            (correlation_id,),
        ).fetchall()
        started = next(
            (event for event in events if event["outcome"] == "started"), None
        )
        if started is None:
            raise DataOperationError(
                "destination_not_empty", "Backup destination already exists"
            )
        if started["actor_identifier"] != operation["actor_identifier"]:
            raise DataOperationError(
                "manifest_invalid", "Published backup operation is inconsistent"
            )
        if not any(event["outcome"] == "succeeded" for event in events):
            _record_published_backup_success(connection, operation, correlation_id)
    (destination / BACKUP_TEMP_MARKER).unlink(missing_ok=True)
    return {
        "operation": "backup",
        "outcome": "succeeded",
        "record_count": operation["record_count"],
        "artifact_count": operation["artifact_count"],
        "duration_ms": operation["duration_ms"],
        "correlation_id": str(correlation_id),
    }


def _verify_bundle(bundle: Path, manifest: dict[str, Any]) -> None:
    dump_path = bundle / "database.dump"
    archive_path = bundle / "storage.tar.gz"
    if (
        not dump_path.is_file()
        or dump_path.is_symlink()
        or _sha256(dump_path) != manifest["database"]["dump_sha256"]
    ):
        raise DataOperationError(
            "database_dump_corrupted", "Database dump integrity failed"
        )
    if (
        not archive_path.is_file()
        or archive_path.is_symlink()
        or _sha256(archive_path) != manifest["storage"]["archive_sha256"]
    ):
        raise DataOperationError(
            "storage_archive_corrupted", "Storage archive integrity failed"
        )
    if manifest["migrations"] != _migration_inventory():
        raise DataOperationError(
            "migration_mismatch", "Migration inventory does not match"
        )


def _extract_storage(bundle: Path, staging: Path, manifest: dict[str, Any]) -> None:
    expected = {
        _archive_member_name(entry): entry for entry in manifest["storage"]["files"]
    }
    try:
        with tarfile.open(bundle / "storage.tar.gz", "r:gz") as archive:
            members = archive.getmembers()
            names = {member.name for member in members}
            if (
                names != set(expected)
                or len(names) != len(members)
                or any(not member.isfile() for member in members)
            ):
                raise DataOperationError(
                    "storage_archive_invalid", "Archive members differ"
                )
            for member in members:
                target = _safe_target(staging, member.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise DataOperationError(
                        "storage_archive_invalid", "Archive member failed"
                    )
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                entry = expected[member.name]
                _verify_source_file(target, entry)
    except tarfile.TarError as exc:
        raise DataOperationError(
            "storage_archive_invalid", "Storage archive is invalid"
        ) from exc


def _storage_is_empty(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_dir() or path.is_symlink():
        raise DataOperationError(
            "target_storage_invalid", "Target storage must be a regular directory"
        )
    return not any(path.iterdir())


def _database_is_empty(database_url: str) -> bool:
    with psycopg.connect(database_url) as connection:
        return connection.execute(
            "SELECT to_regnamespace('synergia') IS NULL"
        ).fetchone()[0]


def _install_staged_storage(staging: Path, config: DataOperationConfig) -> None:
    for name, target in (
        ("imports", config.import_storage_root),
        ("avatars", config.avatar_storage_root),
    ):
        source = staging / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            source.replace(target)
        else:
            target.mkdir(parents=True, exist_ok=True)


def _drop_restored_schema(database_url: str) -> None:
    try:
        with psycopg.connect(database_url) as connection:
            connection.execute("DROP SCHEMA IF EXISTS synergia CASCADE")
    except psycopg.Error:
        pass


def restore_backup(config: DataOperationConfig, bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    manifest = load_manifest(bundle)
    _verify_bundle(bundle, manifest)
    if not _database_is_empty(config.database_url):
        raise DataOperationError(
            "target_database_not_empty", "Target database is not empty"
        )
    if not _storage_is_empty(config.import_storage_root) or not _storage_is_empty(
        config.avatar_storage_root
    ):
        raise DataOperationError(
            "target_storage_not_empty", "Target storage is not empty"
        )

    staging = Path(tempfile.mkdtemp(prefix="synergia-restore-"))
    correlation_id = uuid4()
    started_at = perf_counter()
    restored_database = False
    try:
        _extract_storage(bundle, staging, manifest)
        _restore_database(config.database_url, bundle / "database.dump")
        restored_database = True
        _install_staged_storage(staging, config)
        verify_result = verify_restoration(config, bundle, record_event=False)
        duration = round((perf_counter() - started_at) * 1000)
        record_operation_event(
            config.database_url,
            operation="restore",
            outcome="succeeded",
            dataset="combined",
            actor_identifier=config.actor_identifier,
            correlation_id=correlation_id,
            record_count=verify_result["record_count"],
            artifact_count=verify_result["artifact_count"],
            duration_ms=duration,
        )
        return {
            "operation": "restore",
            "outcome": "succeeded",
            "record_count": verify_result["record_count"],
            "artifact_count": verify_result["artifact_count"],
            "duration_ms": duration,
            "correlation_id": str(correlation_id),
        }
    except (DataOperationError, OSError, psycopg.Error):
        if restored_database:
            _drop_restored_schema(config.database_url)
        for target in (config.import_storage_root, config.avatar_storage_root):
            if target.exists() and target.is_dir():
                shutil.rmtree(target)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def verify_restoration(
    config: DataOperationConfig,
    bundle: Path,
    *,
    record_event: bool = True,
) -> dict[str, Any]:
    started_at = perf_counter()
    correlation_id = uuid4()
    manifest = load_manifest(bundle.resolve())
    try:
        _verify_bundle(bundle.resolve(), manifest)
        with psycopg.connect(config.database_url, row_factory=dict_row) as connection:
            counts = _table_counts(connection)
            expected_counts = manifest["database"]["table_counts"]
            for table, expected in expected_counts.items():
                actual = counts.get(table)
                if table == "data_operation_events":
                    if actual is None or actual < expected:
                        raise DataOperationError(
                            "record_count_mismatch", "Restored record counts differ"
                        )
                elif actual != expected:
                    raise DataOperationError(
                        "record_count_mismatch", "Restored record counts differ"
                    )
            invalid_constraints = connection.execute(
                """
                SELECT count(*) AS total FROM pg_constraint
                WHERE connamespace = 'synergia'::regnamespace
                  AND contype = 'f' AND NOT convalidated
                """
            ).fetchone()["total"]
            if invalid_constraints:
                raise DataOperationError(
                    "referential_integrity_failed", "Foreign keys are not validated"
                )
            artifacts = connection.execute(
                "SELECT content, content_hash FROM synergia.report_artifacts"
            ).fetchall()
            for artifact in artifacts:
                digest = hashlib.sha256(
                    json.dumps(
                        artifact["content"],
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ).encode()
                ).hexdigest()
                if digest != artifact["content_hash"]:
                    raise DataOperationError(
                        "report_hash_mismatch", "Report artifact integrity failed"
                    )
        for entry in manifest["storage"]["files"]:
            _verify_source_file(_source_path(config, entry), entry)
        duration = round((perf_counter() - started_at) * 1000)
        result = {
            "operation": "verification",
            "outcome": "succeeded",
            "record_count": sum(manifest["database"]["table_counts"].values()),
            "artifact_count": len(manifest["storage"]["files"]),
            "duration_ms": duration,
            "correlation_id": str(correlation_id),
        }
        if record_event:
            record_operation_event(
                config.database_url,
                operation="verification",
                outcome="succeeded",
                dataset="combined",
                actor_identifier=config.actor_identifier,
                correlation_id=correlation_id,
                record_count=result["record_count"],
                artifact_count=result["artifact_count"],
                duration_ms=duration,
            )
        return result
    except (DataOperationError, OSError, psycopg.Error) as exc:
        if record_event:
            _record_failure(
                config,
                "verification",
                correlation_id,
                getattr(exc, "reason_code", "verification_failed"),
                started_at,
            )
        raise


def _quarantine_stage_parent(config: DataOperationConfig) -> Path:
    return _safe_target(
        config.import_storage_root, "quarantine/.retention-staging"
    )


def _quarantine_entry_paths(
    config: DataOperationConfig, staging_root: Path, entry: dict[str, Any]
) -> tuple[Path, Path]:
    stem = str(entry["internal_name"]).split(".", 1)[0]
    if not SAFE_STEM.fullmatch(stem):
        raise DataOperationError("storage_key_invalid", "Quarantine key is invalid")
    original = _safe_target(
        config.import_storage_root,
        f"quarantine/{entry['execution_id']}/{stem}.upload",
    )
    return staging_root / f"{entry['inspection_id']}.upload", original


def _cleanup_quarantine_stage(staging_root: Path) -> None:
    manifest_path = staging_root / "manifest.json"
    unexpected = [path for path in staging_root.iterdir() if path != manifest_path]
    if unexpected:
        raise DataOperationError(
            "retention_staging_invalid", "Quarantine staging contains unknown entries"
        )
    manifest_path.unlink()
    staging_root.rmdir()
    try:
        staging_root.parent.rmdir()
    except OSError:
        pass


def _restore_staged_quarantine(
    config: DataOperationConfig, manifest: dict[str, Any], staging_root: Path
) -> None:
    for entry in reversed(manifest["entries"]):
        staged, original = _quarantine_entry_paths(config, staging_root, entry)
        if not entry["had_content"]:
            if staged.exists() or staged.is_symlink():
                raise DataOperationError(
                    "retention_staging_invalid", "Unexpected staged quarantine file"
                )
            continue
        if staged.is_file() or staged.is_symlink():
            if original.exists() or original.is_symlink():
                raise DataOperationError(
                    "retention_compensation_failed",
                    "Quarantine path changed during compensation",
                )
            original.parent.mkdir(parents=True, exist_ok=True)
            staged.rename(original)
        elif staged.exists() or not (original.is_file() or original.is_symlink()):
            raise DataOperationError(
                "retention_compensation_failed",
                "Staged quarantine content cannot be recovered",
            )
    _cleanup_quarantine_stage(staging_root)


def _write_quarantine_manifest(
    staging_root: Path, correlation_id: UUID, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    entries = [
        {
            "inspection_id": row["id"],
            "execution_id": row["execution_id"],
            "internal_name": row["internal_name"],
            "had_content": row["had_content"],
        }
        for row in rows
    ]
    manifest = {
        "format_version": 1,
        "correlation_id": str(correlation_id),
        "entries": entries,
    }
    temporary = staging_root / ".manifest.tmp"
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    temporary.replace(staging_root / "manifest.json")
    return manifest


def _stage_quarantine_files(
    config: DataOperationConfig,
    rows: list[dict[str, Any]],
    correlation_id: UUID,
) -> tuple[dict[str, Any], Path]:
    staging_root = _safe_target(
        config.import_storage_root,
        f"quarantine/.retention-staging/{correlation_id}",
    )
    staged_rows: list[dict[str, Any]] = []
    for row in rows:
        entry = {
            "inspection_id": row["id"],
            "execution_id": row["execution_id"],
            "internal_name": row["internal_name"],
        }
        _, original = _quarantine_entry_paths(config, staging_root, entry)
        if original.exists() and not (original.is_file() or original.is_symlink()):
            raise DataOperationError(
                "storage_key_invalid", "Quarantine entry is invalid"
            )
        staged_rows.append(
            {**row, "had_content": original.is_file() or original.is_symlink()}
        )
    staging_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    staging_root.parent.chmod(0o700)
    manifest = _write_quarantine_manifest(staging_root, correlation_id, staged_rows)
    try:
        for entry in manifest["entries"]:
            if not entry["had_content"]:
                continue
            staged, original = _quarantine_entry_paths(
                config, staging_root, entry
            )
            original.rename(staged)
    except Exception:
        _restore_staged_quarantine(config, manifest, staging_root)
        raise
    return manifest, staging_root


def _load_quarantine_manifest(staging_root: Path) -> dict[str, Any]:
    manifest_path = staging_root / "manifest.json"
    try:
        if (
            not manifest_path.is_file()
            or manifest_path.is_symlink()
            or manifest_path.stat().st_size > 1024 * 1024
        ):
            raise OSError
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        correlation_id = UUID(str(manifest.get("correlation_id", "")))
    except (
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        AttributeError,
    ) as exc:
        raise DataOperationError(
            "retention_staging_invalid", "Quarantine staging manifest is invalid"
        ) from exc
    entries = manifest.get("entries")
    if (
        manifest.get("format_version") != 1
        or str(correlation_id) != staging_root.name
        or not isinstance(entries, list)
    ):
        raise DataOperationError(
            "retention_staging_invalid", "Quarantine staging manifest is invalid"
        )
    inspection_ids: set[int] = set()
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry)
            != {"inspection_id", "execution_id", "internal_name", "had_content"}
            or not isinstance(entry["inspection_id"], int)
            or isinstance(entry["inspection_id"], bool)
            or entry["inspection_id"] <= 0
            or entry["inspection_id"] in inspection_ids
            or not isinstance(entry["execution_id"], str)
            or not isinstance(entry["internal_name"], str)
            or not isinstance(entry["had_content"], bool)
        ):
            raise DataOperationError(
                "retention_staging_invalid", "Quarantine staging manifest is invalid"
            )
        inspection_ids.add(entry["inspection_id"])
    return manifest


def _mark_quarantine_discarded(
    connection: psycopg.Connection[Any], inspection_ids: list[int]
) -> None:
    if not inspection_ids:
        return
    updated = connection.execute(
        """
        UPDATE synergia.file_inspections SET discarded_at = now()
        WHERE id = ANY(%s) AND decision = 'rejected'
          AND discarded_at IS NULL AND retained_until <= now()
        RETURNING id
        """,
        (inspection_ids,),
    ).fetchall()
    if len(updated) != len(inspection_ids):
        raise DataOperationError(
            "retention_state_changed", "Quarantine state changed concurrently"
        )


def _unlink_staged_quarantine_entry(staged: Path) -> None:
    if staged.is_symlink() or staged.is_file():
        staged.unlink()
    elif staged.exists():
        raise DataOperationError(
            "retention_staging_invalid", "Staged quarantine entry is invalid"
        )


def _discard_staged_quarantine(
    config: DataOperationConfig, manifest: dict[str, Any], staging_root: Path
) -> None:
    for entry in manifest["entries"]:
        staged, original = _quarantine_entry_paths(config, staging_root, entry)
        if original.exists() or original.is_symlink():
            raise DataOperationError(
                "retention_state_changed",
                "Discarded quarantine content returned to its original path",
            )
        _unlink_staged_quarantine_entry(staged)
        try:
            original.parent.rmdir()
        except OSError:
            pass


def _reconcile_quarantine_stage(
    connection: psycopg.Connection[Any],
    config: DataOperationConfig,
    staging_root: Path,
) -> dict[str, Any] | None:
    manifest = _load_quarantine_manifest(staging_root)
    correlation_id = UUID(manifest["correlation_id"])
    entries = manifest["entries"]
    inspection_ids = [entry["inspection_id"] for entry in entries]
    rows = connection.execute(
        """
        SELECT id, execution_id, internal_name, discarded_at
        FROM synergia.file_inspections WHERE id = ANY(%s)
        """,
        (inspection_ids,),
    ).fetchall()
    by_id = {row["id"]: row for row in rows}
    if len(rows) != len(entries) or any(
        entry["inspection_id"] not in by_id
        or by_id[entry["inspection_id"]]["execution_id"] != entry["execution_id"]
        or by_id[entry["inspection_id"]]["internal_name"]
        != entry["internal_name"]
        for entry in entries
    ):
        raise DataOperationError(
            "retention_staging_invalid", "Quarantine staging does not match metadata"
        )
    events = connection.execute(
        """
        SELECT outcome, actor_identifier, record_count, duration_ms
        FROM synergia.data_operation_events
        WHERE operation = 'retention' AND dataset = 'quarantine'
          AND correlation_id = %s ORDER BY id
        """,
        (correlation_id,),
    ).fetchall()
    started = next((event for event in events if event["outcome"] == "started"), None)
    succeeded = any(event["outcome"] == "succeeded" for event in events)
    success_is_current = bool(events) and events[-1]["outcome"] == "succeeded"
    discarded = [by_id[item]["discarded_at"] is not None for item in inspection_ids]
    if started is None:
        if any(discarded) or succeeded:
            raise DataOperationError(
                "retention_state_changed", "Quarantine staging state is inconsistent"
            )
        _restore_staged_quarantine(config, manifest, staging_root)
        return None
    if not all(discarded):
        raise DataOperationError(
            "retention_state_changed", "Quarantine staging state is inconsistent"
        )
    try:
        _discard_staged_quarantine(config, manifest, staging_root)
        if not success_is_current:
            connection.execute(
                """
                INSERT INTO synergia.data_operation_events (
                    operation, outcome, dataset, actor_identifier, correlation_id,
                    record_count, duration_ms
                ) VALUES ('retention', 'succeeded', 'quarantine', %s, %s, %s, %s)
                """,
                (
                    started["actor_identifier"],
                    correlation_id,
                    started["record_count"],
                    started["duration_ms"],
                ),
            )
            connection.commit()
        _cleanup_quarantine_stage(staging_root)
    except (DataOperationError, OSError) as exc:
        connection.rollback()
        connection.execute(
            """
            INSERT INTO synergia.data_operation_events (
                operation, outcome, dataset, actor_identifier, correlation_id,
                reason_code, record_count
            ) VALUES ('retention', 'failed', 'quarantine', %s, %s,
                      'retention_incomplete', %s)
            """,
            (started["actor_identifier"], correlation_id, started["record_count"]),
        )
        connection.commit()
        raise DataOperationError(
            "retention_incomplete", "Quarantine discard requires reconciliation"
        ) from exc
    return {
        "operation": "retention",
        "outcome": "succeeded",
        "dataset": "quarantine",
        "record_count": started["record_count"],
        "duration_ms": started["duration_ms"],
        "correlation_id": str(correlation_id),
    }


def _reconcile_quarantine_staging(
    connection: psycopg.Connection[Any], config: DataOperationConfig
) -> None:
    parent = _quarantine_stage_parent(config)
    if not parent.exists():
        return
    if not parent.is_dir() or parent.is_symlink():
        raise DataOperationError(
            "retention_staging_invalid", "Quarantine staging root is invalid"
        )
    for staging_root in sorted(parent.iterdir()):
        if not staging_root.is_dir() or staging_root.is_symlink():
            raise DataOperationError(
                "retention_staging_invalid", "Quarantine staging entry is invalid"
            )
        manifest_path = staging_root / "manifest.json"
        if not manifest_path.exists():
            contents = list(staging_root.iterdir())
            if contents and not all(
                path.name == ".manifest.tmp"
                and path.is_file()
                and not path.is_symlink()
                for path in contents
            ):
                raise DataOperationError(
                    "retention_staging_invalid",
                    "Quarantine staging entry has no recovery manifest",
                )
            for path in contents:
                path.unlink()
            staging_root.rmdir()
            continue
        _reconcile_quarantine_stage(connection, config, staging_root)
    try:
        parent.rmdir()
    except OSError:
        pass


def _purge_quarantine(
    config: DataOperationConfig, *, apply: bool, started_at: float
) -> dict[str, Any]:
    correlation_id = uuid4()
    with psycopg.connect(config.database_url, row_factory=dict_row) as connection:
        if apply:
            connection.execute(
                "SELECT pg_advisory_lock(hashtextextended(%s, 0))",
                ("synergia:retention:quarantine",),
            )
            _reconcile_quarantine_staging(connection, config)
        rows = connection.execute(
            """
            SELECT id, execution_id, internal_name
            FROM synergia.file_inspections
            WHERE decision = 'rejected' AND discarded_at IS NULL
              AND retained_until <= now()
            ORDER BY id FOR UPDATE
            """
        ).fetchall()
        count = len(rows)
        if not apply:
            connection.rollback()
            return {
                "operation": "retention",
                "outcome": "dry_run",
                "dataset": "quarantine",
                "record_count": count,
            }
        manifest, staging_root = _stage_quarantine_files(
            config, rows, correlation_id
        )
        try:
            _mark_quarantine_discarded(connection, [row["id"] for row in rows])
            duration = round((perf_counter() - started_at) * 1000)
            connection.execute(
                """
                INSERT INTO synergia.data_operation_events (
                    operation, outcome, dataset, actor_identifier,
                    correlation_id, record_count, duration_ms
                ) VALUES ('retention', 'started', 'quarantine', %s, %s, %s, %s)
                """,
                (config.actor_identifier, correlation_id, count, duration),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            _restore_staged_quarantine(config, manifest, staging_root)
            raise
        result = _reconcile_quarantine_stage(connection, config, staging_root)
        if result is None:
            raise DataOperationError(
                "retention_state_changed", "Committed retention was not recovered"
            )
        return result


def _purge_dataset(
    config: DataOperationConfig,
    dataset: str,
    *,
    apply: bool,
    transient_retention_days: int = 90,
) -> dict[str, Any]:
    if dataset in PROTECTED_PURGE_DATASETS or dataset not in ALLOWED_PURGE_DATASETS:
        if apply:
            record_operation_event(
                config.database_url,
                operation="retention",
                outcome="refused",
                dataset="combined",
                actor_identifier=config.actor_identifier,
                correlation_id=uuid4(),
                reason_code="dataset_protected",
            )
        raise DataOperationError("dataset_protected", "Dataset cannot be purged")
    if not 1 <= transient_retention_days <= 3650:
        raise DataOperationError("retention_invalid", "Retention days are invalid")

    correlation_id = uuid4()
    started_at = perf_counter()
    if dataset == "quarantine":
        return _purge_quarantine(config, apply=apply, started_at=started_at)

    cutoff = datetime.now(UTC) - timedelta(days=transient_retention_days)
    queries = (
        (
            "identity_login_attempts",
            """SELECT count(*) AS total FROM synergia.identity_login_attempts
               WHERE attempted_at < %s""",
            """DELETE FROM synergia.identity_login_attempts
               WHERE attempted_at < %s""",
        ),
        (
            "rate_limit_events",
            """SELECT count(*) AS total FROM synergia.rate_limit_events
               WHERE occurred_at < %s""",
            """DELETE FROM synergia.rate_limit_events
               WHERE occurred_at < %s""",
        ),
        (
            "rate_limit_buckets",
            """SELECT count(*) AS total FROM synergia.rate_limit_buckets
               WHERE window_expires_at < %s""",
            """DELETE FROM synergia.rate_limit_buckets
               WHERE window_expires_at < %s""",
        ),
    )
    with psycopg.connect(config.database_url, row_factory=dict_row) as connection:
        count = 0
        for _, select_query, delete_query in queries:
            count += connection.execute(select_query, (cutoff,)).fetchone()["total"]
            if apply:
                connection.execute(delete_query, (cutoff,))
        if not apply:
            connection.rollback()
            return {
                "operation": "retention",
                "outcome": "dry_run",
                "dataset": dataset,
                "record_count": count,
            }
        duration = round((perf_counter() - started_at) * 1000)
        connection.execute(
            """
            INSERT INTO synergia.data_operation_events (
                operation, outcome, dataset, actor_identifier, correlation_id,
                record_count, duration_ms
            ) VALUES ('retention', 'succeeded', %s, %s, %s, %s, %s)
            """,
            (
                dataset,
                config.actor_identifier,
                correlation_id,
                count,
                duration,
            ),
        )
    return {
        "operation": "retention",
        "outcome": "succeeded",
        "dataset": dataset,
        "record_count": count,
        "duration_ms": duration,
        "correlation_id": str(correlation_id),
    }


def purge_dataset(
    config: DataOperationConfig,
    dataset: str,
    *,
    apply: bool,
    transient_retention_days: int = 90,
) -> dict[str, Any]:
    started_at = perf_counter()
    try:
        return _purge_dataset(
            config,
            dataset,
            apply=apply,
            transient_retention_days=transient_retention_days,
        )
    except DataOperationError as exc:
        if exc.reason_code not in {
            "dataset_protected",
            "retention_incomplete",
            "retention_invalid",
        }:
            _record_failure(
                config,
                "retention",
                uuid4(),
                exc.reason_code,
                started_at,
                dataset,
            )
        raise
    except (OSError, psycopg.Error) as exc:
        _record_failure(
            config,
            "retention",
            uuid4(),
            "retention_failed",
            started_at,
            dataset,
        )
        raise DataOperationError(
            "retention_failed", "Retention operation failed"
        ) from exc
