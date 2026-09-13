from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.data_operations import (
    ROOT,
    DataOperationConfig,
    DataOperationError,
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
