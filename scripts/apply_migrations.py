from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "database" / "migrations"
LOCK_ID = 7_347_319_119

BASELINE_PROBES = {
    "0037": ("ai_assistance_contract", "synergia", ""),
    "0036": ("graylog_contract", "synergia", ""),
    "0035": ("feedback_contract", "synergia", ""),
    "0034": ("audit_export_contract", "synergia", ""),
    "0033": (
        "checks_contain",
        "",
        "email_deliveries.email_deliveries_provider_check:smtp;"
        "email_delivery_reconciliations.email_delivery_reconciliations_resolution_check:accepted",
    ),
    "0032": (
        "checks_contain",
        "",
        "executions.executions_source_check:Total Decision;"
        "source_files.source_files_source_check:Total Decision;"
        "file_inspections.file_inspections_source_check:Total Decision",
    ),
    "0001": ("schema", "synergia", ""),
    "0002": ("table", "synergia", "executions"),
    "0003": ("column", "source_files", "storage_key"),
    "0004": ("validation_constraint", "executions", "executions_status_check"),
    "0005": ("table", "synergia", "normalized_records"),
    "0006": ("table", "synergia", "pipeline_summaries"),
    "0007": ("index", "synergia", "idx_source_files_execution_source"),
    "0008": ("table", "synergia", "rule_evaluations"),
    "0009": ("table", "synergia", "execution_state_transitions"),
    "0010": ("table", "synergia", "file_inspections"),
    "0011": ("table", "synergia", "identity_users"),
    "0012": ("table", "synergia", "permissions"),
    "0013": ("table", "synergia", "identity_sessions"),
    "0014": ("column", "identity_users", "version"),
    "0015": ("table", "synergia", "user_permission_assignments"),
    "0016": ("table", "synergia", "identity_login_attempts"),
    "0017": ("column", "executions", "organization_id"),
    "0018": ("column", "identity_users", "avatar_updated_at"),
    "0019": ("table", "synergia", "reports"),
    "0020": ("column", "report_events", "actor_session_id"),
    "0021": ("table", "synergia", "notifications"),
    "0022": ("table", "synergia", "email_deliveries"),
    "0023": ("table", "synergia", "approval_requests"),
    "0024": ("table", "synergia", "rate_limit_buckets"),
    "0025": ("index", "synergia", "idx_audit_events_correlation"),
    "0026": ("table", "synergia", "data_operation_events"),
    "0027": (
        "index",
        "synergia",
        "idx_rule_evaluations_workorder_execution_id",
    ),
    "0028": ("column", "identity_users", "font_scale"),
    "0029": ("column", "identity_sessions", "device_label"),
    "0030": ("table", "synergia", "notification_template_revisions"),
    # Widening CHECKs creates no object, so the probe reads their definitions.
    "0031": (
        "checks_contain",
        "",
        "executions.executions_source_check:WO Status;"
        "source_files.source_files_source_check:WO Status;"
        "file_inspections.file_inspections_source_check:WO Status",
    ),
}


