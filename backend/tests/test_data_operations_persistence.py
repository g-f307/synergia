from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app import data_operations
from app.data_operations import (
    DataOperationConfig,
    DataOperationError,
    create_backup,
    purge_dataset,
    restore_backup,
    verify_restoration,
)
from app.observability.config import ObservabilityConfig
from app.observability.health import probe_data_recovery
from app.observability.metrics import render_metrics

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _database_url(database: str) -> str:
    parameters = conninfo_to_dict(os.environ["DATABASE_URL"])
    parameters["dbname"] = database
    return make_conninfo(**parameters)


def _create_database(name: str) -> None:
    parameters = conninfo_to_dict(os.environ["DATABASE_URL"])
    parameters["dbname"] = "postgres"
    with psycopg.connect(make_conninfo(**parameters), autocommit=True) as connection:
        connection.execute(f'CREATE DATABASE "{name}"')


def _drop_database(name: str) -> None:
    parameters = conninfo_to_dict(os.environ["DATABASE_URL"])
    parameters["dbname"] = "postgres"
    with psycopg.connect(make_conninfo(**parameters), autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (name,),
        )
        connection.execute(f'DROP DATABASE IF EXISTS "{name}"')


def _apply_migrations(database_url: str) -> None:
    migrations = sorted((ROOT / "database" / "migrations").glob("*.sql"))
    with psycopg.connect(database_url) as connection:
        for migration in migrations:
            connection.execute(migration.read_text(encoding="utf-8"))


@pytest.fixture
def isolated_database() -> str:
    name = f"synergia_backup_{uuid4().hex[:12]}"
    _create_database(name)
    try:
        database_url = _database_url(name)
        _apply_migrations(database_url)
        yield database_url
    finally:
        _drop_database(name)


