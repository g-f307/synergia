from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Iterable
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from generate_synthetic_data import (
    CANONICAL_FORMATS,
    PROFILES,
    build_dataset,
    validate_manifest,
)

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


def _canonical_digest(rows: Iterable[dict[str, Any]], fields: tuple[str, ...]) -> str:
    """Digest a multiset of semantic rows, preserving duplicate multiplicity."""
    encoded = [
        json.dumps(
            {field: row.get(field) for field in fields},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        for row in rows
    ]
    payload = "\n".join(sorted(encoded)).encode()
    return hashlib.sha256(payload).hexdigest()


def _reference_records(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Rebuild the independent deterministic oracle described by the manifest."""
    organizations = manifest["expectations"]["known_organizations"]
    starts = [int(code.rsplit("-", 1)[-1]) for code in organizations]
    configuration = manifest["configuration"]
    profile = manifest["profile"] if manifest["profile"] in PROFILES else None
    records, _ = build_dataset(
        profile_name=profile,
        seed=manifest["seed"],
        scenario=manifest["scenario"],
        workorders=None if profile else configuration["workorders"],
        serials=None if profile else configuration["serials"],
        organization_count=len(organizations),
        organization_start=min(starts),
    )
    logical_payload = json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    if hashlib.sha256(logical_payload).hexdigest() != manifest["logical_digest"]:
        raise ValueError("Oráculo reconstruído diverge do digest lógico do manifesto")
    return records


CLASSIFICATION_FIELDS = (
    "workorder_number",
    "lot_number",
    "serial_number",
    "rule_id",
    "state",
    "entity_type",
    "entity_id",
    "data_quality",
    "source",
)
WORKORDER_REPORT_FIELDS = (
    "workorder_number",
    "organization_code",
    "processing_status",
    "planned_quantity",
    "produced_quantity",
    "received_quantity",
    "released_quantity",
    "pending_quantity",
    "retained_quantity",
    "partially_released",
    "lots",
    "serial_count",
    "open_pending_count",
)
OQC_REPORT_FIELDS = (
    "workorder_number",
    "lot_number",
    "organization_code",
    "decision_state",
    "reason",
    "pending_item_id",
    "priority",
    "priority_score",
    "pending_reason",
    "pending_status",
)


def _expected_oracle(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest["scenario"] != "valid":
        raise ValueError("A reconciliação integral exige uma massa de cenário valid")
    records = _reference_records(manifest)
    plans = {row["workorder_number"]: row for row in records["N-FP"]}
    serials_by_workorder: Counter[str] = Counter(
        row["workorder_number"] for row in records["OWM"]
    )
    workorders = []
    for number, row in sorted(plans.items()):
        serial_count = serials_by_workorder[number]
        workorders.append(
            {
                "workorder_number": number,
                "organization_code": row["organization_code"],
                "processing_status": "consolidated",
                "planned_quantity": row["planned_quantity"],
                "produced_quantity": row["produced_quantity"],
                "received_quantity": serial_count,
                "released_quantity": serial_count,
                "pending_quantity": max(row["planned_quantity"] - serial_count, 0),
                "retained_quantity": 0,
                "partially_released": False,
                "lots": [row["lot_number"]],
                "serial_count": serial_count,
                "open_pending_count": 0,
            }
        )

    classifications = []
    for source in ("OWM", "GMES/OQC", "TMS"):
        for row in records[source]:
            serial = row.get("serial_number") or None
            lot = row.get("lot_number") or None
            entity_type = "serial" if serial else "lot" if lot else "workorder"
            classifications.append(
                {
                    "workorder_number": row["workorder_number"],
                    "lot_number": lot,
                    "serial_number": serial,
                    "rule_id": "oqc_pass",
                    "state": "closed",
                    "entity_type": entity_type,
                    "entity_id": serial or lot or row["workorder_number"],
                    "data_quality": "complete",
                    "source": source,
                }
            )

    oqc_items = []
    organization_by_workorder = {
        number: row["organization_code"] for number, row in plans.items()
    }
    for item in classifications:
        oqc_items.append(
            {
                "workorder_number": item["workorder_number"],
                "lot_number": item["lot_number"],
                "organization_code": organization_by_workorder[
                    item["workorder_number"]
                ],
                "decision_state": "approved",
                "reason": None,
                "pending_item_id": None,
                "priority": None,
                "priority_score": None,
                "pending_reason": None,
                "pending_status": None,
            }
        )
    pipeline = manifest["expectations"]["valid_pipeline"]
    return {
        "counts": {
            "files": 4,
            "files_received": 4,
            "files_accepted": 4,
            "files_rejected": 0,
            "rows_read": pipeline["rows_read"],
            "valid_records": pipeline["valid_records"],
            "rejected_records": pipeline["rejected_records"],
            "normalized_records": pipeline["normalized_records"],
            "workorders": pipeline["consolidated_workorders"],
            "lots": pipeline["consolidated_lots"],
            "serials": pipeline["consolidated_serials"],
            "classifications": len(classifications),
            "pending_items": 0,
            "errors": 0,
            "warnings": 0,
        },
        "classification_count": len(classifications),
        "classification_digest": _canonical_digest(
            classifications, CLASSIFICATION_FIELDS
        ),
        "workorder_count": len(workorders),
        "workorder_digest": _canonical_digest(workorders, WORKORDER_REPORT_FIELDS),
        "oqc_count": len(oqc_items),
        "oqc_digest": _canonical_digest(oqc_items, OQC_REPORT_FIELDS),
    }


def _all_pages(
    recorder: HttpRecorder, url: str, route: str, *, page_size: int = 100
) -> tuple[list[dict[str, Any]], int | None]:
    items: list[dict[str, Any]] = []
    page = 1
    reported_total = None
    while True:
        response = recorder.request(
            "ORACLE",
            route,
            "GET",
            url,
            {200},
            measured=False,
            params={"page": page, "page_size": page_size, "sort": "oldest"},
        )
        if response is None or response.status_code != 200:
            break
        payload = response.json()
        pagination = payload["pagination"]
        reported_total = pagination["total"]
        items.extend(payload["items"])
        if page >= pagination["pages"]:
            break
        page += 1
    return items, reported_total


def _classification_semantics(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "source": (item.get("evidence") or {}).get("source"),
    }


def _csv_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def _csv_digest(content: bytes, fields: tuple[str, ...]) -> tuple[int, str]:
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    normalized = [
        {field: row.get(field, "") for field in fields}
        for row in rows
    ]
    return len(rows), _canonical_digest(normalized, fields)


def _json_rows_digest(
    rows: list[dict[str, Any]], fields: tuple[str, ...]
) -> tuple[int, str]:
    return len(rows), _canonical_digest(rows, fields)


def _reconcile_report(
    recorder: HttpRecorder,
    checks: list[dict[str, Any]],
    report_type: str,
    report: dict[str, Any],
    expected_count: int,
    expected_digest: str,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    base = f"/reports/{report['report_id']}/versions/{report['version']}"
    response = recorder.request(
        "ORACLE", f"GET report ({report_type})", "GET", base, {200}, measured=False
    )
    if response is None or response.status_code != 200:
        return {"report_type": report_type, "status": "unavailable"}
    payload = response.json()
    key = "workorders" if report_type == "workorder_consolidated" else "items"
    rows = payload["data"][key]
    count, digest = _json_rows_digest(rows, fields)
    _check(checks, f"oracle.{report_type}.report_count", expected_count, count)
    _check(checks, f"oracle.{report_type}.report_digest", expected_digest, digest)

    exports: dict[str, Any] = {}
    for export_format in ("json", "csv"):
        exported = recorder.request(
            "ORACLE",
            f"GET report export ({report_type}/{export_format})",
            "GET",
            f"{base}/export",
            {200},
            measured=False,
            params={"format": export_format},
        )
        if exported is None or exported.status_code != 200:
            continue
        if export_format == "json":
            export_rows = exported.json()["data"][key]
            export_count, export_digest = _json_rows_digest(export_rows, fields)
            expected_export_digest = expected_digest
        else:
            export_count, export_digest = _csv_digest(exported.content, fields)
            expected_csv_rows = [
                {field: _csv_value(row.get(field)) for field in fields}
                for row in rows
            ]
            expected_export_digest = _canonical_digest(expected_csv_rows, fields)
        _check(
            checks,
            f"oracle.{report_type}.{export_format}_count",
            expected_count,
            export_count,
        )
        _check(
            checks,
            f"oracle.{report_type}.{export_format}_digest",
            expected_export_digest,
            export_digest,
        )
        exports[export_format] = {"count": export_count, "digest": export_digest}
    return {
        "report_type": report_type,
        "count": count,
        "digest": digest,
        "exports": exports,
    }


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
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
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
            latest[report_type] = report
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
    return latest


def _reconcile_full_oracle(
    recorder: HttpRecorder,
    manifest: dict[str, Any],
    execution_id: str,
    reports: dict[str, dict[str, Any]],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = _expected_oracle(manifest)
    result: dict[str, Any] = {
        "manifest_logical_digest": manifest["logical_digest"],
        "expected": expected,
    }
    execution = recorder.request(
        "ORACLE",
        "GET /executions/{id}",
        "GET",
        f"/executions/{execution_id}",
        {200},
        measured=False,
    )
    if execution is not None and execution.status_code == 200:
        actual_counts = execution.json()["counts"]
        for key, expected_value in expected["counts"].items():
            _check(
                checks,
                f"oracle.execution_counts.{key}",
                expected_value,
                actual_counts[key],
            )
        result["execution_counts"] = actual_counts

    classifications, classification_total = _all_pages(
        recorder,
        f"/executions/{execution_id}/classifications",
        "GET /executions/{id}/classifications",
        page_size=1000,
    )
    classification_digest = _canonical_digest(
        (_classification_semantics(item) for item in classifications),
        CLASSIFICATION_FIELDS,
    )
    _check(
        checks,
        "oracle.classifications.total",
        expected["classification_count"],
        classification_total,
    )
    _check(
        checks,
        "oracle.classifications.fetched",
        expected["classification_count"],
        len(classifications),
    )
    _check(
        checks,
        "oracle.classifications.digest",
        expected["classification_digest"],
        classification_digest,
    )
    result["classifications"] = {
        "reported_total": classification_total,
        "fetched": len(classifications),
        "digest": classification_digest,
    }

    pending, pending_total = _all_pages(
        recorder,
        f"/executions/{execution_id}/pending-items",
        "GET /executions/{id}/pending-items",
    )
    _check(checks, "oracle.pending.total", 0, pending_total)
    _check(checks, "oracle.pending.fetched", 0, len(pending))
    result["pending"] = {"reported_total": pending_total, "fetched": len(pending)}

    report_results = []
    report_specs = {
        "workorder_consolidated": (
            expected["workorder_count"],
            expected["workorder_digest"],
            WORKORDER_REPORT_FIELDS,
        ),
        "oqc_summary": (
            expected["oqc_count"],
            expected["oqc_digest"],
            OQC_REPORT_FIELDS,
        ),
    }
    for report_type, (count, digest, fields) in report_specs.items():
        report = reports.get(report_type)
        _check(checks, f"oracle.{report_type}.generated", True, report is not None)
        if report is not None:
            report_results.append(
                _reconcile_report(
                    recorder,
                    checks,
                    report_type,
                    report,
                    count,
                    digest,
                    fields,
                )
            )
    result["reports"] = report_results
    return result


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

    passed_checks = sum(item["passed"] for item in checks)
    total_checks = len(checks)
    lines = [
        "# Relatório de baseline de desempenho",
        "",
        f"- Execução: `{workload['run_id']}`",
        f"- Comparabilidade: `{environment['comparability']}`",
        f"- Ambiente: `{environment['environment_name']}`",
        f"- Commit: `{environment['commit']}`",
        f"- Massa: `{environment['mass']['logical_digest']}`",
        f"- Erros inesperados: `{summary['unexpected_errors']}`",
        f"- Validações funcionais: `{passed_checks}/{total_checks}`",
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
    parser.add_argument(
        "--existing-execution-id",
        help=(
            "Reconcilia uma execução terminal existente, sem realizar um novo upload"
        ),
    )
    parser.add_argument("--token-env", default="SYNERGIA_PERFORMANCE_TOKEN")
    parser.add_argument("--metadata", action="append", default=[])
    parser.add_argument("--process", action="append", default=[])
    parser.add_argument("--sample-interval", type=_positive_float, default=1.0)
    parser.add_argument("--request-timeout", type=_positive_float, default=3600.0)
    parser.add_argument("--query-warmups", type=_nonnegative_int, default=1)
    parser.add_argument("--query-repetitions", type=_nonnegative_int, default=5)
    parser.add_argument("--report-warmups", type=_nonnegative_int, default=1)
    parser.add_argument("--report-repetitions", type=_nonnegative_int, default=5)
    parser.add_argument("--skip-reports", action="store_true")
    parser.add_argument(
        "--skip-full-oracle",
        action="store_true",
        help="Desativa a reconciliação integral (somente para sondas exploratórias)",
    )
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
        "full_oracle_enabled": not args.skip_full_oracle,
        "reprocess_enabled": args.include_reprocess,
        "sample_interval_seconds": args.sample_interval,
        "request_timeout_seconds": args.request_timeout,
        "isolation_kind": args.isolation_kind or "not_declared",
        "existing_execution_id": args.existing_execution_id,
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
    with httpx.Client(
        base_url=args.base_url, headers=headers, timeout=args.request_timeout
    ) as client:
        recorder = HttpRecorder(client, args.scenario_id)
        reports: dict[str, dict[str, Any]] = {}
        oracle_result: dict[str, Any] | None = None
        monitor.start()
        try:
            execution_id = args.existing_execution_id
            if execution_id:
                response = recorder.request(
                    "PROCESS",
                    "GET /executions/{id}",
                    "GET",
                    f"/executions/{execution_id}",
                    {200},
                )
                if response is not None and response.status_code == 200:
                    _check(
                        checks,
                        "existing_execution_terminal_state",
                        (
                            "completed"
                            if manifest["scenario"] == "valid"
                            else "completed_with_errors"
                        ),
                        response.json()["status"],
                    )
                else:
                    execution_id = None
            else:
                ready, problems = _preflight(
                    recorder, manifest, args.organization_id
                )
                _check(checks, "upload_preflight", [], problems)
                response = (
                    _upload(recorder, args.bundle, manifest, args.organization_id)
                    if ready
                    else None
                )
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

            if execution_id is not None:
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
                    reports = _report_rounds(
                        recorder,
                        args.organization_id,
                        execution_id,
                        args.report_warmups,
                        args.report_repetitions,
                    )
                if not args.skip_full_oracle:
                    if args.skip_reports:
                        _check(
                            checks,
                            "oracle.reports_enabled",
                            True,
                            False,
                        )
                    else:
                        oracle_result = _reconcile_full_oracle(
                            recorder,
                            manifest,
                            execution_id,
                            reports,
                            checks,
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
    if oracle_result is not None:
        _write_json(output / "oracle-results.json", oracle_result)
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
