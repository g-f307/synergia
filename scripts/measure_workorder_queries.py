"""Measure #195 SQL on a reproducible, synthetic PostgreSQL 16 fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.execution_filters import ExecutionQueryFilters  # noqa: E402
from app.workorder_snapshots import workorder_snapshot_query  # noqa: E402

try:
    from bootstrap_workorder_versions_e2e import configuration
except ModuleNotFoundError:
    from scripts.bootstrap_workorder_versions_e2e import configuration

ORGANIZATIONS = [UUID(f"19500000-0000-4000-8000-{n:012d}") for n in (101, 102)]


def seed(connection):
    if connection.execute(
        "SELECT EXISTS (SELECT 1 FROM synergia.workorders "
        "WHERE execution_id NOT LIKE 'perf195-%') AS contaminated"
    ).fetchone()["contaminated"]:
        raise ValueError("Benchmark requires a dedicated empty or perf195-only DB")
    for tenant, organization in enumerate(ORGANIZATIONS):
        connection.execute(
            "INSERT INTO synergia.iam_organizations "
            "(id,organization_code,display_name) VALUES (%s,%s,'Synthetic perf') "
            "ON CONFLICT DO NOTHING",
            (organization, f"perf195-{tenant}"),
        )
        for version in range(5):
            execution = f"perf195-{tenant}-{version}"
            row = connection.execute(
                "INSERT INTO synergia.executions "
                "(id,organization_id,status,source,started_at) "
                "VALUES (%s,%s,'completed','OWM',%s) "
                "ON CONFLICT DO NOTHING RETURNING id",
                (execution, organization, datetime(2026, 10, version + 1, tzinfo=UTC)),
            ).fetchone()
            if not row:
                continue
            source = connection.execute(
                "INSERT INTO synergia.source_files "
                "(execution_id,file_name,content_hash,source) "
                "VALUES (%s,'synthetic.json',%s,'OWM') RETURNING id",
                (execution, hashlib.sha256(execution.encode()).hexdigest()),
            ).fetchone()["id"]
            business = connection.execute(
                "INSERT INTO synergia.organizations "
                "(organization_code,execution_id,source_file_id) "
                "VALUES ('SAME-WORKBOOK-CODE',%s,%s) RETURNING id",
                (execution, source),
            ).fetchone()["id"]
            connection.execute(
                "INSERT INTO synergia.workorders "
                "(workorder_number,organization_id,execution_id,source_file_id,"
                "processing_status,updated_at,produced_quantity) "
                "SELECT 'PERF-' || lpad(n::text,5,'0'),%s,%s,%s,'consolidated',"
                "%s,CASE WHEN %s=4 THEN NULL ELSE 20 END "
                "FROM generate_series(1,5000) n",
                (
                    business,
                    execution,
                    source,
                    datetime(2026, 10, version + 1, tzinfo=UTC),
                    version,
                ),
            )
    count = connection.execute(
        "SELECT count(*) AS total FROM synergia.workorders"
    ).fetchone()["total"]
    if count != 50000:
        raise ValueError("Benchmark fixture must contain exactly 50000 snapshots")
    for table in ("executions", "workorders", "organizations", "iam_organizations"):
        connection.execute("ANALYZE synergia." + table)


def measure(connection, query, suffix):
    samples = []
    last_plan = None
    for _ in range(6):
        last_plan = connection.execute(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query.cte + suffix,
            query.parameters,
        ).fetchone()["QUERY PLAN"][0]
        samples.append(last_plan["Execution Time"])
    return {
        "warm_samples_ms": samples[1:],
        "median_ms": statistics.median(samples[1:]),
        "plan": last_plan,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with psycopg.connect(configuration(), row_factory=dict_row) as connection:
        seed(connection)
    a, b = ORGANIZATIONS
    scenarios = [
        ("exact_current_a", frozenset([a]), "current", "PERF-02500", None),
        ("exact_history_a", frozenset([a]), "history", "PERF-02500", None),
        ("exact_current_ab", frozenset([a, b]), "current", "PERF-02500", None),
        (
            "period_current_a",
            frozenset([a]),
            "current",
            "PERF-02500",
            ExecutionQueryFilters(date_to=datetime(2026, 10, 2, tzinfo=UTC)),
        ),
        (
            "pinned_old_a",
            frozenset([a]),
            "current",
            "PERF-02500",
            ExecutionQueryFilters(execution_id="perf195-0-0"),
        ),
        ("future_aggregate_a", frozenset([a]), "current", None, None),
        ("future_aggregate_global", None, "current", None, None),
    ]
    results = {}
    with psycopg.connect(configuration(), row_factory=dict_row) as connection:
        version = connection.execute("SHOW server_version").fetchone()["server_version"]
        work_mem = connection.execute("SHOW work_mem").fetchone()["work_mem"]
        for name, scopes, view, number, filters in scenarios:
            query = workorder_snapshot_query(
                organization_scopes=scopes,
                view=view,
                workorder_number=number,
                filters=filters,
            )
            if number is None:
                results[name] = {
                    "aggregate": measure(
                        connection,
                        query,
                        " SELECT count(*),sum(produced_quantity) "
                        "FROM workorder_snapshots",
                    )
                }
            else:
                results[name] = {
                    "count": measure(
                        connection, query, " SELECT count(*) FROM workorder_snapshots"
                    ),
                    "page": measure(
                        connection,
                        query,
                        " SELECT * FROM workorder_snapshots ORDER BY updated_at DESC,"
                        + (
                            "execution_id DESC, snapshot_id DESC LIMIT 25 OFFSET 0"
                            if view == "history"
                            else "snapshot_id DESC LIMIT 25 OFFSET 0"
                        ),
                    ),
                }
    output = {
        "scenario": "issue-195-synthetic-50k",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "revision": "uncommitted issue-195 code, identified by code_sha256",
        "work_mem": work_mem,
        "postgres": version,
        "fixture": {
            "organizations": 2,
            "executions": 10,
            "workorders_per_organization": 5000,
            "versions": 5,
            "snapshots": 50000,
        },
        "method": "one warmup + five warm samples, EXPLAIN ANALYZE BUFFERS",
        "code_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("backend/app/workorder_snapshots.py", "backend/app/queries.py")
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    for name, operations in results.items():
        print(
            name,
            {
                operation: round(value["median_ms"], 3)
                for operation, value in operations.items()
            },
        )


if __name__ == "__main__":
    main()
