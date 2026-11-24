"""Measure #196 on the reusable 50k-snapshot synthetic #195 distribution."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.execution_filters import ExecutionQueryFilters  # noqa: E402
from app.queries import PostgresQueryRepository  # noqa: E402
from app.workorder_indicators import read_current_workorder_indicators  # noqa: E402
from app.workorder_snapshots import workorder_snapshot_query  # noqa: E402

try:
    from bootstrap_indicator_coverage_e2e import configuration
    from measure_workorder_queries import ORGANIZATIONS, measure, seed
except ModuleNotFoundError:
    from scripts.bootstrap_indicator_coverage_e2e import configuration
    from scripts.measure_workorder_queries import ORGANIZATIONS, measure, seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = configuration()
    with psycopg.connect(url, row_factory=dict_row) as c:
        seed(c)
        c.execute(
            "UPDATE synergia.workorders SET planned_quantity="
            "CASE WHEN right(workorder_number,1)::int < 3 THEN NULL ELSE 4 END, "
            "received_quantity=0,released_quantity="
            "CASE WHEN right(workorder_number,1)::int < 3 THEN NULL ELSE 0 END"
        )
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("VACUUM ANALYZE synergia.workorders")
    quantities = ("planned", "produced", "received", "released")
    suffix = " SELECT count(*) AS total_count, "
    suffix += "count(*) FILTER (WHERE partially_released) AS partially_released, "
    suffix += (
        ", ".join(
            f"sum({q}_quantity), count(*) FILTER (WHERE {q}_quantity IS NOT NULL)"
            for q in quantities
        )
        + " FROM workorder_snapshots"
    )
    results = {}
    scenarios = (
        ("organization_a", frozenset([ORGANIZATIONS[0]]), None),
        ("global", None, None),
        (
            "period_a",
            frozenset([ORGANIZATIONS[0]]),
            ExecutionQueryFilters(date_to=datetime(2026, 10, 2, tzinfo=UTC)),
        ),
    )
    repository = PostgresQueryRepository(url)
    with psycopg.connect(url, row_factory=dict_row) as c:
        postgres = c.execute("SHOW server_version").fetchone()["server_version"]
        work_mem = c.execute("SHOW work_mem").fetchone()["work_mem"]
        for name, scopes, filters in scenarios:
            selected = workorder_snapshot_query(
                organization_scopes=scopes, filters=filters, view="current"
            )
            current = read_current_workorder_indicators(
                c, organization_scopes=scopes, filters=filters
            )
            assert current.total == (10000 if scopes is None else 5000)
            assert current.quantities_coverage["planned"].state == "partial"
            assert current.quantities_coverage["received"].state == "complete"
            assert current.quantities_coverage["produced"].state == (
                "complete" if filters else "missing"
            )
            results[name] = {
                "current_total": current.total,
                "aggregate": measure(c, selected, suffix),
                "list_count": measure(
                    c, selected, " SELECT count(*) FROM workorder_snapshots"
                ),
                "list_page": measure(
                    c,
                    selected,
                    " SELECT s.workorder_number AS identifier,s.processing_status AS status,"
                    "e.started_at AS occurred_at,s.snapshot_id,s.execution_id,s.organization_id,"
                    "s.organization_name,s.organization_code,s.updated_at FROM workorder_snapshots s "
                    "JOIN synergia.executions e ON e.id=s.execution_id "
                    "ORDER BY s.updated_at DESC,s.snapshot_id DESC LIMIT 25 OFFSET 0",
                ),
            }
            samples = []
            for _ in range(6):
                start = perf_counter()
                result = repository.indicators(scopes, execution_filters=filters)
                samples.append((perf_counter() - start) * 1000)
                assert result["workorders_current"]["total"] == current.total
            results[name]["repository_including_legacy"] = {
                "warm_samples_ms": samples[1:],
                "median_ms": statistics.median(samples[1:]),
            }
    output = {
        "issue": 196,
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "revision": "uncommitted issue-196 worktree, identified by source_sha256",
        "postgres": postgres,
        "work_mem": work_mem,
        "fixture": {
            "source": "scripts/measure_workorder_queries.py:seed (#195)",
            "snapshots": 50000,
            "organizations": 2,
            "versions": 5,
            "numbers_per_organization": 5000,
            "latest_produced": "missing; period selects a complete older version",
            "planned_released": "70% informed, including known released zero",
            "received": "complete known zero",
        },
        "method": "one warmup + five warm samples; SQL EXPLAIN ANALYZE BUFFERS; repository wall time includes connection, legacy and current reads; no concurrent load",
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "backend/app/workorder_snapshots.py",
                "backend/app/workorder_indicators.py",
                "backend/app/queries.py",
                "scripts/measure_indicator_coverage.py",
                "scripts/measure_workorder_queries.py",
            )
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    for name, operations in results.items():
        print(
            name,
            {
                key: round(value["median_ms"], 3)
                for key, value in operations.items()
                if isinstance(value, dict)
            },
        )


if __name__ == "__main__":
    main()
