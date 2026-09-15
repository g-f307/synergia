from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def _git_value(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "not_available"


def _walk(plan: dict) -> list[dict]:
    return [plan, *[node for child in plan.get("Plans", []) for node in _walk(child)]]


def _summarize(document: dict) -> dict:
    plan = document["Plan"]
    nodes = _walk(plan)
    return {
        "execution_ms": document.get("Execution Time"),
        "planning_ms": document.get("Planning Time"),
        "actual_rows": plan.get("Actual Rows"),
        "shared_hit_blocks": plan.get("Shared Hit Blocks", 0),
        "shared_read_blocks": plan.get("Shared Read Blocks", 0),
        "temp_read_blocks": plan.get("Temp Read Blocks", 0),
        "temp_written_blocks": plan.get("Temp Written Blocks", 0),
        "node_types": [node.get("Node Type") for node in nodes],
        "scans": [
            {
                "type": node.get("Node Type"),
                "relation": node.get("Relation Name"),
                "index": node.get("Index Name"),
                "rows": node.get("Actual Rows"),
                "loops": node.get("Actual Loops"),
            }
            for node in nodes
            if "Scan" in str(node.get("Node Type"))
        ],
        "sorts": [
            {
                "method": node.get("Sort Method"),
                "space_kb": node.get("Sort Space Used"),
                "space_type": node.get("Sort Space Type"),
            }
            for node in nodes
            if node.get("Node Type") == "Sort"
        ],
    }


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile) - 1)
    return ordered[index]


