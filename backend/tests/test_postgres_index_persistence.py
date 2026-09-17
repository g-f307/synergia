from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from benchmark_postgres_workorder_index import _write_probe  # noqa: E402


def test_rule_evaluations_workorder_index_matches_consolidated_access() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        row = connection.execute(
            """
            SELECT i.indisvalid, i.indisready,
                   pg_get_indexdef(i.indexrelid) AS definition
            FROM pg_index i
            WHERE i.indexrelid =
                'synergia.idx_rule_evaluations_workorder_execution_id'::regclass
            """
        ).fetchone()
        previous = connection.execute(
            "SELECT to_regclass('synergia.idx_rule_evaluations_execution_rule')"
        ).fetchone()[0]
        relationship = connection.execute(
            """
            SELECT count(*) FROM pg_constraint
            WHERE conrelid = 'synergia.rule_evaluations'::regclass
              AND contype = 'f'
              AND pg_get_constraintdef(oid) LIKE
                  'FOREIGN KEY (workorder_id, execution_id)%'
            """
        ).fetchone()[0]
    assert row[0] is True
    assert row[1] is True
    assert "(workorder_id, execution_id, id)" in row[2]
    assert previous is not None
    assert relationship == 1


def test_synthetic_index_write_probe_rolls_back_all_fixture_rows() -> None:
    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        before = [
            connection.execute(f"SELECT count(*) FROM synergia.{table}").fetchone()[0]
            for table in (
                "executions",
                "source_files",
                "workorders",
                "rule_evaluations",
            )
        ]
    sample = _write_probe(database_url, 10)
    with psycopg.connect(database_url) as connection:
        after = [
            connection.execute(f"SELECT count(*) FROM synergia.{table}").fetchone()[0]
            for table in (
                "executions",
                "source_files",
                "workorders",
                "rule_evaluations",
            )
        ]
    assert sample["rows"] == 10
    assert sample["wal_records"] > 0
    assert after == before
