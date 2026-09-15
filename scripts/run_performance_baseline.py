from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from generate_synthetic_data import CANONICAL_FORMATS, validate_manifest

REQUIRED_ENVIRONMENT_METADATA = {
    "backend_limits",
    "container_runtime",
    "network_topology",
    "postgres_limits",
    "resource_collection",
    "storage_type",
}
RESOURCE_FIELDS = (
    "timestamp",
    "target",
    "cpu_seconds",
    "rss_bytes",
    "read_bytes",
    "write_bytes",
    "load_1m",
    "memory_available_bytes",
    "disk_free_bytes",
    "db_connections",
    "db_active",
    "db_waiting",
    "db_commits",
    "db_rollbacks",
    "db_blocks_read",
    "db_blocks_hit",
    "db_temp_files",
    "db_temp_bytes",
    "db_deadlocks",
    "collection_error",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not_available"


def _git_value(*arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "not_available"


def _memory_total() -> int | str:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return "not_available"


def parse_metadata(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key.strip() or not item.strip():
            raise ValueError(f"Metadado inválido: {value!r}; use chave=valor")
        result[key.strip()] = item.strip()
    return dict(sorted(result.items()))


def collect_environment(
    environment_name: str,
    bundle: Path,
    manifest: dict[str, Any],
    metadata: dict[str, str],
) -> dict[str, Any]:
    disk = shutil.disk_usage(bundle)
    missing = sorted(REQUIRED_ENVIRONMENT_METADATA - metadata.keys())
    status = _git_value("status", "--porcelain")
    worktree = (
        "not_available" if status == "not_available" else "dirty" if status else "clean"
    )
    comparability_issues = list(missing)
    if worktree != "clean":
        comparability_issues.append(f"worktree_{worktree}")
    return {
        "captured_at": _now(),
        "environment_name": environment_name,
        "commit": _git_value("rev-parse", "HEAD"),
        "worktree": worktree,
        "host": {
            "operating_system": platform.platform(),
            "architecture": platform.machine(),
            "cpu_model": platform.processor() or "not_available",
            "logical_cpus": os.cpu_count() or "not_available",
            "memory_total_bytes": _memory_total(),
        },
        "storage": {
            "capacity_bytes": disk.total,
            "free_bytes_initial": disk.free,
        },
        "software": {
            "python": platform.python_version(),
            "httpx": _package_version("httpx"),
            "psycopg": _package_version("psycopg"),
        },
        "metadata": metadata,
        "missing_required_metadata": missing,
        "comparability_issues": comparability_issues,
        "comparability": (
            "comparable" if not comparability_issues else "non_comparable"
        ),
        "mass": {
            "bundle": bundle.name,
            "schema_version": manifest["schema_version"],
            "generator_version": manifest["generator_version"],
            "profile": manifest["profile"],
            "scenario": manifest["scenario"],
            "seed": manifest["seed"],
            "logical_digest": manifest["logical_digest"],
            "configuration": manifest["configuration"],
            "entities": manifest["entities"],
            "files": manifest["files"],
        },
    }


def collect_postgres_environment(database_url: str | None) -> dict[str, Any]:
    if not database_url:
        return {"collection_status": "not_configured"}
    try:
        import psycopg

        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SHOW server_version")
            server_version = cursor.fetchone()[0]
            cursor.execute(
                """
                SELECT name, setting, unit
                FROM pg_settings
                WHERE name = ANY(%s)
                ORDER BY name
                """,
                (
                    [
                        "effective_cache_size",
                        "maintenance_work_mem",
                        "max_connections",
                        "max_parallel_workers",
                        "max_parallel_workers_per_gather",
                        "shared_buffers",
                        "temp_file_limit",
                        "work_mem",
                    ],
                ),
            )
            settings = {
                name: {"setting": setting, "unit": unit}
                for name, setting, unit in cursor
            }
        return {
            "collection_status": "collected",
            "server_version": server_version,
            "settings": settings,
        }
    except Exception as exc:
        return {
            "collection_status": "unavailable",
            "collection_error": type(exc).__name__,
        }


def _memory_available() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _process_metrics(pid: int) -> dict[str, int | float]:
    stat = Path(f"/proc/{pid}/stat").read_text()
    fields = stat[stat.rfind(")") + 2 :].split()
    ticks = os.sysconf("SC_CLK_TCK")
    status = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        key, separator, value = line.partition(":")
        if separator:
            status[key] = value.strip()
    io_values = {}
    for line in Path(f"/proc/{pid}/io").read_text().splitlines():
        key, separator, value = line.partition(":")
        if separator:
            io_values[key] = int(value.strip())
    return {
        "cpu_seconds": (int(fields[11]) + int(fields[12])) / ticks,
        "rss_bytes": int(status["VmRSS"].split()[0]) * 1024,
        "read_bytes": io_values.get("read_bytes", 0),
        "write_bytes": io_values.get("write_bytes", 0),
    }


class ResourceMonitor:
    def __init__(
        self,
        interval: float,
        storage_path: Path,
        processes: dict[str, int],
        database_url: str | None,
    ) -> None:
        self.interval = interval
        self.storage_path = storage_path
        self.processes = processes
        self.database_url = database_url
        self.rows: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(self.interval * 2, 2))

    def _system_row(self) -> dict[str, Any]:
        return {
            "timestamp": _now(),
            "target": "system",
            "load_1m": os.getloadavg()[0] if hasattr(os, "getloadavg") else None,
            "memory_available_bytes": _memory_available(),
            "disk_free_bytes": shutil.disk_usage(self.storage_path).free,
        }

    def _database_row(self, connection) -> dict[str, Any]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
                       temp_files, temp_bytes, deadlocks
                FROM pg_stat_database WHERE datname = current_database()
                """
            )
            database = cursor.fetchone()
            cursor.execute(
                """
                SELECT count(*) FILTER (WHERE state = 'active'),
                       count(*) FILTER (WHERE wait_event IS NOT NULL)
                FROM pg_stat_activity WHERE datname = current_database()
                """
            )
            active, waiting = cursor.fetchone()
        return {
            "timestamp": _now(),
            "target": "postgres",
            "db_connections": database[0],
            "db_active": active,
            "db_waiting": waiting,
            "db_commits": database[1],
            "db_rollbacks": database[2],
            "db_blocks_read": database[3],
            "db_blocks_hit": database[4],
            "db_temp_files": database[5],
            "db_temp_bytes": database[6],
            "db_deadlocks": database[7],
        }

    def _run(self) -> None:
        connection = None
        if self.database_url:
            try:
                import psycopg

                connection = psycopg.connect(self.database_url, autocommit=True)
            except Exception as exc:  # observability must not abort the workload
                self.rows.append(
                    {
                        "timestamp": _now(),
                        "target": "postgres",
                        "collection_error": type(exc).__name__,
                    }
                )
        try:
            while not self._stop.is_set():
                self.rows.append(self._system_row())
                for name, pid in self.processes.items():
                    try:
                        self.rows.append(
                            {"timestamp": _now(), "target": name}
                            | _process_metrics(pid)
                        )
                    except (OSError, ValueError, KeyError) as exc:
                        self.rows.append(
                            {
                                "timestamp": _now(),
                                "target": name,
                                "collection_error": type(exc).__name__,
                            }
                        )
                if connection:
                    try:
                        self.rows.append(self._database_row(connection))
                    except Exception as exc:
                        self.rows.append(
                            {
                                "timestamp": _now(),
                                "target": "postgres",
                                "collection_error": type(exc).__name__,
                            }
                        )
                self._stop.wait(self.interval)
        finally:
            if connection:
                connection.close()


@dataclass
class Sample:
    scenario_id: str
    operation: str
    route: str
    measured: bool
    started_at: str
    finished_at: str
    duration_ms: float
    first_byte_ms: float | None
    status_code: int | None
    expected_status: str
    success: bool
    response_bytes: int
    correlation_id: str
    error_code: str | None


class HttpRecorder:
    def __init__(self, client: httpx.Client, scenario_id: str) -> None:
        self.client = client
        self.scenario_id = scenario_id
        self.samples: list[Sample] = []

    def request(
        self,
        operation: str,
        route: str,
        method: str,
        url: str,
        expected: set[int],
        *,
        measured: bool = True,
        **kwargs,
    ) -> httpx.Response | None:
        correlation_id = str(uuid4())
        headers = dict(kwargs.pop("headers", {}))
        headers["X-Correlation-ID"] = correlation_id
        started_at = _now()
        started = time.perf_counter_ns()
        response = None
        error_code = None
        first_byte_ms = None
        try:
            with self.client.stream(method, url, headers=headers, **kwargs) as response:
                first_byte_ms = (time.perf_counter_ns() - started) / 1_000_000
                content = response.read()
            success = response.status_code in expected
            if not success:
                error_code = _response_error_code(response)
            status_code = response.status_code
            response_bytes = len(content)
        except httpx.HTTPError as exc:
            success = False
            status_code = None
            response_bytes = 0
            error_code = type(exc).__name__
        finished = time.perf_counter_ns()
        self.samples.append(
            Sample(
                scenario_id=self.scenario_id,
                operation=operation,
                route=route,
                measured=measured,
                started_at=started_at,
                finished_at=_now(),
                duration_ms=(finished - started) / 1_000_000,
                first_byte_ms=first_byte_ms,
                status_code=status_code,
                expected_status=",".join(str(value) for value in sorted(expected)),
                success=success,
                response_bytes=response_bytes,
                correlation_id=correlation_id,
                error_code=error_code,
            )
        )
        return response


def _response_error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("code"):
                return str(error["code"])
            detail = payload.get("detail")
            if isinstance(detail, dict) and detail.get("code"):
                return str(detail["code"])
    except (ValueError, UnicodeDecodeError):
        pass
    return f"http_{response.status_code}"


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(math.ceil(percentile * len(ordered)) - 1, 0)
    return ordered[index]


def summarize(samples: list[Sample]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[Sample]] = {}
    for sample in samples:
        if sample.measured:
            groups.setdefault((sample.operation, sample.route), []).append(sample)
    operations = []
    for (operation, route), items in sorted(groups.items()):
        durations = [item.duration_ms for item in items]
        first_bytes = [
            item.first_byte_ms for item in items if item.first_byte_ms is not None
        ]
        elapsed_seconds = sum(durations) / 1000
        operations.append(
            {
                "operation": operation,
                "route": route,
                "samples": len(items),
                "successes": sum(item.success for item in items),
                "unexpected_errors": sum(not item.success for item in items),
                "error_rate": sum(not item.success for item in items) / len(items),
                "response_bytes": sum(item.response_bytes for item in items),
                "latency_ms": {
                    "min": min(durations),
                    "p50": _percentile(durations, 0.50),
                    "p95": _percentile(durations, 0.95),
                    "p99": _percentile(durations, 0.99),
                    "max": max(durations),
                },
                "first_byte_ms": (
                    {
                        "p50": _percentile(first_bytes, 0.50),
                        "p95": _percentile(first_bytes, 0.95),
                        "p99": _percentile(first_bytes, 0.99),
                    }
                    if first_bytes
                    else None
                ),
                "throughput_requests_per_second": (
                    len(items) / elapsed_seconds if elapsed_seconds else None
                ),
            }
        )
    return {
        "generated_at": _now(),
        "measured_samples": sum(sample.measured for sample in samples),
        "unexpected_errors": sum(
            sample.measured and not sample.success for sample in samples
        ),
        "operations": operations,
    }


def summarize_resources(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["target"]), []).append(row)
    result = {}
    for target, items in sorted(grouped.items()):
        metrics: dict[str, Any] = {
            "samples": len(items),
            "collection_errors": sum(
                bool(item.get("collection_error")) for item in items
            ),
        }
        for field in (
            "rss_bytes",
            "load_1m",
            "db_connections",
            "db_active",
            "db_waiting",
        ):
            values = [item[field] for item in items if item.get(field) is not None]
            if values:
                metrics[f"{field}_max"] = max(values)
        for field in ("memory_available_bytes", "disk_free_bytes"):
            values = [item[field] for item in items if item.get(field) is not None]
            if values:
                metrics[f"{field}_min"] = min(values)
        for field in (
            "cpu_seconds",
            "read_bytes",
            "write_bytes",
            "db_commits",
            "db_rollbacks",
            "db_blocks_read",
            "db_blocks_hit",
            "db_temp_files",
            "db_temp_bytes",
            "db_deadlocks",
        ):
            values = [item[field] for item in items if item.get(field) is not None]
            if values:
                metrics[f"{field}_delta"] = max(values[-1] - values[0], 0)
        cpu_values = [item for item in items if item.get("cpu_seconds") is not None]
        if len(cpu_values) >= 2:
            elapsed = (
                datetime.fromisoformat(cpu_values[-1]["timestamp"])
                - datetime.fromisoformat(cpu_values[0]["timestamp"])
            ).total_seconds()
            if elapsed > 0:
                metrics["cpu_percent_average"] = max(
                    (cpu_values[-1]["cpu_seconds"] - cpu_values[0]["cpu_seconds"])
                    / elapsed
                    * 100,
                    0,
                )
        result[target] = metrics
    return result


def _check(checks: list[dict[str, Any]], name: str, expected: Any, actual: Any) -> None:
    checks.append(
        {
            "check": name,
            "passed": actual == expected,
            "expected": expected,
            "actual": actual,
        }
    )


def _upload(
    recorder: HttpRecorder,
    bundle: Path,
    manifest: dict[str, Any],
    organization_id: str,
    expected: set[int] | None = None,
) -> httpx.Response | None:
    by_source = {
        item["source"]: item
        for item in manifest["files"]
        if item["format"] == CANONICAL_FORMATS[item["source"]]
    }
    if set(by_source) != set(CANONICAL_FORMATS):
        raise ValueError("Bundle sem um arquivo canônico para cada fonte")
    with ExitStack() as stack:
        multipart = []
        for source in CANONICAL_FORMATS:
            item = by_source[source]
            stream = stack.enter_context((bundle / item["file"]).open("rb"))
            multipart.append(("source", (None, source)))
            multipart.append(
                ("file", (item["file"], stream, "application/octet-stream"))
            )
        multipart.append(("organization_id", (None, organization_id)))
        return recorder.request(
            "UPLOAD",
            "POST /imports",
            "POST",
            "/imports",
            expected or {201},
            files=multipart,
        )


def _preflight(
    recorder: HttpRecorder, manifest: dict[str, Any], organization_id: str
) -> tuple[bool, list[str]]:
    response = recorder.request(
        "PREFLIGHT",
        "GET /imports/policy",
        "GET",
        "/imports/policy",
        {200},
        measured=False,
    )
    if response is None or response.status_code != 200:
        return False, ["upload_policy_unavailable"]
    payload = response.json()
    policies = {item["source"]: item for item in payload["policies"]}
    problems = []
    selected_files = [
        item
        for item in manifest["files"]
        if item["format"] == CANONICAL_FORMATS[item["source"]]
    ]
    for item in selected_files:
        policy = policies.get(item["source"])
        if not policy or item["format"] not in policy["allowed_extensions"]:
            problems.append(f"unsupported:{item['source']}:{item['format']}")
        elif item["size_bytes"] > policy["max_bytes"]:
            problems.append(f"too_large:{item['source']}:{item['size_bytes']}")
    organization_ids = {item["id"] for item in payload["organizations"]}
    if organization_id not in organization_ids:
        problems.append("organization_not_authorized")
    return not problems, problems


def _query_rounds(
    recorder: HttpRecorder,
    samples: dict[str, Any],
    organization_id: str,
    execution_id: str,
    warmups: int,
    repetitions: int,
) -> None:
    workorder = samples["workorders"]["median"]
    lot = samples["lots"]["median"]
    serial = samples["serials"]["median"]
    routes = (
        ("search-workorder", "/search", {"type": "workorder", "query": workorder}),
        (
            "workorder-detail",
            f"/workorders/{workorder}",
            {"execution_id": execution_id},
        ),
        ("lot-detail", f"/lots/{lot}", {"workorder_number": workorder}),
        ("serial-detail", f"/serials/{serial}", {}),
        ("pending-list", "/pending-items", {"page": 1, "page_size": 100}),
        ("history-list", "/history", {"execution_id": execution_id, "page_size": 100}),
        (
            "consolidated",
            f"/workorders/{workorder}/consolidated-result",
            {"execution_id": execution_id},
        ),
        ("indicators", "/indicators", {"organization_id": organization_id}),
    )
    for round_index in range(warmups + repetitions):
        measured = round_index >= warmups
        for route, url, params in routes:
            recorder.request(
                "QUERY", route, "GET", url, {200}, measured=measured, params=params
            )


def _report_rounds(
    recorder: HttpRecorder,
    organization_id: str,
    execution_id: str,
    warmups: int,
    repetitions: int,
) -> None:
    for round_index in range(warmups + repetitions):
        measured = round_index >= warmups
        for report_type in ("workorder_consolidated", "oqc_summary"):
            response = recorder.request(
                "REPORT",
                f"POST /reports ({report_type})",
                "POST",
                "/reports",
                {201},
                measured=measured,
                json={
                    "report_type": report_type,
                    "execution_id": execution_id,
                    "organization_id": organization_id,
                    "reference_at": _now(),
                    "filters": {},
                },
            )
            if response is None or response.status_code != 201:
                continue
            report = response.json()
            for export_format in ("csv", "json"):
                recorder.request(
                    "EXPORT",
                    f"GET /reports/version/export ({report_type}/{export_format})",
                    "GET",
                    f"/reports/{report['report_id']}/versions/{report['version']}/export",
                    {200},
                    measured=measured,
                    params={"format": export_format},
                )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_report(
    path: Path,
    environment: dict[str, Any],
    workload: dict[str, Any],
    summary: dict[str, Any],
    checks: list[dict[str, Any]],
) -> None:
    lines = [
        "# Relatório de baseline de desempenho",
        "",
        f"- Execução: `{workload['run_id']}`",
        f"- Comparabilidade: `{environment['comparability']}`",
        f"- Ambiente: `{environment['environment_name']}`",
        f"- Commit: `{environment['commit']}`",
        f"- Massa: `{environment['mass']['logical_digest']}`",
        f"- Erros inesperados: `{summary['unexpected_errors']}`",
        f"- Validações funcionais: `{sum(item['passed'] for item in checks)}/{len(checks)}`",
        "",
        "## Resultados",
        "",
        "| Operação | Rota | N | p50 ms | p95 ms | p99 ms | Erros |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary["operations"]:
        latency = item["latency_ms"]
        lines.append(
            f"| {item['operation']} | {item['route']} | {item['samples']} | "
            f"{latency['p50']:.2f} | {latency['p95']:.2f} | "
            f"{latency['p99']:.2f} | {item['unexpected_errors']} |"
        )
    if environment["missing_required_metadata"]:
        lines.extend(
            [
                "",
                "## Limitação de comparabilidade",
                "",
                "Metadados ausentes: "
                + ", ".join(environment["missing_required_metadata"])
                + ".",
            ]
        )
    lines.extend(
        ["", "Consulte os arquivos JSON e CSV deste diretório para os dados completos."]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_processes(values: list[str]) -> dict[str, int]:
    result = {}
    for value in values:
        name, separator, pid = value.partition("=")
        if not separator or not name or not pid.isdigit():
            raise ValueError(f"Processo inválido: {value!r}; use nome=pid")
        result[name] = int(pid)
    return result


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("o valor deve ser maior ou igual a zero")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("o valor deve ser maior que zero")
    return parsed


def _guard_rupture_environment(
    scenario_id: str,
    manifest: dict,
    isolation_kind: str | None,
    metadata: dict[str, str],
) -> None:
    entities = manifest.get("entities", {})
    workorders = entities.get("workorders")
    serials = entities.get("serials")
    if workorders is None or serials is None:
        raise ValueError("Massa sem cardinalidades; não assumir zero")
    above_reference = workorders > 6_800 or serials > 88_000
    rupture_scenario = scenario_id.upper().startswith(("V06", "V07", "V08", "V09"))
    if not (above_reference or rupture_scenario):
        return
    if isolation_kind not in {"isolated-container", "isolated-vm"}:
        raise ValueError("V06+ exige --isolation-kind em ambiente descartável")
    required = ("backend_limits", "postgres_limits", "storage_type")
    if any(
        not metadata.get(field) or metadata[field] == "not_available"
        for field in required
    ):
        raise ValueError(f"V06+ exige limites explícitos: {required}")
    if isolation_kind == "isolated-container" and not metadata.get("container_runtime"):
        raise ValueError("V06+ em container exige runtime registrado")
    if isolation_kind == "isolated-vm" and not metadata.get("vm_limits"):
        raise ValueError("V06+ em VM exige vm_limits registrado")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa e registra uma baseline HTTP reproduzível do SYNERGIA"
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--environment-name", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--organization-code", required=True)
    parser.add_argument("--scenario-id", default="V05")
    parser.add_argument("--output", type=Path, default=Path("artifacts/performance"))
    parser.add_argument("--run-id")
    parser.add_argument("--token-env", default="SYNERGIA_PERFORMANCE_TOKEN")
    parser.add_argument("--metadata", action="append", default=[])
    parser.add_argument("--process", action="append", default=[])
    parser.add_argument("--sample-interval", type=_positive_float, default=1.0)
    parser.add_argument("--query-warmups", type=_nonnegative_int, default=1)
    parser.add_argument("--query-repetitions", type=_nonnegative_int, default=5)
    parser.add_argument("--report-warmups", type=_nonnegative_int, default=1)
    parser.add_argument("--report-repetitions", type=_nonnegative_int, default=5)
    parser.add_argument("--skip-reports", action="store_true")
    parser.add_argument("--include-reprocess", action="store_true")
    parser.add_argument(
        "--isolation-kind", choices=("isolated-container", "isolated-vm")
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.getenv(args.token_env)
    if not token:
        raise SystemExit(f"Token ausente na variável {args.token_env}")
    manifest = validate_manifest(args.bundle / "manifest.json")
    if args.organization_code not in manifest["expectations"]["known_organizations"]:
        raise SystemExit("organization-code não pertence ao bundle")
    metadata = parse_metadata(args.metadata)
    try:
        _guard_rupture_environment(
            args.scenario_id, manifest, args.isolation_kind, metadata
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    run_id = (
        args.run_id or f"{args.scenario_id.lower()}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    )
    output = args.output / run_id
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Diretório de execução não está vazio: {output}")
    output.mkdir(parents=True, exist_ok=True)
    environment = collect_environment(
        args.environment_name, args.bundle, manifest, metadata
    )
    database_url = os.getenv("DATABASE_URL")
    environment["postgres"] = collect_postgres_environment(database_url)
    environment["isolation_kind"] = args.isolation_kind or "not_declared"
    workload = {
        "run_id": run_id,
        "scenario_id": args.scenario_id,
        "base_url": args.base_url,
        "organization_id": args.organization_id,
        "organization_code": args.organization_code,
        "token_source": args.token_env,
        "query_warmups": args.query_warmups,
        "query_repetitions": args.query_repetitions,
        "report_warmups": args.report_warmups,
        "report_repetitions": args.report_repetitions,
        "reports_enabled": not args.skip_reports,
        "reprocess_enabled": args.include_reprocess,
        "sample_interval_seconds": args.sample_interval,
        "isolation_kind": args.isolation_kind or "not_declared",
    }
    checks: list[dict[str, Any]] = []
    processes = parse_processes(args.process)
    monitor = ResourceMonitor(
        args.sample_interval,
        output,
        processes,
        database_url,
    )
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=900) as client:
        recorder = HttpRecorder(client, args.scenario_id)
        monitor.start()
        try:
            ready, problems = _preflight(recorder, manifest, args.organization_id)
            _check(checks, "upload_preflight", [], problems)
            if ready:
                response = _upload(
                    recorder, args.bundle, manifest, args.organization_id
                )
            else:
                response = None
            execution_id = None
            if response is not None and response.status_code == 201:
                upload_result = response.json()
                execution_id = upload_result["execution_id"]
                expected_state = (
                    "completed"
                    if manifest["scenario"] == "valid"
                    else "completed_with_errors"
                )
                _check(
                    checks,
                    "upload_terminal_state",
                    expected_state,
                    upload_result["status"],
                )
                summary_response = recorder.request(
                    "PROCESS",
                    "GET /imports/{id}/pipeline-summary",
                    "GET",
                    f"/imports/{execution_id}/pipeline-summary",
                    {200},
                )
                if summary_response is not None and summary_response.status_code == 200:
                    actual_summary = summary_response.json()
                    expected_summary = manifest["expectations"]["valid_pipeline"]
                    if expected_summary:
                        for key in (
                            "rows_read",
                            "valid_records",
                            "rejected_records",
                            "normalized_records",
                        ):
                            _check(
                                checks,
                                f"pipeline_summary.{key}",
                                expected_summary[key],
                                actual_summary[key],
                            )
                samples = manifest["expectations"]["query_samples"]["organizations"]
                _query_rounds(
                    recorder,
                    samples[args.organization_code],
                    args.organization_id,
                    execution_id,
                    args.query_warmups,
                    args.query_repetitions,
                )
                if not args.skip_reports:
                    _report_rounds(
                        recorder,
                        args.organization_id,
                        execution_id,
                        args.report_warmups,
                        args.report_repetitions,
                    )
                if args.include_reprocess:
                    idempotency_key = f"performance-{run_id}"
                    first = recorder.request(
                        "REPROCESS",
                        "POST /executions/{id}/reprocess",
                        "POST",
                        f"/executions/{execution_id}/reprocess",
                        {202},
                        json={
                            "technical_origin": "performance-baseline",
                            "idempotency_key": idempotency_key,
                        },
                    )
                    second = recorder.request(
                        "REPROCESS",
                        "POST /executions/{id}/reprocess replay",
                        "POST",
                        f"/executions/{execution_id}/reprocess",
                        {202},
                        json={
                            "technical_origin": "performance-baseline",
                            "idempotency_key": idempotency_key,
                        },
                    )
                    if (
                        first
                        and second
                        and first.status_code == second.status_code == 202
                    ):
                        _check(
                            checks,
                            "reprocess_idempotent_execution",
                            first.json()["execution_id"],
                            second.json()["execution_id"],
                        )
                        _check(
                            checks,
                            "reprocess_idempotent_replay",
                            True,
                            second.json()["idempotent_replay"],
                        )
        finally:
            monitor.stop()
    environment["storage"]["free_bytes_final"] = shutil.disk_usage(output).free
    summary = summarize(recorder.samples)
    summary["resources"] = summarize_resources(monitor.rows)
    summary["comparability"] = environment["comparability"]
    summary["correctness_passed"] = all(item["passed"] for item in checks)
    _write_json(output / "environment.json", environment)
    _write_json(output / "workload.json", workload)
    _write_json(output / "summary.json", summary)
    _write_json(output / "correctness.json", {"checks": checks})
    _write_csv(
        output / "samples.csv",
        [asdict(sample) for sample in recorder.samples],
        tuple(Sample.__dataclass_fields__),
    )
    _write_csv(output / "resources.csv", monitor.rows, RESOURCE_FIELDS)
    _write_report(output / "report.md", environment, workload, summary, checks)
    print(f"Artefatos: {output}")
    return (
        0 if summary["unexpected_errors"] == 0 and summary["correctness_passed"] else 1
    )


if __name__ == "__main__":
    sys.exit(main())
