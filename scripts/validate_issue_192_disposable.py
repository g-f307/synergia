#!/usr/bin/env python3
"""Validação segura de migrations, rollback e reconciliação PostgreSQL/Graylog (#192)."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "database" / "migrations"
ROLLBACKS_DIR = ROOT / "database" / "rollbacks"
DEFAULT_PROJECT = "synergia-issue-192"
DISPOSABLE_DB_RE = re.compile(r"^synergia_issue_192_[a-z0-9_]+$")

AI_ASSISTANCE_ROLLBACKS = (
    "0040_add_ai_assistance_observability.down.sql",
    "0039_create_ai_assistance_rate_attempts.down.sql",
    "0038_create_ai_assistance_persistence.down.sql",
    "0037_create_ai_assistance_permissions.down.sql",
)


class _RollbackProbeDone(Exception):
    pass


def validate_disposable_database_url(database_url: str) -> str:
    env_name = os.getenv("SYNERGIA_ENV", "test").strip().lower()
    if env_name in {"production", "homologation"}:
        raise ValueError("Recusado: ambiente não descartável para runner da #192")
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError("Recusado: esquema de banco inválido")
    dbname = parsed.path.lstrip("/")
    if not DISPOSABLE_DB_RE.fullmatch(dbname):
        raise ValueError(
            "Recusado: nome do banco deve seguir synergia_issue_192_<sufixo>"
        )
    return dbname


def ensure_empty_disposable_database(conn: psycopg.Connection, expected_db: str) -> None:
    current_db = conn.execute("SELECT current_database()").fetchone()[0]
    if current_db != expected_db:
        raise ValueError("Recusado: current_database() diverge do nome descartável")
    has_schema = conn.execute(
        "SELECT to_regnamespace('synergia') IS NOT NULL"
    ).fetchone()[0]
    if has_schema:
        raise ValueError("Recusado: banco descartável já possui schema synergia")


def validate_migrations_and_rollback(database_url: str) -> dict:
    dbname = validate_disposable_database_url(database_url)
    with psycopg.connect(database_url) as conn:
        ensure_empty_disposable_database(conn, dbname)

    env = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "apply_migrations.py")],
        env=env,
        check=True,
    )

    rolled_back: list[str] = []
    with psycopg.connect(database_url) as conn:
        ledger_before = conn.execute(
            "SELECT count(*) FROM public.synergia_schema_migrations"
        ).fetchone()[0]
        # Execute rollbacks in a rolled-back transaction so the ledger stays intact.
        try:
            with conn.transaction():
                for name in AI_ASSISTANCE_ROLLBACKS:
                    rb_path = ROLLBACKS_DIR / name
                    conn.execute(rb_path.read_text(encoding="utf-8"))
                    rolled_back.append(name)
                raise _RollbackProbeDone
        except _RollbackProbeDone:
            pass
        ledger_after = conn.execute(
            "SELECT count(*) FROM public.synergia_schema_migrations"
        ).fetchone()[0]
    if ledger_after != ledger_before:
        raise ValueError("Ledger de migrations inconsistente após ensaio de rollback")

    return {
        "schema_version": "1.2.0",
        "issue": 192,
        "project": DEFAULT_PROJECT,
        "database_name": dbname,
        "executed_at": datetime.now(UTC).isoformat(),
        "applied_count": ledger_before,
        "rolled_back_verified": rolled_back,
        "ledger_count_after": ledger_after,
        "status": "passed",
    }


def reconcile_correlation_sets(
    pg_events: list[tuple[str, str]], graylog_messages: list[dict]
) -> dict:
    """Compare exact sets/multiplicities of (event_id, action) by correlation_id."""
    pg_counter = Counter((str(eid), str(action)) for eid, action in pg_events)
    gl_pairs = [
        (str(msg.get("event_id", "")), str(msg.get("action", "")))
        for msg in graylog_messages
    ]
    gl_counter = Counter(gl_pairs)

    duplicates_in_gl = sorted(
        pair for pair, count in gl_counter.items() if count > 1
    )
    missing_in_gl = sorted(set(pg_counter.keys()) - set(gl_counter.keys()))
    extra_in_gl = sorted(set(gl_counter.keys()) - set(pg_counter.keys()))
    matched = (
        bool(pg_counter)
        and not duplicates_in_gl
        and not missing_in_gl
        and not extra_in_gl
        and pg_counter == gl_counter
    )
    return {
        "postgres_count": sum(pg_counter.values()),
        "graylog_count": sum(gl_counter.values()),
        "missing_in_graylog": missing_in_gl,
        "extra_in_graylog": extra_in_gl,
        "duplicates_in_graylog": duplicates_in_gl,
        "matched": matched,
    }


def reconcile_correlation_id(
    database_url: str, correlation_id: UUID, graylog_messages: list[dict]
) -> dict:
    validate_disposable_database_url(database_url)
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT id::text, action
            FROM synergia.audit_event_catalog
            WHERE correlation_id = %s
            ORDER BY id
            """,
            (correlation_id,),
        ).fetchall()
    filtered_gl = [
        msg
        for msg in graylog_messages
        if str(msg.get("correlation_id", "")) == str(correlation_id)
    ]
    report = reconcile_correlation_sets(rows, filtered_gl)
    report["correlation_id"] = str(correlation_id)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = validate_migrations_and_rollback(args.database_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
