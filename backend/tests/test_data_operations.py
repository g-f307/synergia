from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.data_operations import (
    BACKUP_TEMP_MARKER,
    ROOT,
    DataOperationConfig,
    DataOperationError,
    _backup_destination_key,
    _backup_temporary_prefix,
    _cleanup_stale_backup_temporaries,
    _database_command,
    _postgres_tool_command,
    _safe_target,
    create_backup,
    load_manifest,
    purge_dataset,
)


def test_database_command_keeps_password_out_of_arguments() -> None:
    connection, environment = _database_command(
        "postgresql://operator:secret-value@db.example.invalid:5432/synergia"
    )
    assert "secret-value" not in connection
    assert environment["PGPASSWORD"] == "secret-value"


def test_docker_fallback_refuses_a_remote_database(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.data_operations.shutil.which",
        lambda executable: "/usr/bin/docker" if executable == "docker" else None,
    )
    with pytest.raises(DataOperationError) as failure:
        _postgres_tool_command(
            "pg_dump",
            "postgresql://operator:secret@db.example.invalid:5432/synergia",
            [],
        )
    assert failure.value.reason_code == "postgres_tool_unavailable"


def test_manifest_rejects_invalid_or_unsupported_content(tmp_path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(DataOperationError) as failure:
        load_manifest(bundle)
    assert failure.value.reason_code == "manifest_version_unsupported"

    (bundle / "manifest.json").write_text("not-json", encoding="utf-8")
    with pytest.raises(DataOperationError) as invalid:
        load_manifest(bundle)
    assert invalid.value.reason_code == "manifest_invalid"

    (bundle / "manifest.json").write_text(
        json.dumps({"format_version": "1.0", "storage": {"files": []}}),
        encoding="utf-8",
    )
    with pytest.raises(DataOperationError) as incomplete:
        load_manifest(bundle)
    assert incomplete.value.reason_code == "manifest_invalid"

    malformed = {
        "format_version": "1.0",
        "database": {"dump_sha256": "a" * 64, "table_counts": {}},
        "storage": {
            "archive_sha256": "b" * 64,
            "files": [
                {
                    "kind": "accepted_upload",
                    "relative_path": "quarantine/execution/file.upload",
                    "sha256": "c" * 64,
                    "size_bytes": 1,
                }
            ],
        },
        "migrations": [],
    }
    (bundle / "manifest.json").write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(DataOperationError) as semantic:
        load_manifest(bundle)
    assert semantic.value.reason_code == "manifest_invalid"


def test_protected_dataset_is_refused_without_connecting_to_database(tmp_path) -> None:
    config = DataOperationConfig(
        "unused", tmp_path / "imports", tmp_path / "avatars", "test"
    )
    with pytest.raises(DataOperationError) as failure:
        purge_dataset(config, "audit", apply=False)
    assert failure.value.reason_code == "dataset_protected"


def test_storage_paths_and_repository_backup_destination_are_rejected(tmp_path) -> None:
    with pytest.raises(DataOperationError) as traversal:
        _safe_target(tmp_path, "../outside")
    assert traversal.value.reason_code == "storage_key_invalid"

    config = DataOperationConfig(
        "unused", tmp_path / "imports", tmp_path / "avatars", "test"
    )
    with pytest.raises(DataOperationError) as destination:
        create_backup(config, ROOT / "artifacts" / "backups" / "unsafe")
    assert destination.value.reason_code == "destination_unsafe"


def test_interrupted_backup_temporary_is_cleaned_before_next_attempt(tmp_path) -> None:
    destination = (tmp_path / "published-bundle").resolve()
    correlation_id = uuid4()
    temporary = tmp_path / (
        f"{_backup_temporary_prefix(destination)}{correlation_id}"
    )
    temporary.mkdir()
    created_at = datetime.now(UTC) - timedelta(hours=25)
    (temporary / BACKUP_TEMP_MARKER).write_text(
        json.dumps(
            {
                "format_version": "1.0",
                "destination_key": _backup_destination_key(destination),
                "correlation_id": str(correlation_id),
                "created_at": created_at.isoformat(),
            }
        ),
        encoding="utf-8",
    )
    (temporary / "database.dump").write_bytes(b"restricted")

    assert _cleanup_stale_backup_temporaries(destination) == 1
    assert not temporary.exists()


def test_backup_temporary_cleanup_preserves_active_foreign_and_unsafe_entries(
    tmp_path,
) -> None:
    destination = (tmp_path / "published-bundle").resolve()
    now = datetime.now(UTC)

    def temporary(*, age_hours: int, destination_key: str) -> Path:
        correlation_id = uuid4()
        path = tmp_path / (
            f"{_backup_temporary_prefix(destination)}{correlation_id}"
        )
        path.mkdir()
        (path / BACKUP_TEMP_MARKER).write_text(
            json.dumps(
                {
                    "format_version": "1.0",
                    "destination_key": destination_key,
                    "correlation_id": str(correlation_id),
                    "created_at": (now - timedelta(hours=age_hours)).isoformat(),
                }
            ),
            encoding="utf-8",
        )
        return path

    destination_key = _backup_destination_key(destination)
    active = temporary(age_hours=1, destination_key=destination_key)
    foreign = temporary(age_hours=25, destination_key="0" * 64)
    mismatched = temporary(age_hours=25, destination_key=destination_key)
    mismatched_marker = mismatched / BACKUP_TEMP_MARKER
    marker = json.loads(mismatched_marker.read_text(encoding="utf-8"))
    marker["correlation_id"] = str(uuid4())
    mismatched_marker.write_text(json.dumps(marker), encoding="utf-8")
    malformed = tmp_path / (
        f"{_backup_temporary_prefix(destination)}{uuid4()}"
    )
    malformed.mkdir()
    (malformed / BACKUP_TEMP_MARKER).write_text("not-json", encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    symbolic = tmp_path / f"{_backup_temporary_prefix(destination)}{uuid4()}"
    try:
        symbolic.symlink_to(external, target_is_directory=True)
    except OSError:
        symbolic = None

    assert _cleanup_stale_backup_temporaries(destination, now=now) == 0
    assert active.is_dir()
    assert foreign.is_dir()
    assert mismatched.is_dir()
    assert malformed.is_dir()
    if symbolic is not None:
        assert symbolic.is_symlink()
    assert external.is_dir()


def test_storage_path_rejects_symbolic_parent_without_following_it(tmp_path) -> None:
    root = tmp_path / "storage"
    real = root / "real"
    real.mkdir(parents=True)
    (root / "symbolic").symlink_to(real, target_is_directory=True)

    with pytest.raises(DataOperationError) as failure:
        _safe_target(root, "symbolic/file.upload")
    assert failure.value.reason_code == "storage_key_invalid"


def test_cli_failure_payload_does_not_expose_the_error_message(
    tmp_path, monkeypatch, capsys
) -> None:
    import sys

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from scripts.data_operations import main

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "manifest.json").write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@invalid/database")
    assert main(["verify", "--bundle", str(bundle)]) == 1
    output = capsys.readouterr().out
    assert "secret" not in output
    assert "manifest_version_unsupported" in output


def test_cli_sanitizes_unexpected_infrastructure_failure(
    tmp_path, monkeypatch, capsys
) -> None:
    import sys

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from scripts import data_operations as cli

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@invalid/database")
    monkeypatch.setenv("IMPORT_STORAGE_DIR", str(tmp_path / "imports"))
    monkeypatch.setenv("PROFILE_AVATAR_STORAGE_ROOT", str(tmp_path / "avatars"))

    def fail_backup(_config, _destination):
        raise OSError("/private/storage/customer-name")

    monkeypatch.setattr(cli, "create_backup", fail_backup)
    assert cli.main(["backup", "--destination", str(tmp_path / "bundle")]) == 1
    output = capsys.readouterr().out
    assert "Traceback" not in output
    assert "private" not in output
    assert "secret" not in output
    assert '"operation": "backup"' in output
    assert '"reason_code": "operation_failed"' in output