def object_exists(
    connection: psycopg.Connection, kind: str, parent: str, name: str
) -> bool:
    if kind == "ai_assistance_contract":
        if not object_exists(connection, "table", "synergia", "permissions"):
            return False
        return connection.execute(
            """WITH expected(role_key, permission_key, role_active) AS (
                VALUES ('gestor', 'ai.assistance.read', true),
                       ('gestor', 'ai.assistance.generate', true),
                       ('analista', 'ai.assistance.read', true),
                       ('analista', 'ai.assistance.generate', true)
            ), actual AS (
                SELECT r.normalized_key, p.normalized_key, r.is_active
                FROM synergia.role_permissions rp
                JOIN synergia.roles r ON r.id = rp.role_id
                JOIN synergia.permissions p ON p.id = rp.permission_id
                WHERE p.normalized_key IN
                    ('ai.assistance.read', 'ai.assistance.generate')
                  AND rp.revoked_at IS NULL
            )
            SELECT 1 WHERE EXISTS (
                SELECT 1 FROM synergia.permission_catalog_versions
                WHERE version = '1.6.0' AND is_active
            ) AND (SELECT count(*) FROM synergia.permissions
            WHERE normalized_key IN ('ai.assistance.read', 'ai.assistance.generate')
              AND catalog_version = '1.6.0' AND is_reserved AND is_active
              AND resource_type = 'execution') = 2
            AND NOT EXISTS (
                (SELECT * FROM expected EXCEPT SELECT * FROM actual)
                UNION ALL
                (SELECT * FROM actual EXCEPT SELECT * FROM expected)
            )"""
        ).fetchone() is not None
    if kind == "graylog_contract":
        return connection.execute(
            """SELECT 1 WHERE
            to_regclass('synergia.graylog_deliveries') IS NOT NULL
            AND to_regclass('synergia.graylog_delivery_history') IS NOT NULL
            AND to_regclass('synergia.graylog_scan_windows') IS NOT NULL
            AND to_regclass('synergia.observability_events') IS NOT NULL
            AND to_regclass('synergia.audit_event_catalog_v1') IS NOT NULL
            AND EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'synergia' AND table_name = 'graylog_deliveries'
                  AND column_name = 'source_snapshot' AND data_type = 'jsonb')
            AND EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'synergia' AND table_name = 'graylog_deliveries'
                  AND column_name = 'confirmed_at')
            AND EXISTS (SELECT 1 FROM pg_trigger
                WHERE tgrelid = to_regclass('synergia.graylog_delivery_history')
                  AND tgname = 'graylog_history_immutable' AND tgenabled <> 'D')
            AND (SELECT count(*) FROM pg_trigger
                 WHERE tgname = 'graylog_source_insert' AND tgenabled <> 'D') = 13"""
        ).fetchone() is not None
    if kind == "feedback_contract":
        if not object_exists(connection, "table", "synergia", "permissions"):
            return False
        return (
            connection.execute(
                """SELECT 1 WHERE
            to_regclass('synergia.feedback') IS NOT NULL
            AND to_regclass('synergia.feedback_events') IS NOT NULL
            AND (SELECT count(*) FROM pg_trigger
                 WHERE tgname IN ('feedback_events_immutable',
                     'feedback_mutation_guard', 'feedback_audit_created')
                     AND tgenabled <> 'D') = 3
            AND EXISTS (SELECT 1 FROM synergia.permissions
                        WHERE normalized_key = 'feedback.triage'
                          AND catalog_version = '1.5.0' AND is_reserved)"""
            ).fetchone()
            is not None
        )
    if kind == "audit_export_contract":
        if not object_exists(connection, "table", "synergia", "permissions"):
            return False
        row = connection.execute(
            """SELECT 1
            WHERE EXISTS (
                SELECT 1 FROM pg_class
                WHERE oid = to_regclass('synergia.audit_event_catalog')
                  AND relkind = 'v'
            ) AND EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgrelid = to_regclass('synergia.audit_export_events')
                  AND tgname = 'audit_export_events_immutable'
                  AND tgenabled <> 'D'
            ) AND to_regclass('synergia.audit_export_events_one_result') IS NOT NULL
            AND (SELECT count(*) FROM pg_constraint
                 WHERE conrelid = to_regclass('synergia.audit_export_events')
                   AND conname IN (
                       'audit_export_events_event_count_check',
                       'audit_export_events_export_format_check'
                   )) = 2
            AND EXISTS (
                SELECT 1 FROM synergia.permissions
                WHERE normalized_key = 'audit.export'
                  AND catalog_version = '1.4.0' AND is_reserved
            )"""
        ).fetchone()
        return row is not None
    if kind == "schema":
        row = connection.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            (parent,),
        ).fetchone()
    elif kind == "table":
        row = connection.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (parent, name),
        ).fetchone()
    elif kind == "column":
        row = connection.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'synergia' AND table_name = %s
              AND column_name = %s
            """,
            (parent, name),
        ).fetchone()
    elif kind == "constraint":
        row = connection.execute(
            """
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_schema = 'synergia' AND table_name = %s
              AND constraint_name = %s
            """,
            (parent, name),
        ).fetchone()
    elif kind == "validation_constraint":
        row = connection.execute(
            """
            SELECT 1
            FROM pg_constraint constraint_record
            JOIN pg_class table_record
              ON table_record.oid = constraint_record.conrelid
            JOIN pg_namespace schema_record
              ON schema_record.oid = table_record.relnamespace
            WHERE schema_record.nspname = 'synergia'
              AND table_record.relname = %s
              AND constraint_record.conname = %s
              AND pg_get_constraintdef(constraint_record.oid)
                    LIKE '%%validation_failed%%'
            """,
            (parent, name),
        ).fetchone()
    elif kind == "checks_contain":
        # "table.constraint:fragment;..." - every definition must hold its fragment.
        row = (1,)
        for item in name.split(";"):
            target, _, fragment = item.partition(":")
            table, _, constraint = target.partition(".")
            found = connection.execute(
                """
                SELECT 1
                FROM pg_constraint constraint_record
                JOIN pg_class table_record
                  ON table_record.oid = constraint_record.conrelid
                JOIN pg_namespace schema_record
                  ON schema_record.oid = table_record.relnamespace
                WHERE schema_record.nspname = 'synergia'
                  AND table_record.relname = %s
                  AND constraint_record.conname = %s
                  AND strpos(pg_get_constraintdef(constraint_record.oid), %s) > 0
                """,
                (table, constraint, fragment),
            ).fetchone()
            if found is None:
                row = None
                break
    elif kind == "index":
        row = connection.execute(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname = %s AND indexname = %s
            """,
            (parent, name),
        ).fetchone()
    else:  # pragma: no cover
        raise ValueError(f"unsupported baseline probe: {kind}")
    return row is not None


