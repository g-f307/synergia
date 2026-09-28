from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "database" / "migrations"
LOCK_ID = 7_347_319_119

BASELINE_PROBES = {
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
}


def object_exists(
    connection: psycopg.Connection, kind: str, parent: str, name: str
) -> bool:
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


def validate_baseline(
    connection: psycopg.Connection, migrations: list[Path]
) -> None:
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