def _seed_recovery_data(config: DataOperationConfig) -> dict[str, object]:
    organization_id = uuid4()
    user_id = uuid4()
    session_id = uuid4()
    report_id = uuid4()
    report_version_id = uuid4()
    approval_id = uuid4()
    correlation_id = uuid4()
    execution_id = f"recovery-{uuid4()}"
    upload_content = b"synthetic recovery evidence\n"
    avatar_content = b"synthetic-avatar"
    upload_hash = _sha256(upload_content)
    avatar_hash = _sha256(avatar_content)
    internal_name = f"{uuid4().hex}{uuid4().hex[:16]}.csv"
    avatar_key = f"{uuid4().hex}{uuid4().hex[:16]}.png"
    storage_key = f"accepted/N_FP/{execution_id}/{internal_name}"
    upload_path = config.import_storage_root / storage_key
    avatar_path = config.avatar_storage_root / avatar_key[:2] / avatar_key
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    avatar_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(upload_content)
    avatar_path.write_bytes(avatar_content)
    for name, content in {
        "validation-report.json": b'{"issues": [], "synthetic": true}\n',
        "pipeline-summary.json": b'{"status": "completed", "synthetic": true}\n',
        "normalized-data.json": b'{"records": [], "synthetic": true}\n',
    }.items():
        (upload_path.parent / name).write_bytes(content)

    report_content = {"schema_version": "1.0.0", "rows": [{"result": "synthetic"}]}
    report_hash = _sha256(
        json.dumps(
            report_content, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    )
    with psycopg.connect(config.database_url) as connection:
        connection.execute(
            """
            INSERT INTO synergia.iam_organizations (
                id, organization_code, display_name
            ) VALUES (%s, %s, 'Synthetic Recovery Organization')
            """,
            (organization_id, f"recovery-{organization_id.hex[:12]}"),
        )
        connection.execute(
            """
            INSERT INTO synergia.identity_users (
                id, status, display_name, avatar_storage_key,
                avatar_media_type, avatar_size_bytes, avatar_sha256,
                avatar_updated_at
            ) VALUES (%s, 'active', 'Synthetic Recovery User', %s,
                      'image/png', %s, %s, now())
            """,
            (user_id, avatar_key, len(avatar_content), avatar_hash),
        )
        connection.execute(
            """
            INSERT INTO synergia.identity_sessions (
                id, user_id, status, authenticated_at, last_seen_at,
                idle_expires_at, absolute_expires_at, authentication_method
            ) VALUES (%s, %s, 'active', now(), now(), now() + interval '8 hours',
                      now() + interval '24 hours', 'synthetic')
            """,
            (session_id, user_id),
        )
        connection.execute(
            """
            INSERT INTO synergia.user_role_assignments (
                user_id, role_id, organization_id
            ) SELECT %s, id, %s FROM synergia.roles
              WHERE normalized_key = 'gestor'
            """,
            (user_id, organization_id),
        )
        connection.execute(
            """
            INSERT INTO synergia.executions (
                id, status, source, actor_type, actor_identifier,
                organization_id, initiated_by_user_id, initiated_by_session_id,
                state_changed_by_type, state_changed_by, state_change_reason,
                correlation_id, finished_at
            ) VALUES (%s, 'completed', 'N-FP', 'technical', 'recovery-test',
                      %s, %s, %s, 'technical', 'recovery-test', 'completed',
                      %s, now())
            """,
            (
                execution_id,
                organization_id,
                user_id,
                session_id,
                correlation_id,
            ),
        )
        inspection_id = connection.execute(
            """
            INSERT INTO synergia.file_inspections (
                execution_id, source, original_file_name, internal_name,
                extension, declared_media_type, detected_media_type,
                size_bytes, content_hash, decision, reason_code, analyzed_at
            ) VALUES (%s, 'N-FP', 'synthetic.csv', %s, 'csv', 'text/csv',
                      'text/csv', %s, %s, 'accepted', 'accepted', now())
            RETURNING id
            """,
            (execution_id, internal_name, len(upload_content), upload_hash),
        ).fetchone()[0]
        source_id = connection.execute(
            """
            INSERT INTO synergia.source_files (
                execution_id, file_name, content_hash, media_type, size_bytes,
                extension, storage_key, inspection_id, detected_media_type
            ) VALUES (%s, 'synthetic.csv', %s, 'text/csv', %s, 'csv', %s,
                      %s, 'text/csv') RETURNING id
            """,
            (
                execution_id,
                upload_hash,
                len(upload_content),
                storage_key,
                inspection_id,
            ),
        ).fetchone()[0]
        operational_org = connection.execute(
            """
            INSERT INTO synergia.organizations (
                organization_code, organization_name, execution_id, source_file_id
            ) VALUES ('SYN-RECOVERY', 'Synthetic', %s, %s) RETURNING id
            """,
            (execution_id, source_id),
        ).fetchone()[0]
        workorder_id = connection.execute(
            """
            INSERT INTO synergia.workorders (
                workorder_number, organization_id, execution_id,
                source_file_id, processing_status
            ) VALUES (%s, %s, %s, %s, 'consolidated') RETURNING id
            """,
            (f"SYN-WO-{uuid4().hex[:12]}", operational_org, execution_id, source_id),
        ).fetchone()[0]
        pending_id = connection.execute(
            """
            INSERT INTO synergia.pending_items (
                workorder_id, execution_id, source_file_id, category, reason
            ) VALUES (%s, %s, %s, 'synthetic_review', 'Synthetic') RETURNING id
            """,
            (workorder_id, execution_id, source_id),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO synergia.reports (
                id, report_type, organization_id, created_by_user_id
            ) VALUES (%s, 'workorder_consolidated', %s, %s)
            """,
            (report_id, organization_id, user_id),
        )
        connection.execute(
            """
            INSERT INTO synergia.report_versions (
                id, report_id, version, execution_id, organization_id,
                requested_by_user_id, requested_by_session_id, reference_at,
                schema_version, state, completeness, correlation_id,
                completed_at
            ) VALUES (%s, %s, 1, %s, %s, %s, %s, now(), '1.0.0',
                      'succeeded', 'complete', %s, now())
            """,
            (
                report_version_id,
                report_id,
                execution_id,
                organization_id,
                user_id,
                session_id,
                correlation_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO synergia.report_artifacts (
                report_version_id, artifact_type, content, content_hash
            ) VALUES (%s, 'data', %s, %s)
            """,
            (report_version_id, json.dumps(report_content), report_hash),
        )
        connection.execute(
            """
            INSERT INTO synergia.report_events (
                report_version_id, event_type, actor_user_id,
                correlation_id, payload
            ) VALUES (%s, 'report.generation_succeeded', %s, %s, '{}')
            """,
            (report_version_id, user_id, correlation_id),
        )
        connection.execute(
            """
            INSERT INTO synergia.approval_requests (
                id, pending_item_id, organization_id, requester_user_id,
                requester_session_id, assignee_user_id, review_group,
                policy_key, policy_version, state, submitted_at, decided_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'gestor',
                      'pending.standard', 1, 'approved', now(), now())
            """,
            (
                approval_id,
                pending_id,
                organization_id,
                user_id,
                session_id,
                user_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO synergia.approval_stages (
                request_id, sequence, review_group, assignee_user_id,
                state, closed_at
            ) VALUES (%s, 1, 'gestor', %s, 'completed', now())
            """,
            (approval_id, user_id),
        )
        connection.execute(
            """
            INSERT INTO synergia.approval_events (
                request_id, event_type, from_state, to_state, actor_user_id,
                actor_session_id, organization_id, actor_permissions,
                assignee_user_id, justification, consent, request_version,
                correlation_id
            ) VALUES (%s, 'approved', 'in_review', 'approved', %s, %s, %s,
                      '["approval.decide"]', %s, 'Synthetic approval', true,
                      1, %s)
            """,
            (
                approval_id,
                user_id,
                session_id,
                organization_id,
                user_id,
                correlation_id,
            ),
        )
        rejected_name = f"{uuid4().hex}{uuid4().hex[:16]}.csv"
        connection.execute(
            """
            INSERT INTO synergia.file_inspections (
                execution_id, source, original_file_name, internal_name,
                extension, declared_media_type, detected_media_type,
                size_bytes, content_hash, decision, reason_code,
                analyzed_at, retained_until
            ) VALUES (%s, 'N-FP', 'rejected.csv', %s, 'csv', 'text/csv',
                      'text/html', 9, %s, 'rejected', 'disguised_active_content',
                      now() - interval '2 days', now() - interval '1 day')
            """,
            (execution_id, rejected_name, "b" * 64),
        )
        connection.execute(
            """
            INSERT INTO synergia.identity_login_attempts (
                identifier_hash, ip_hash, attempted_at
            ) VALUES (%s, %s, now() - interval '100 days')
            """,
            ("c" * 64, "d" * 64),
        )
    rejected_stem = rejected_name.split(".", 1)[0]
    rejected_path = (
        config.import_storage_root
        / "quarantine"
        / execution_id
        / f"{rejected_stem}.upload"
    )
    rejected_path.parent.mkdir(parents=True, exist_ok=True)
    rejected_path.write_bytes(b"untrusted")
    return {
        "user_id": user_id,
        "execution_id": execution_id,
        "report_id": report_id,
        "approval_id": approval_id,
        "upload_path": upload_path,
        "upload_content": upload_content,
        "rejected_path": rejected_path,
    }


def test_backup_restore_integrity_retention_and_recovery(
    tmp_path, monkeypatch, isolated_database
) -> None:
    source = DataOperationConfig(
        isolated_database,
        tmp_path / "source-imports",
        tmp_path / "source-avatars",
        "integration-recovery",
    )
    identifiers = _seed_recovery_data(source)
    upload_path = identifiers["upload_path"]
    upload_content = identifiers["upload_content"]
    assert isinstance(upload_path, Path) and isinstance(upload_content, bytes)

    recovery_config = ObservabilityConfig(
        source.database_url, source.import_storage_root, "x" * 32
    )
    assert probe_data_recovery(recovery_config).reason == "backup_missing"
    with psycopg.connect(source.database_url) as connection:
        connection.execute(
            """
            INSERT INTO synergia.data_operation_events (
                operation, outcome, dataset, actor_identifier, correlation_id,
                record_count, artifact_count, duration_ms, occurred_at
            ) VALUES ('backup', 'succeeded', 'combined', 'integration-recovery',
                      %s, 0, 0, 1, now() - interval '26 hours')
            """,
            (uuid4(),),
        )
    assert probe_data_recovery(recovery_config).reason == "backup_stale"

    symbolic_target = source.import_storage_root / "protected-synthetic.csv"
    symbolic_target.write_bytes(upload_content)
    upload_path.unlink()
    upload_path.symlink_to(symbolic_target)
    with pytest.raises(DataOperationError) as symbolic:
        create_backup(source, tmp_path / "symbolic-bundle")
    assert symbolic.value.reason_code == "referenced_file_missing"
    assert symbolic_target.read_bytes() == upload_content
    upload_path.unlink()
    symbolic_target.unlink()
    upload_path.write_bytes(upload_content)

    upload_path.unlink()
    with pytest.raises(DataOperationError) as missing:
        create_backup(source, tmp_path / "missing-bundle")
    assert missing.value.reason_code == "referenced_file_missing"
    assert probe_data_recovery(recovery_config).reason == "operation_failed"
    upload_path.write_bytes(b"corrupted")
    with pytest.raises(DataOperationError) as corrupted:
        create_backup(source, tmp_path / "corrupted-bundle")
    assert corrupted.value.reason_code == "referenced_file_corrupted"
    upload_path.write_bytes(upload_content)

    original_archive = data_operations._write_storage_archive

    def write_with_controlled_activity(archive_path, config, files):
        with psycopg.connect(source.database_url) as connection:
            connection.execute(
                """
                INSERT INTO synergia.identity_login_attempts (
                    identifier_hash, ip_hash, succeeded
                ) VALUES (%s, %s, true)
                """,
                ("e" * 64, "f" * 64),
            )
        original_archive(archive_path, config, files)

    monkeypatch.setattr(
        data_operations, "_write_storage_archive", write_with_controlled_activity
    )
    bundle = tmp_path / "bundle"
    backup = create_backup(source, bundle)
    assert backup["outcome"] == "succeeded"
    assert backup["artifact_count"] == 5
    private_manifest = (bundle / "manifest.json").read_text(encoding="utf-8")
    assert "synergia-local-only" not in private_manifest
    assert "synthetic.csv" not in private_manifest
    assert str(source.import_storage_root) not in private_manifest
    recovery_health = probe_data_recovery(recovery_config)
    assert recovery_health.status == "healthy"
    monkeypatch.setenv("DATABASE_URL", source.database_url)
    metrics = render_metrics().decode()
    assert (
        'synergia_data_operation_last_success_timestamp_seconds{operation="backup"}'
        in metrics
    )
    assert 'synergia_data_operation_failures_total{operation="backup"}' in metrics
    monkeypatch.setattr(data_operations, "_write_storage_archive", original_archive)

    database_name = f"synergia_restore_{uuid4().hex[:12]}"
    _create_database(database_name)
    target = DataOperationConfig(
        _database_url(database_name),
        tmp_path / "target-imports",
        tmp_path / "target-avatars",
        "integration-restore",
    )
    try:
        restored = restore_backup(target, bundle)
        assert restored["outcome"] == "succeeded"
        verified = verify_restoration(target, bundle)
        assert verified["artifact_count"] == 5
        with psycopg.connect(target.database_url) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM synergia.identity_users WHERE id = %s",
                    (identifiers["user_id"],),
                ).fetchone()[0]
                == 1
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM synergia.executions WHERE id = %s",
                    (identifiers["execution_id"],),
                ).fetchone()[0]
                == 1
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM synergia.report_artifacts"
                ).fetchone()[0]
                >= 1
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM synergia.notifications"
                ).fetchone()[0]
                >= 1
            )
            assert (
                connection.execute(
                    """SELECT count(*) FROM synergia.approval_events
                       WHERE request_id = %s""",
                    (identifiers["approval_id"],),
                ).fetchone()[0]
                == 1
            )
            assert (
                connection.execute(
                    """SELECT count(*) FROM synergia.audit_events
                       WHERE execution_id = %s""",
                    (identifiers["execution_id"],),
                ).fetchone()[0]
                >= 1
            )

        restored_upload = target.import_storage_root / upload_path.relative_to(
            source.import_storage_root
        )
        assert (restored_upload.parent / "validation-report.json").is_file()
        assert (restored_upload.parent / "pipeline-summary.json").is_file()
        assert (restored_upload.parent / "normalized-data.json").is_file()
        assert not (target.import_storage_root / "quarantine").exists()
        restored_upload.unlink()
        with pytest.raises(DataOperationError) as absent:
            verify_restoration(target, bundle)
        assert absent.value.reason_code == "referenced_file_missing"
        restored_upload.write_bytes(b"corrupted")
        with pytest.raises(DataOperationError) as changed:
            verify_restoration(target, bundle)
        assert changed.value.reason_code == "referenced_file_corrupted"
        restored_upload.write_bytes(upload_content)
        assert verify_restoration(target, bundle)["outcome"] == "succeeded"

        with pytest.raises(DataOperationError) as nonempty:
            restore_backup(target, bundle)
        assert nonempty.value.reason_code == "target_database_not_empty"
    finally:
        _drop_database(database_name)

    damaged_bundle = tmp_path / "damaged-bundle"
    shutil.copytree(bundle, damaged_bundle)
    with (damaged_bundle / "storage.tar.gz").open("ab") as archive:
        archive.write(b"corruption")
    with pytest.raises(DataOperationError) as damaged:
        verify_restoration(source, damaged_bundle)
    assert damaged.value.reason_code == "storage_archive_corrupted"

    original_mark_discarded = data_operations._mark_quarantine_discarded

    def fail_after_quarantine_staging(connection, inspection_ids):
        assert identifiers["rejected_path"].exists() is False
        assert list(
            source.import_storage_root.glob("quarantine/.retention-staging/**/*.upload")
        )
        original_mark_discarded(connection, inspection_ids)
        assert connection.execute(
            """
            SELECT discarded_at IS NOT NULL AS discarded
            FROM synergia.file_inspections
            WHERE id = %s
            """,
            (inspection_ids[0],),
        ).fetchone()["discarded"]
        raise psycopg.OperationalError("synthetic database failure")

    monkeypatch.setattr(
        data_operations,
        "_mark_quarantine_discarded",
        fail_after_quarantine_staging,
    )
    with pytest.raises(DataOperationError) as retention_failure:
        purge_dataset(source, "quarantine", apply=True)
    assert retention_failure.value.reason_code == "retention_failed"
    monkeypatch.setattr(
        data_operations,
        "_mark_quarantine_discarded",
        original_mark_discarded,
    )
    assert identifiers["rejected_path"].read_bytes() == b"untrusted"
    assert not list(
        source.import_storage_root.glob("quarantine/.retention-staging/**/*.upload")
    )
    with psycopg.connect(source.database_url) as connection:
        assert (
            connection.execute(
                """
                SELECT count(*) FROM synergia.data_operation_events
                WHERE operation = 'retention' AND outcome = 'failed'
                  AND reason_code = 'retention_failed'
                  AND dataset = 'quarantine'
                """
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                """
                SELECT discarded_at FROM synergia.file_inspections
                WHERE internal_name = %s
                """,
                (identifiers["rejected_path"].stem + ".csv",),
            ).fetchone()[0]
            is None
        )
        assert (
            connection.execute(
                """
                SELECT count(*) FROM synergia.data_operation_events
                WHERE operation = 'retention' AND outcome = 'started'
                  AND dataset = 'quarantine'
                """
            ).fetchone()[0]
            == 0
        )

    identifiers["rejected_path"].unlink()
    identifiers["rejected_path"].symlink_to(upload_path)
    preview = purge_dataset(source, "quarantine", apply=False)
    assert preview["record_count"] >= 1
    applied = purge_dataset(source, "quarantine", apply=True)
    assert applied["record_count"] >= 1
    assert identifiers["rejected_path"].exists() is False
    assert upload_path.read_bytes() == upload_content
    assert not list(
        source.import_storage_root.glob("quarantine/.retention-staging/**/*.upload")
    )
    with psycopg.connect(source.database_url) as connection:
        retention_state = connection.execute(
            """
            SELECT discarded_at FROM synergia.file_inspections
            WHERE internal_name = %s
            """,
            (identifiers["rejected_path"].stem + ".csv",),
        ).fetchone()[0]
        retention_events = connection.execute(
            """
            SELECT outcome FROM synergia.data_operation_events
            WHERE correlation_id = %s ORDER BY id
            """,
            (applied["correlation_id"],),
        ).fetchall()
    assert retention_state is not None
    assert retention_events == [("started",), ("succeeded",)]
    transient = purge_dataset(
        source, "security_transient", apply=True, transient_retention_days=90
    )
    assert transient["record_count"] >= 1
    with pytest.raises(DataOperationError) as protected:
        purge_dataset(source, "audit", apply=True)
    assert protected.value.reason_code == "dataset_protected"
    with psycopg.connect(source.database_url) as connection:
        payload = json.dumps(
            connection.execute(
                """
                SELECT operation, outcome, dataset, actor_identifier,
                       reason_code, record_count, artifact_count, duration_ms
                FROM synergia.data_operation_events
                WHERE actor_identifier = 'integration-recovery'
                """
            ).fetchall(),
            default=str,
        )
    assert str(source.import_storage_root) not in payload
    assert "synthetic.csv" not in payload
    assert "untrusted" not in payload
    with psycopg.connect(source.database_url) as connection:
        event_id = connection.execute(
            """SELECT id FROM synergia.data_operation_events
               ORDER BY id DESC LIMIT 1"""
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.RestrictViolation):
            connection.execute(
                "DELETE FROM synergia.data_operation_events WHERE id = %s",
                (event_id,),
            )
        connection.rollback()