def resolve_baseline(files: list[Path], requested: str) -> int:
    names = [migration.name for migration in files]
    if requested not in names:
        raise RuntimeError(
            "MIGRATION_BASELINE_THROUGH must be an exact migration filename; "
            f"received {requested!r}"
        )
    return names.index(requested)


def validate_baseline(connection: psycopg.Connection, migrations: list[Path]) -> None:
    missing = []
    for migration in migrations:
        prefix = migration.name.split("_", 1)[0]
        probe = BASELINE_PROBES.get(prefix)
        if probe is None or not object_exists(connection, *probe):
            missing.append(f"{migration.name} ({probe or 'probe missing'})")
    if missing:
        raise RuntimeError(
            "legacy schema is partial or incompatible; missing baseline objects: "
            + ", ".join(missing)
        )


def main() -> None:
    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        raise SystemExit(f"no migrations found in {MIGRATIONS}")

    database_url = os.environ.get("DATABASE_URL", "").strip()
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS public.synergia_schema_migrations (
                    filename text PRIMARY KEY,
                    sha256 text NOT NULL,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            applied = dict(
                connection.execute(
                    "SELECT filename, sha256 FROM public.synergia_schema_migrations"
                ).fetchall()
            )
            digests = {
                migration.name: hashlib.sha256(migration.read_bytes()).hexdigest()
                for migration in files
            }
            for filename, previous in applied.items():
                current = digests.get(filename)
                if current is None:
                    raise RuntimeError(f"recorded migration is unavailable: {filename}")
                if previous != current:
                    raise RuntimeError(f"published migration changed: {filename}")

            existing_tables = connection.execute(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'synergia' AND table_type = 'BASE TABLE'
                """
            ).fetchone()[0]
            requested = os.environ.get("MIGRATION_BASELINE_THROUGH", "").strip()
            if requested:
                if applied:
                    raise RuntimeError(
                        "baseline adoption requires an empty migration history"
                    )
                if not existing_tables:
                    raise RuntimeError("cannot baseline an empty synergia schema")
                baseline_index = resolve_baseline(files, requested)
                baseline = files[: baseline_index + 1]
                validate_baseline(connection, baseline)
                print(
                    f"baseline validated through {requested}; "
                    f"recording {len(baseline)} migrations",
                    flush=True,
                )
                with connection.transaction():
                    for migration in baseline:
                        connection.execute(
                            """
                            INSERT INTO public.synergia_schema_migrations
                                (filename, sha256) VALUES (%s, %s)
                            """,
                            (migration.name, digests[migration.name]),
                        )
                applied = {item.name: digests[item.name] for item in baseline}
            elif existing_tables and not applied:
                raise RuntimeError(
                    "legacy synergia schema detected without migration history; "
                    "set MIGRATION_BASELINE_THROUGH to the exact last migration "
                    "already present"
                )

            for migration in files:
                if migration.name in applied:
                    print(f"skip {migration.name}", flush=True)
                    continue
                print(f"apply {migration.name}", flush=True)
                with connection.transaction():
                    connection.execute(
                        migration.read_text(encoding="utf-8"), prepare=False
                    )
                    connection.execute(
                        """
                        INSERT INTO public.synergia_schema_migrations
                            (filename, sha256) VALUES (%s, %s)
                        """,
                        (migration.name, digests[migration.name]),
                    )
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


if __name__ == "__main__":
    main()
