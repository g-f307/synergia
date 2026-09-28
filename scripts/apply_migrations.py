from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "database" / "migrations"
LOCK_ID = 7_347_319_119


def enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        raise SystemExit(f"no migrations found in {MIGRATIONS}")

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

            existing_tables = connection.execute(
                """
                SELECT count(*)
                FROM information_schema.tables
                WHERE table_schema = 'synergia'
                  AND table_type = 'BASE TABLE'
                """
            ).fetchone()[0]
            pending = [
                migration for migration in files if migration.name not in applied
            ]
            if pending and existing_tables and enabled("MIGRATION_BASELINE_EXISTING"):
                print(
                    f"baseline existing schema with {existing_tables} tables; "
                    f"recording {len(pending)} migrations",
                    flush=True,
                )
                with connection.transaction():
                    for migration in pending:
                        digest = hashlib.sha256(migration.read_bytes()).hexdigest()
                        connection.execute(
                            """
                            INSERT INTO public.synergia_schema_migrations
                                (filename, sha256)
                            VALUES (%s, %s)
                            """,
                            (migration.name, digest),
                        )
                return

            for migration in files:
                contents = migration.read_bytes()
                digest = hashlib.sha256(contents).hexdigest()
                previous = applied.get(migration.name)
                if previous:
                    if previous != digest:
                        raise RuntimeError(
                            f"published migration changed: {migration.name}"
                        )
                    print(f"skip {migration.name}", flush=True)
                    continue

                print(f"apply {migration.name}", flush=True)
                with connection.transaction():
                    connection.execute(contents.decode("utf-8"), prepare=False)
                    connection.execute(
                        """
                        INSERT INTO public.synergia_schema_migrations (filename, sha256)
                        VALUES (%s, %s)
                        """,
                        (migration.name, digest),
                    )
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


if __name__ == "__main__":
    main()
