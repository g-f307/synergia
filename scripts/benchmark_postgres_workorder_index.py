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
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.queries import PostgresQueryRepository  # noqa: E402

INDEX_NAME = "synergia.idx_rule_evaluations_workorder_execution_id"


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * fraction) - 1]


def _catalog_state(database_url: str) -> tuple[bool, int]:
    with psycopg.connect(database_url) as connection:
        present = connection.execute(
            "SELECT to_regclass(%s) IS NOT NULL", (INDEX_NAME,)
        ).fetchone()[0]
        total = connection.execute(
            "SELECT count(*) FROM synergia.rule_evaluations"
        ).fetchone()[0]
    return present, total


def _git_value(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "not_available"


def _read_probe(
    database_url: str,
    execution_id: str,
    organization_id: UUID,
    workorder_number: str,
) -> tuple[float, str, int]:
    repository = PostgresQueryRepository(database_url)
    started = time.perf_counter_ns()
    result = repository.get_consolidated(
        workorder_number, execution_id, frozenset({organization_id})
    )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    if result is None:
        raise ValueError("Consolidado sintético não encontrado no escopo")
    payload = json.dumps(result, sort_keys=True, ensure_ascii=False, default=str)
    return elapsed_ms, hashlib.sha256(payload.encode()).hexdigest(), len(payload)


def _write_probe(database_url: str, rows: int) -> dict:
    """Measure a synthetic INSERT, then roll the entire fixture back."""
    execution_id = f"exec-index-probe-{uuid4().hex}"
    digest = hashlib.sha256(execution_id.encode()).hexdigest()
    with psycopg.connect(database_url) as connection:
        try:
            connection.execute(
                "INSERT INTO synergia.executions (id, status, source) "
                "VALUES (%s, 'pending', 'N-FP')",
                (execution_id,),
            )
            source_file_id = connection.execute(
                "INSERT INTO synergia.source_files "
                "(execution_id, source, file_name, content_hash) "
                "VALUES (%s, 'N-FP', 'synthetic-probe.csv', %s) RETURNING id",
                (execution_id, digest),
            ).fetchone()[0]
            workorder_id = connection.execute(
                "INSERT INTO synergia.workorders "
                "(workorder_number, execution_id, source_file_id, "
                "processing_status) "
                "VALUES (%s, %s, %s, 'consolidated') RETURNING id",
                (f"WO-INDEX-PROBE-{uuid4().hex}", execution_id, source_file_id),
            ).fetchone()[0]
            document = connection.execute(
                """
                EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS, FORMAT JSON)
                INSERT INTO synergia.rule_evaluations
                    (execution_id, workorder_id, rule_id,
                     rule_catalog_version, result, justification)
                SELECT %s, %s, 'synthetic_probe', '1.0.0',
                       'not_matched', 'Synthetic write probe'
                FROM generate_series(1, %s)
                """,
                (execution_id, workorder_id, rows),
            ).fetchone()[0][0]
        finally:
            connection.rollback()
    return {
        "execution_ms": document["Execution Time"],
        "wal_records": document["Plan"].get("WAL Records", 0),
        "wal_bytes": document["Plan"].get("WAL Bytes", 0),
        "shared_dirtied_blocks": document["Plan"].get("Shared Dirtied Blocks", 0),
        "rows": rows,
        "plan": document,
    }


def benchmark(args: argparse.Namespace) -> dict:
    database_url = os.environ["DATABASE_URL"]
    manifest = json.loads(args.mass_manifest.read_text(encoding="utf-8"))
    environment = json.loads(args.baseline_environment.read_text(encoding="utf-8"))
    if manifest["logical_digest"] != environment["mass"]["logical_digest"]:
        raise ValueError("Ambiente e manifesto divergem")
    workorder_number = manifest["expectations"]["query_samples"]["organizations"][
        args.organization_code
    ]["workorders"]["median"]
    present, count_before = _catalog_state(database_url)
    if present != (args.index_state == "present"):
        raise ValueError("Estado do índice não corresponde à fase declarada")
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Diretório de saída deve estar vazio")
    output_dir.mkdir(parents=True, exist_ok=True)
    read_samples = []
    digests = set()
    for index in range(args.warmups + args.repetitions):
        duration, digest, payload_bytes = _read_probe(
            database_url,
            args.execution_id,
            UUID(args.organization_id),
            workorder_number,
        )
        digests.add(digest)
        if index >= args.warmups:
            read_samples.append(
                {
                    "duration_ms": duration,
                    "payload_bytes": payload_bytes,
                    "digest": digest,
                }
            )
    if len(digests) != 1:
        raise ValueError("Consolidado variou durante as amostras")
    write_samples = []
    for index in range(args.warmups + args.repetitions):
        sample = _write_probe(database_url, args.write_rows)
        if index >= args.warmups:
            write_samples.append(sample)
    _, count_after = _catalog_state(database_url)
    if count_after != count_before:
        raise ValueError("Sonda de escrita deixou linhas persistidas")
    with psycopg.connect(database_url) as connection:
        postgres = connection.execute(
            "SELECT version(), current_setting('shared_buffers'), "
            "current_setting('max_connections')"
        ).fetchone()
        index_bytes = connection.execute(
            "SELECT CASE WHEN to_regclass(%s) IS NULL THEN 0 "
            "ELSE pg_relation_size(to_regclass(%s)) END",
            (INDEX_NAME, INDEX_NAME),
        ).fetchone()[0]
    read_values = [item["duration_ms"] for item in read_samples]
    write_values = [item["execution_ms"] for item in write_samples]
    result = {
        "captured_at": datetime.now(UTC).isoformat(),
        "run_id": args.run_id,
        "phase": args.index_state,
        "execution_id": args.execution_id,
        "organization_id": args.organization_id,
        "workorder_number": workorder_number,
        "mass_manifest": manifest,
        "baseline_environment": environment,
        "warmups": args.warmups,
        "repetitions": args.repetitions,
        "index_present": present,
        "index_bytes": index_bytes,
        "commit": _git_value("rev-parse", "HEAD"),
        "worktree": "dirty" if _git_value("status", "--porcelain") else "clean",
        "host": {
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "python": sys.version.split()[0],
            "disk_free_bytes": shutil.disk_usage(output_dir).free,
        },
        "postgres": {
            "version": postgres[0],
            "shared_buffers": postgres[1],
            "max_connections": postgres[2],
        },
        "rule_evaluations_before": count_before,
        "rule_evaluations_after": count_after,
        "read": {
            "p50_ms": _percentile(read_values, 0.50),
            "p95_ms": _percentile(read_values, 0.95),
            "p99_ms": _percentile(read_values, 0.99),
            "digest": next(iter(digests)),
            "samples": read_samples,
        },
        "write": {
            "rows_per_sample": args.write_rows,
            "p50_ms": _percentile(write_values, 0.50),
            "p95_ms": _percentile(write_values, 0.95),
            "p99_ms": _percentile(write_values, 0.99),
            "samples": write_samples,
        },
        "comparability": "non_comparable",
    }
    (output_dir / "run.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mede consolidado e INSERT sintético com/sem índice"
    )
    parser.add_argument("--index-state", choices=("absent", "present"), required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--organization-code", required=True)
    parser.add_argument("--mass-manifest", type=Path, required=True)
    parser.add_argument("--baseline-environment", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--write-rows", type=int, default=1000)
    args = parser.parse_args()
    if args.warmups < 0 or args.repetitions < 1 or args.write_rows < 1:
        parser.error("Aquecimento, repetições ou linhas inválidos")
    if not os.getenv("DATABASE_URL"):
        parser.error("DATABASE_URL é obrigatório")
    result = benchmark(args)
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "read_p95_ms": result["read"]["p95_ms"],
                "write_p95_ms": result["write"]["p95_ms"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