def _queries(
    execution_id: str, organization_id: str, samples: dict, reference_at: datetime
) -> list[tuple[str, str, tuple]]:
    workorder = samples["workorders"]["median"]
    lot = samples["lots"]["median"]
    serial = samples["serials"]["median"]
    published = "e.status IN ('completed', 'completed_with_errors')"
    return [
        (
            "workorder_detail",
            f"""
            SELECT w.id, w.workorder_number FROM synergia.workorders w
            JOIN synergia.executions e ON e.id = w.execution_id
            WHERE w.workorder_number = %s AND {published}
              AND e.organization_id = %s
            ORDER BY w.updated_at DESC, w.id DESC LIMIT 1
        """,
            (workorder, organization_id),
        ),
        (
            "lot_detail",
            f"""
            SELECT l.id, l.lot_number FROM synergia.lots l
            JOIN synergia.workorders w ON w.id = l.workorder_id
            JOIN synergia.executions e ON e.id = l.execution_id
            WHERE l.lot_number = %s AND {published}
              AND e.organization_id = %s
            ORDER BY l.updated_at DESC, l.id DESC LIMIT 1
        """,
            (lot, organization_id),
        ),
        (
            "serial_detail",
            f"""
            SELECT s.id, s.serial_number FROM synergia.serials s
            JOIN synergia.workorders w ON w.id = s.workorder_id
            JOIN synergia.executions e ON e.id = s.execution_id
            WHERE s.serial_number = %s AND {published}
              AND e.organization_id = %s
            ORDER BY s.updated_at DESC, s.id DESC LIMIT 1
        """,
            (serial, organization_id),
        ),
        (
            "workorder_serials",
            """
            SELECT s.serial_number FROM synergia.serials s
            JOIN synergia.workorders w ON w.id = s.workorder_id
            JOIN synergia.executions e ON e.id = w.execution_id
            WHERE w.workorder_number = %s AND w.execution_id = %s
              AND e.organization_id = %s
              AND e.status IN ('completed', 'completed_with_errors')
            ORDER BY s.serial_number
            """,
            (workorder, execution_id, organization_id),
        ),
        (
            "search_workorder_count",
            f"""
            SELECT count(*) FROM synergia.workorders w
            JOIN synergia.executions e ON e.id = w.execution_id
            WHERE w.workorder_number = %s AND {published}
              AND e.organization_id = %s
        """,
            (workorder, organization_id),
        ),
        (
            "search_workorder_page",
            f"""
            SELECT w.workorder_number, w.execution_id, w.updated_at
            FROM synergia.workorders w
            JOIN synergia.executions e ON e.id = w.execution_id
            WHERE w.workorder_number = %s AND {published}
              AND e.organization_id = %s
            ORDER BY w.updated_at DESC, w.execution_id DESC, w.id DESC
            LIMIT 25 OFFSET 0
        """,
            (workorder, organization_id),
        ),
        (
            "history_page",
            """
            SELECT a.id, a.event_type, a.occurred_at
            FROM synergia.audit_events a
            JOIN synergia.executions e ON e.id = a.execution_id
            WHERE a.execution_id = %s AND e.organization_id = %s
            ORDER BY a.occurred_at DESC, a.id DESC LIMIT 25 OFFSET 0
        """,
            (execution_id, organization_id),
        ),
        (
            "consolidated_evaluations",
            """
            SELECT r.id, r.rule_id, r.result, r.created_at
            FROM synergia.rule_evaluations r
            JOIN synergia.workorders w ON w.id = r.workorder_id
            WHERE w.workorder_number = %s AND r.execution_id = %s
            ORDER BY r.id
            """,
            (workorder, execution_id),
        ),
        (
            "consolidated_provenance",
            """
            SELECT p.id, p.field_name, p.source_file_id, p.row_number
            FROM synergia.consolidated_field_provenance p
            JOIN synergia.workorders w ON w.id = p.workorder_id
            WHERE w.workorder_number = %s AND p.execution_id = %s
            ORDER BY p.field_name, p.source_file_id, p.row_number, p.id
            """,
            (workorder, execution_id),
        ),
        (
            "consolidated_classifications",
            """
            SELECT c.classification_id, c.rule_id, c.classified_at
            FROM synergia.classifications c
            JOIN synergia.workorders w ON w.id = c.workorder_id
            WHERE w.workorder_number = %s AND c.execution_id = %s
            ORDER BY c.classified_at, c.classification_id
            """,
            (workorder, execution_id),
        ),
        (
            "pending_page",
            f"""
            SELECT p.id, p.status, p.created_at
            FROM synergia.pending_items p
            JOIN synergia.executions e ON e.id = p.execution_id
            WHERE {published} AND e.organization_id = %s
            ORDER BY p.created_at DESC, p.id DESC LIMIT 25 OFFSET 0
        """,
            (organization_id,),
        ),
        (
            "indicator_workorders",
            f"""
            SELECT count(*), count(*) FILTER (WHERE w.partially_released),
                   CASE WHEN count(*) = 0 OR bool_or(w.planned_quantity IS NULL)
                        THEN NULL ELSE sum(w.planned_quantity) END
            FROM synergia.workorders w
            JOIN synergia.executions e ON e.id = w.execution_id
            WHERE {published} AND e.organization_id = %s
        """,
            (organization_id,),
        ),
        (
            "indicator_related_workorders",
            f"""
            SELECT w.workorder_number, e.started_at
            FROM synergia.workorders w
            JOIN synergia.executions e ON e.id = w.execution_id
            WHERE {published} AND e.organization_id = %s
            ORDER BY e.started_at DESC, w.workorder_number DESC
            LIMIT 25 OFFSET 0
        """,
            (organization_id,),
        ),
        (
            "report_workorders",
            """
            SELECT w.workorder_number,
                   coalesce(array_agg(DISTINCT l.lot_number)
                            FILTER (WHERE l.id IS NOT NULL), '{}') AS lots,
                   count(DISTINCT s.id) AS serial_count,
                   count(DISTINCT p.id)
                       FILTER (WHERE p.status = 'open') AS open_pending_count
            FROM synergia.workorders w
            LEFT JOIN synergia.lots l ON l.workorder_id = w.id
              AND l.execution_id = w.execution_id AND l.updated_at <= %s
            LEFT JOIN synergia.serials s ON s.workorder_id = w.id
              AND s.execution_id = w.execution_id AND s.updated_at <= %s
            LEFT JOIN synergia.pending_items p ON p.workorder_id = w.id
              AND p.execution_id = w.execution_id AND p.updated_at <= %s
            WHERE w.execution_id = %s AND w.updated_at <= %s
            GROUP BY w.id ORDER BY w.workorder_number
        """,
            (reference_at, reference_at, reference_at, execution_id, reference_at),
        ),
        (
            "report_oqc",
            """
            SELECT w.workorder_number, l.lot_number, q.decision_state,
                   p.id AS pending_item_id, p.priority_score
            FROM synergia.oqc_decisions q
            JOIN synergia.workorders w ON w.id = q.workorder_id
              AND w.execution_id = q.execution_id
            LEFT JOIN synergia.lots l ON l.id = q.lot_id
              AND l.execution_id = q.execution_id AND l.updated_at <= %s
            LEFT JOIN synergia.pending_items p ON p.workorder_id = q.workorder_id
              AND p.execution_id = q.execution_id
              AND p.lot_id IS NOT DISTINCT FROM q.lot_id
              AND p.serial_id IS NOT DISTINCT FROM q.serial_id
              AND p.updated_at <= %s
            WHERE q.execution_id = %s AND q.updated_at <= %s
            ORDER BY coalesce(p.priority_score, 0) DESC,
                     w.workorder_number, l.lot_number
        """,
            (reference_at, reference_at, execution_id, reference_at),
        ),
    ]


