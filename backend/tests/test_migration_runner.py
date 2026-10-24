from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((ROOT / "database" / "migrations").glob("*.sql"))
RUNNER = ROOT / "scripts" / "apply_migrations.py"

pytestmark = pytest.mark.integration


@pytest.fixture
def migration_database():
    name = f"synergia_migration_{uuid.uuid4().hex}"
    with psycopg.connect("", dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield name
    finally:
        with psycopg.connect("", dbname="postgres", autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (name,),
            )
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


def runner_environment(database: str, baseline: str | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment["PGDATABASE"] = database
    if baseline:
        environment["MIGRATION_BASELINE_THROUGH"] = baseline
    else:
        environment.pop("MIGRATION_BASELINE_THROUGH", None)
    return environment


def run_migrations(
    database: str, baseline: str | None = None, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER)],
        cwd=ROOT,
        env=runner_environment(database, baseline),
        text=True,
        capture_output=True,
        check=check,
    )


def apply_legacy_schema(database: str, through: int) -> None:
    with psycopg.connect("", dbname=database, autocommit=True) as connection:
        for migration in MIGRATIONS[:through]:
            with connection.transaction():
                connection.execute(migration.read_text(encoding="utf-8"), prepare=False)


def migration_count(database: str) -> int:
    with psycopg.connect("", dbname=database) as connection:
        return connection.execute(
            "SELECT count(*) FROM public.synergia_schema_migrations"
        ).fetchone()[0]


@pytest.mark.parametrize("table", ["executions", "source_files", "file_inspections"])
def test_total_decision_baseline_requires_all_source_constraints(
    migration_database: str,
    table: str,
) -> None:
    index = next(i for i, path in enumerate(MIGRATIONS) if path.name.startswith("0032"))
    apply_legacy_schema(migration_database, index)
    with psycopg.connect("", dbname=migration_database) as connection:
        connection.execute(
            sql.SQL(
                "ALTER TABLE synergia.{} DROP CONSTRAINT {}, "
                "ADD CONSTRAINT {} CHECK (source IN "
                "('N-FP', 'OWM', 'GMES/OQC', 'TMS', 'WO Status', 'Total Decision'))"
            ).format(
                sql.Identifier(table),
                sql.Identifier(f"{table}_source_check"),
                sql.Identifier(f"{table}_source_check"),
            )
        )
    result = run_migrations(migration_database, MIGRATIONS[index].name, check=False)
    assert result.returncode != 0
    assert "partial or incompatible" in result.stderr
    assert migration_count(migration_database) == 0


def test_adopts_completely_legacy_database(migration_database: str) -> None:
    apply_legacy_schema(migration_database, len(MIGRATIONS))

    run_migrations(migration_database, MIGRATIONS[-1].name)

    assert migration_count(migration_database) == len(MIGRATIONS)


@pytest.mark.parametrize("missing", ["provider", "reconciliations"])
def test_smtp_baseline_requires_provider_and_reconciliation_schema(
    migration_database: str, missing: str
) -> None:
    apply_legacy_schema(migration_database, len(MIGRATIONS))
    with psycopg.connect("", dbname=migration_database) as connection:
        if missing == "provider":
            connection.execute(
                "ALTER TABLE synergia.email_deliveries "
                "DROP CONSTRAINT email_deliveries_provider_check, "
                "ADD CONSTRAINT email_deliveries_provider_check "
                "CHECK (provider IN ('local_capture'))"
            )
        else:
            connection.execute("DROP TABLE synergia.email_delivery_reconciliations")
    result = run_migrations(migration_database, MIGRATIONS[-1].name, check=False)
    assert result.returncode != 0
    assert "partial or incompatible" in result.stderr
    assert migration_count(migration_database) == 0


def test_runs_migrations_after_partial_baseline(migration_database: str) -> None:
    baseline_count = 25
    apply_legacy_schema(migration_database, baseline_count)

    result = run_migrations(migration_database, MIGRATIONS[baseline_count - 1].name)

    assert f"apply {MIGRATIONS[baseline_count].name}" in result.stdout
    assert migration_count(migration_database) == len(MIGRATIONS)


def test_rejects_incompatible_partial_baseline(migration_database: str) -> None:
    apply_legacy_schema(migration_database, 24)

    result = run_migrations(migration_database, MIGRATIONS[24].name, check=False)

    assert result.returncode != 0
    assert "partial or incompatible" in result.stderr
    assert migration_count(migration_database) == 0


def test_adoption_notices_a_missing_source_constraint_widening(
    migration_database: str,
) -> None:
    # 0031 only widens a CHECK, so adopting a database that stopped at 0030 as if
    # it had 0031 must be refused by the baseline probe.
    index = next(i for i, m in enumerate(MIGRATIONS) if m.name.startswith("0031"))
    apply_legacy_schema(migration_database, index)

    result = run_migrations(migration_database, MIGRATIONS[index].name, check=False)

    assert result.returncode != 0
    assert "partial or incompatible" in result.stderr
    assert migration_count(migration_database) == 0


@pytest.mark.parametrize(
    "widened",
    [
        ("file_inspections",),
        ("executions",),
        ("source_files",),
        ("executions", "source_files"),
        ("source_files", "file_inspections"),
    ],
)
def test_adoption_requires_every_source_constraint_to_be_widened(
    migration_database: str, widened: tuple[str, ...]
) -> None:
    index = next(i for i, m in enumerate(MIGRATIONS) if m.name.startswith("0031"))
    apply_legacy_schema(migration_database, index)
    with psycopg.connect("", dbname=migration_database) as connection:
        for table in widened:
            name = f"{table}_source_check"
            connection.execute(
                f"ALTER TABLE synergia.{table} DROP CONSTRAINT {name}, "
                f"ADD CONSTRAINT {name} CHECK (source IN "
                "('N-FP', 'OWM', 'GMES/OQC', 'TMS', 'WO Status'))"
            )
        connection.commit()

    result = run_migrations(migration_database, MIGRATIONS[index].name, check=False)

    assert result.returncode != 0
    assert "partial or incompatible" in result.stderr


def test_adoption_accepts_a_fully_widened_database(migration_database: str) -> None:
    apply_legacy_schema(migration_database, len(MIGRATIONS))

    run_migrations(migration_database, MIGRATIONS[-1].name)

    assert migration_count(migration_database) == len(MIGRATIONS)


def test_rejects_checksum_divergence(migration_database: str) -> None:
    run_migrations(migration_database)
    with psycopg.connect("", dbname=migration_database) as connection:
        connection.execute(
            "UPDATE public.synergia_schema_migrations SET sha256 = %s "
            "WHERE filename = %s",
            ("invalid", MIGRATIONS[0].name),
        )
        connection.commit()

    result = run_migrations(migration_database, check=False)

    assert result.returncode != 0
    assert "published migration changed" in result.stderr


def test_serializes_two_concurrent_runs(migration_database: str) -> None:
    command = [sys.executable, str(RUNNER)]
    environment = runner_environment(migration_database)
    first = subprocess.Popen(
        command, cwd=ROOT, env=environment, text=True, stderr=subprocess.PIPE
    )
    second = subprocess.Popen(
        command, cwd=ROOT, env=environment, text=True, stderr=subprocess.PIPE
    )

    assert first.wait(timeout=60) == 0, first.stderr.read()
    assert second.wait(timeout=60) == 0, second.stderr.read()
    assert migration_count(migration_database) == len(MIGRATIONS)