def collect(args: argparse.Namespace) -> dict:
    manifest_path = args.mass_manifest.resolve(strict=True)
    baseline_path = args.baseline_environment.resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if manifest.get("logical_digest") != baseline.get("mass", {}).get("logical_digest"):
        raise ValueError("Manifesto e descrição da baseline divergem")
    if baseline.get("organization_id") not in {None, args.organization_id}:
        raise ValueError("Organização da baseline diverge")
    expected = manifest["entities"]
    samples = manifest["expectations"]["query_samples"]["organizations"][
        args.organization_code
    ]
    reference_at = datetime.now(UTC)
    database_url = os.environ["DATABASE_URL"]
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Diretório de saída deve estar vazio")
    output_dir.mkdir(parents=True, exist_ok=True)
    plans = []
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '30s'")
        info = connection.execute(
            "SELECT version() AS version, current_setting('shared_buffers') "
            "AS shared_buffers, current_setting('max_connections') "
            "AS max_connections"
        ).fetchone()
        execution = connection.execute(
            "SELECT status, organization_id FROM synergia.executions WHERE id = %s",
            (args.execution_id,),
        ).fetchone()
        if (
            execution is None
            or execution["status"] not in {"completed", "completed_with_errors"}
            or str(execution["organization_id"]) != args.organization_id
        ):
            raise ValueError("Execução/escopo não correspondem à massa")
        counts = {}
        for table in (
            "workorders",
            "lots",
            "serials",
            "oqc_decisions",
            "pending_items",
            "audit_events",
            "rule_evaluations",
            "consolidated_field_provenance",
            "classifications",
        ):
            counts[table] = connection.execute(
                f"SELECT count(*) AS total FROM synergia.{table} "
                "WHERE execution_id = %s",
                (args.execution_id,),
            ).fetchone()["total"]
        for table in ("workorders", "lots", "serials"):
            if counts[table] != expected[table]:
                raise ValueError(f"Cardinalidade {table} diverge do manifesto")
        for name, sql, parameters in _queries(
            args.execution_id, args.organization_id, samples, reference_at
        ):
            samples_for_query = []
            for index in range(args.warmups + args.repetitions):
                document = connection.execute(
                    "EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON) " + sql,
                    parameters,
                ).fetchone()["QUERY PLAN"][0]
                if index < args.warmups:
                    continue
                item = {
                    "name": name,
                    "sample": index - args.warmups + 1,
                    "sql": sql.strip(),
                    "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
                    "parameters": [str(value) for value in parameters],
                    "plan": document,
                    "summary": _summarize(document),
                }
                (output_dir / f"{name}-{item['sample']:02d}.json").write_text(
                    json.dumps(item, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8",
                )
                samples_for_query.append(item["summary"])
            latencies = [float(item["execution_ms"]) for item in samples_for_query]
            plans.append(
                {
                    "name": name,
                    "samples": len(latencies),
                    "execution_ms": {
                        "min": min(latencies),
                        "p50": _nearest_rank(latencies, 0.50),
                        "p95": _nearest_rank(latencies, 0.95),
                        "p99": _nearest_rank(latencies, 0.99),
                        "max": max(latencies),
                    },
                    "shared_hit_blocks_max": max(
                        item["shared_hit_blocks"] for item in samples_for_query
                    ),
                    "shared_read_blocks_max": max(
                        item["shared_read_blocks"] for item in samples_for_query
                    ),
                    "temp_written_blocks_max": max(
                        item["temp_written_blocks"] for item in samples_for_query
                    ),
                    "scans": samples_for_query[-1]["scans"],
                    "sorts": samples_for_query[-1]["sorts"],
                }
            )
    run = {
        "captured_at": datetime.now(UTC).isoformat(),
        "run_id": args.run_id,
        "cache_label": args.cache_label,
        "warmups": args.warmups,
        "repetitions": args.repetitions,
        "comparability": "non_comparable"
        if baseline.get("worktree") != "clean"
        or _git_value("status", "--porcelain")
        or "PostgreSQL 16" not in info["version"]
        else "comparable",
        "commit": _git_value("rev-parse", "HEAD"),
        "worktree": "dirty" if _git_value("status", "--porcelain") else "clean",
        "execution_id": args.execution_id,
        "organization_id": args.organization_id,
        "organization_code": args.organization_code,
        "postgres": dict(info),
        "host": {
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "python": sys.version.split()[0],
            "disk_free_bytes": shutil.disk_usage(output_dir).free,
        },
        "baseline_environment": baseline,
        "mass_manifest": manifest,
        "mass_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "mass_logical_digest": manifest["logical_digest"],
        "execution_counts": counts,
        "global_counts": "mixed database; plans filtered by execution/org as noted",
        "reference_at": reference_at.isoformat(),
        "plans": plans,
    }
    (output_dir / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return run


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Coleta EXPLAIN JSON de consultas críticas com massa sintética"
    )
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--organization-code", required=True)
    parser.add_argument("--mass-manifest", type=Path, required=True)
    parser.add_argument("--baseline-environment", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--cache-label", choices=("cold", "warm", "mixed"), default="mixed"
    )
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    if args.warmups < 0 or args.repetitions < 1:
        parser.error("--warmups >= 0 e --repetitions >= 1")
    if not os.getenv("DATABASE_URL"):
        parser.error("DATABASE_URL é obrigatório")
    run = collect(args)
    print(
        json.dumps(
            {
                "run_id": run["run_id"],
                "plans": len(run["plans"]),
                "comparability": run["comparability"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
