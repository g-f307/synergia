from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from generate_synthetic_data import validate_manifest
from run_performance_baseline import (
    RESOURCE_FIELDS,
    HttpRecorder,
    ResourceMonitor,
    Sample,
    _check,
    _memory_available,
    _preflight,
    _upload,
    _write_csv,
    _write_json,
    collect_environment,
    collect_postgres_environment,
    parse_metadata,
    parse_processes,
    summarize,
    summarize_resources,
)

SUPPORTED_SCENARIOS = ("C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08")


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Wave:
    scenario_id: str
    level: int
    cycle: int
    started_at: str
    finished_at: str
    duration_ms: float
    clients: int
    requests: int
    successes: int
    unexpected_errors: int
    throughput_requests_per_second: float


def run_wave(
    scenario_id: str,
    level: int,
    cycle: int,
    task: Callable[[int], int],
) -> Wave:
    """Start all clients behind one barrier and measure aggregate wall time."""
    barrier = threading.Barrier(level)

    def synchronized(index: int) -> int:
        barrier.wait(timeout=30)
        return task(index)

    started_at = _now()
    started = time.perf_counter_ns()
    with ThreadPoolExecutor(max_workers=level) as executor:
        request_counts = list(executor.map(synchronized, range(level)))
    duration_ms = (time.perf_counter_ns() - started) / 1_000_000
    requests = sum(request_counts)
    return Wave(
        scenario_id=scenario_id,
        level=level,
        cycle=cycle,
        started_at=started_at,
        finished_at=_now(),
        duration_ms=duration_ms,
        clients=level,
        requests=requests,
        successes=0,
        unexpected_errors=0,
        throughput_requests_per_second=(
            requests / (duration_ms / 1000) if duration_ms else 0
        ),
    )


def _safe_json(response: httpx.Response | None) -> dict[str, Any]:
    if response is None:
        return {}
    try:
        payload = response.json()
    except (ValueError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _error_details(response: httpx.Response | None) -> dict[str, Any]:
    payload = _safe_json(response)
    error = payload.get("error")
    if not isinstance(error, dict):
        return {}
    details = error.get("details")
    return details if isinstance(details, dict) else {}


def _json_digest(response: httpx.Response | None) -> str | None:
    if response is None or response.status_code != 200:
        return None
    try:
        payload = response.json()
        if isinstance(payload, dict):
            payload = {
                key: value for key, value in payload.items() if key != "generated_at"
                }
        canonical = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except (ValueError, UnicodeDecodeError):
        return None
    return hashlib.sha256(canonical.encode()).hexdigest()


def _record_wave_result(wave: Wave, samples: list[Sample], start: int) -> None:
    measured = samples[start:]
    wave.successes = sum(sample.success for sample in measured)
    wave.unexpected_errors = sum(not sample.success for sample in measured)


def check_c02(
    checks: list[dict[str, Any]], responses: list[httpx.Response | None], level: int
) -> None:
    created = [
        item for item in responses if item is not None and item.status_code == 201
    ]
    duplicates = [
        item for item in responses if item is not None and item.status_code == 409
    ]
    _check(checks, f"C02.level_{level}.created", 1, len(created))
    _check(checks, f"C02.level_{level}.duplicates", level - 1, len(duplicates))
    _check(
        checks,
        f"C02.level_{level}.contractual_duplicate_code",
        level - 1,
        sum(
            _safe_json(item).get("error", {}).get("code") == "duplicate_file"
            for item in duplicates
        ),
    )
    if created:
        execution_id = _safe_json(created[0]).get("execution_id")
        duplicate_targets = {
            _error_details(item).get("duplicate_of_execution_id") for item in duplicates
        }
        _check(
            checks,
            f"C02.level_{level}.single_duplicate_target",
            [execution_id],
            sorted(duplicate_targets, key=lambda value: "" if value is None else value),
        )


def check_distinct_uploads(
    checks: list[dict[str, Any]],
    responses: list[httpx.Response | None],
    level: int,
    check_name: str,
) -> None:
    payloads = [_safe_json(item) for item in responses]
    _check(
        checks,
        f"{check_name}.level_{level}.completed",
        level,
        sum(
            item is not None
            and item.status_code == 201
            and payload.get("status") == "completed"
            for item, payload in zip(responses, payloads, strict=True)
        ),
    )
    _check(
        checks,
        f"{check_name}.level_{level}.distinct_executions",
        level,
        len({item.get("execution_id") for item in payloads}),
    )


def check_pipeline_counts(
    checks: list[dict[str, Any]],
    recorder: HttpRecorder,
    response: httpx.Response | None,
    manifest: dict[str, Any],
    check_name: str,
) -> None:
    execution_id = _safe_json(response).get("execution_id")
    if not execution_id:
        _check(checks, f"{check_name}.execution_id", True, False)
        return
    summary = recorder.request(
        "PROCESS",
        "GET /imports/{id}/pipeline-summary",
        "GET",
        f"/imports/{execution_id}/pipeline-summary",
        {200},
        measured=False,
    )
    actual = _safe_json(summary)
    expected = manifest["expectations"]["valid_pipeline"]
    for field in (
        "rows_read",
        "valid_records",
        "rejected_records",
        "normalized_records",
    ):
        _check(
            checks,
            f"{check_name}.{field}",
            expected[field],
            actual.get(field),
        )
def check_c03(
    checks: list[dict[str, Any]], responses: list[httpx.Response | None], level: int
) -> None:
    payloads = [_safe_json(item) for item in responses]
    _check(
        checks,
        f"C03.level_{level}.one_execution",
        1,
        len({item.get("execution_id") for item in payloads}),
    )
    _check(
        checks,
        f"C03.level_{level}.one_reservation",
        1,
        sum(item.get("idempotent_replay") is False for item in payloads),
    )
    _check(
        checks,
        f"C03.level_{level}.replays",
        level - 1,
        sum(item.get("idempotent_replay") is True for item in payloads),
    )


def check_c04(
    checks: list[dict[str, Any]], responses: list[httpx.Response | None], level: int
) -> None:
    payloads = [_safe_json(item) for item in responses]
    _check(
        checks,
        f"C04.level_{level}.distinct_executions",
        level,
        len({item.get("execution_id") for item in payloads}),
    )
    _check(
        checks,
        f"C04.level_{level}.new_reservations",
        level,
        sum(item.get("idempotent_replay") is False for item in payloads),
    )


def check_report_export(
    checks: list[dict[str, Any]],
    report: httpx.Response | None,
    exports: dict[str, httpx.Response | None],
    check_name: str,
) -> None:
    report_payload = _safe_json(report)
    report_data = report_payload.get("data")
    metadata = {
        key: report_payload.get(key)
        for key in ("report_id", "version", "execution_id", "organization_id")
    }
    _check(checks, f"{check_name}.succeeded", "succeeded", report_payload.get("state"))
    csv_response = exports.get("csv")
    json_response = exports.get("json")
    exported_json = _safe_json(json_response)
    _check(
        checks,
        f"{check_name}.json_data_unchanged",
        hashlib.sha256(
            json.dumps(
                report_data, sort_keys=True, ensure_ascii=False
                ).encode()
        ).hexdigest(),
        hashlib.sha256(
            json.dumps(
                exported_json.get("data"), sort_keys=True, ensure_ascii=False
                ).encode()
        ).hexdigest(),
    )
    _check(
        checks,
        f"{check_name}.json_identity",
        metadata,
        {key: exported_json.get(key) for key in metadata},
    )
    try:
        csv_rows = list(
            csv.DictReader(io.StringIO(csv_response.text))
            ) if csv_response else []
    except (UnicodeDecodeError, csv.Error):
        csv_rows = []
    expected_count = (
        report_data.get("count") if isinstance(report_data, dict) else None
    )
    _check(checks, f"{check_name}.csv_rows", expected_count, len(csv_rows))
    _check(
        checks,
        f"{check_name}.csv_identity",
        {"report_id": str(metadata["report_id"]), "version": str(metadata["version"])},
        (
            {
                "report_id": csv_rows[0].get("report_id"),
                "version": csv_rows[0].get("version"),
            }
            if csv_rows
            else {
                "report_id": str(metadata["report_id"]),
                "version": str(metadata["version"]),
            }
            if expected_count == 0 and csv_response is not None
            else None
        ),
    )
def _query_routes(
    samples: dict[str, Any], organization_id: str, execution_id: str
) -> tuple[tuple[str, str, dict[str, Any]], ...]:
    workorder = samples["workorders"]["median"]
    lot = samples["lots"]["median"]
    serial = samples["serials"]["median"]
    return (
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


def _query_snapshot(
    client: httpx.Client,
    samples: dict[str, Any],
    organization_id: str,
    execution_id: str,
) -> dict[str, str | None]:
    return {
        route: _json_digest(client.get(url, params=params))
        for route, url, params in _query_routes(
            samples, organization_id, execution_id
        )
    }


def _write_report(
    path: Path,
    environment: dict[str, Any],
    workload: dict[str, Any],
    summary: dict[str, Any],
    checks: list[dict[str, Any]],
) -> None:
    lines = [
        "# Relatório de concorrência e idempotência",
        "",
        f"- Execução: `{workload['run_id']}`",
        f"- Comparabilidade: `{environment['comparability']}`",
        f"- Cenários: `{', '.join(workload['scenarios'])}`",
        f"- Erros inesperados: `{summary['unexpected_errors']}`",
        f"- Validações funcionais: `{sum(c['passed'] for c in checks)}/{len(checks)}`",
        "",
        "## Ondas",
        "",
        "| Cenário | Nível | Ciclo | Clientes | Requisições | "
        "Duração ms | req/s | Erros |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for wave in summary["waves"]:
        lines.append(
            f"| {wave['scenario_id']} | {wave['level']} | {wave['cycle']} | "
            f"{wave['clients']} | {wave['requests']} | {wave['duration_ms']:.2f} | "
            f"{wave['throughput_requests_per_second']:.2f} | "
            f"{wave['unexpected_errors']} |"
        )
    if summary["skipped_levels"]:
        lines.extend(("", "## Níveis não iniciados", ""))
        for item in summary["skipped_levels"]:
            lines.append(
                f"- `{item['scenario_id']}` nível `{item['level']}`: {item['reason']}"
            )
    lines.extend(
        ("", "Os arquivos JSON e CSV contêm as amostras e recursos completos.")
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _levels(value: str) -> list[int]:
    try:
        levels = sorted({int(item) for item in value.split(",")})
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "use níveis inteiros separados por vírgula"
        ) from exc
    if not levels or levels[0] < 2:
        raise argparse.ArgumentTypeError("cada nível deve ser maior ou igual a 2")
    return levels


def _swap_used() -> int | None:
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, separator, amount = line.partition(":")
            if separator and key in {"SwapTotal", "SwapFree"}:
                values[key] = int(amount.split()[0]) * 1024
        return values["SwapTotal"] - values["SwapFree"]
    except (OSError, ValueError, IndexError, KeyError):
        return None


def _resource_guard(
    min_available_memory_bytes: int, max_swap_used_bytes: int | None
) -> tuple[str | None, dict[str, int | None]]:
    available = _memory_available()
    swap_used = _swap_used()
    observed = {
        "available_memory_bytes": available,
        "swap_used_bytes": swap_used,
    }
    if available is not None and available < min_available_memory_bytes:
        return "memória disponível abaixo da guarda configurada", observed
    if (
        max_swap_used_bytes is not None
        and swap_used is not None
        and swap_used > max_swap_used_bytes
    ):
        return "swap utilizada acima da guarda configurada", observed
    return None, observed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa ondas concorrentes reproduzíveis do SYNERGIA"
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument(
        "--c01-bundle",
        type=Path,
        action="append",
        default=[],
        help="massa inédita por cliente/onda C01, na ordem nível/ciclo/cliente",
    )
    parser.add_argument(
        "--c02-bundle",
        type=Path,
        action="append",
        default=[],
        help="massa inédita por onda C02, na ordem nível/ciclo",
    )
    parser.add_argument(
        "--c07-bundle",
        type=Path,
        action="append",
        default=[],
        help="massa inédita do escritor por onda C07, na ordem nível/ciclo",
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--environment-name", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--organization-code", required=True)
    parser.add_argument("--execution-id")
    parser.add_argument(
        "--scenario", action="append", choices=SUPPORTED_SCENARIOS, required=True
    )
    parser.add_argument("--levels", type=_levels, default=[2, 4, 8])
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("artifacts/performance"))
    parser.add_argument("--run-id")
    parser.add_argument("--token-env", default="SYNERGIA_PERFORMANCE_TOKEN")
    parser.add_argument("--isolation-token-env")
    parser.add_argument("--isolation-organization-id")
    parser.add_argument("--isolation-organization-code")
    parser.add_argument("--metadata", action="append", default=[])
    parser.add_argument("--process", action="append", default=[])
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--min-available-memory-bytes", type=int, default=536_870_912)
    parser.add_argument("--max-swap-used-bytes", type=int)
    args = parser.parse_args()
    if args.cycles < 1:
        parser.error("--cycles deve ser maior ou igual a 1")
    if args.sample_interval <= 0 or args.min_available_memory_bytes < 0:
        parser.error(
            "intervalo deve ser positivo e memória mínima não pode ser negativa"
        )
    if args.max_swap_used_bytes is not None and args.max_swap_used_bytes < 0:
        parser.error("--max-swap-used-bytes não pode ser negativo")
    execution_scenarios = {"C03", "C04", "C05", "C06", "C07", "C08"}
    if execution_scenarios.intersection(args.scenario) and not args.execution_id:
        parser.error("os cenários C03 a C08 exigem --execution-id")
    if "C08" in args.scenario and not all(
        (
            args.isolation_token_env,
            args.isolation_organization_id,
            args.isolation_organization_code,
        )
    ):
        parser.error(
            "C08 exige token, id e código da organização usada para isolamento"
        )
    if (
        "C08" in args.scenario
        and args.isolation_organization_id == args.organization_id
    ):
        parser.error("C08 exige duas organizações distintas")
    required_c02_bundles = len(args.levels) * args.cycles
    required_c01_bundles = sum(args.levels) * args.cycles
    if "C01" in args.scenario and len(args.c01_bundle) != required_c01_bundles:
        parser.error(
            "C01 exige exatamente "
            f"{required_c01_bundles} opções --c01-bundle "
            "(uma massa inédita por cliente/onda)"
        )
    if "C02" in args.scenario and len(args.c02_bundle) != required_c02_bundles:
        parser.error(
            "C02 exige exatamente "
            f"{required_c02_bundles} opções --c02-bundle (uma massa inédita por onda)"
        )
    if "C07" in args.scenario and len(args.c07_bundle) != required_c02_bundles:
        parser.error(
            "C07 exige exatamente "
            f"{required_c02_bundles} opções --c07-bundle "
            "(uma massa inédita por onda)"
        )
    return args


def main() -> int:
    args = parse_args()
    token = os.getenv(args.token_env)
    if not token:
        raise SystemExit(f"Token ausente na variável {args.token_env}")
    isolation_token = (
        os.getenv(args.isolation_token_env) if args.isolation_token_env else None
    )
    if args.isolation_token_env and not isolation_token:
        raise SystemExit(f"Token ausente na variável {args.isolation_token_env}")
    manifest = validate_manifest(args.bundle / "manifest.json")
    c01_bundles = [
        (bundle, validate_manifest(bundle / "manifest.json"))
        for bundle in args.c01_bundle
    ]
    c02_bundles = [
        (bundle, validate_manifest(bundle / "manifest.json"))
        for bundle in args.c02_bundle
    ]
    c07_bundles = [
        (bundle, validate_manifest(bundle / "manifest.json"))
        for bundle in args.c07_bundle
    ]
    organizations = manifest["expectations"]["query_samples"]["organizations"]
    if args.organization_code not in organizations:
        raise SystemExit("organization-code não pertence ao bundle")

    run_id = args.run_id or f"concurrency-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    output = args.output / run_id
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Diretório de execução não está vazio: {output}")
    output.mkdir(parents=True, exist_ok=True)
    metadata = parse_metadata(args.metadata)
    environment = collect_environment(
        args.environment_name, args.bundle, manifest, metadata
    )
    database_url = os.getenv("DATABASE_URL")
    environment["postgres"] = collect_postgres_environment(database_url)
    workload = {
        "run_id": run_id,
        "scenarios": args.scenario,
        "levels": args.levels,
        "cycles": args.cycles,
        "base_url": args.base_url,
        "organization_id": args.organization_id,
        "organization_code": args.organization_code,
        "execution_id": args.execution_id,
        "scenario_bundles": [
            {
                "scenario_id": scenario_id,
                "bundle": bundle.name,
                "logical_digest": item["logical_digest"],
                "seed": item["seed"],
            }
            for scenario_id, scenario_bundles in (
                ("C01", c01_bundles),
                ("C02", c02_bundles),
                ("C07", c07_bundles),
            )
            for bundle, item in scenario_bundles
        ],
        "token_source": args.token_env,
        "isolation_token_source": args.isolation_token_env,
        "isolation_organization_id": args.isolation_organization_id,
        "isolation_organization_code": args.isolation_organization_code,
        "min_available_memory_bytes": args.min_available_memory_bytes,
        "max_swap_used_bytes": args.max_swap_used_bytes,
        "sample_interval_seconds": args.sample_interval,
    }
    checks: list[dict[str, Any]] = []
    waves: list[Wave] = []
    skipped: list[dict[str, Any]] = []
    samples = organizations[args.organization_code]
    c01_wave_index = 0
    c02_wave_index = 0
    c07_wave_index = 0
    monitor = ResourceMonitor(
        args.sample_interval, output, parse_processes(args.process), database_url
    )
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=900) as client:
        recorder = HttpRecorder(client, "CONCURRENCY")
        isolation_client = (
            httpx.Client(
                base_url=args.base_url,
                headers={"Authorization": f"Bearer {isolation_token}"},
                timeout=900,
            )
            if isolation_token
            else None
        )
        isolation_recorder = (
            HttpRecorder(isolation_client, "C08") if isolation_client else None
        )
        monitor.start()
        try:
            ready, problems = _preflight(recorder, manifest, args.organization_id)
            _check(checks, "upload_preflight", [], problems)
            if not ready:
                raise RuntimeError("preflight de upload falhou: " + ", ".join(problems))
            if "C08" in args.scenario and isolation_recorder:
                visible = isolation_recorder.request(
                    "ISOLATION_PREFLIGHT",
                    "GET /indicators (own organization)",
                    "GET",
                    "/indicators",
                    {200},
                    measured=False,
                    params={"organization_id": args.isolation_organization_id},
                )
                denied = isolation_recorder.request(
                    "ISOLATION_PREFLIGHT",
                    "GET /indicators (foreign organization)",
                    "GET",
                    "/indicators",
                    {403},
                    measured=False,
                    params={"organization_id": args.organization_id},
                )
                _check(
                    checks,
                    "C08.isolation_actor_own_organization",
                    200,
                    visible.status_code if visible is not None else None,
                )
                _check(
                    checks,
                    "C08.isolation_actor_foreign_organization",
                    403,
                    denied.status_code if denied is not None else None,
                )
                if not checks[-1]["passed"] or not checks[-2]["passed"]:
                    raise RuntimeError("ator de isolamento possui escopo incorreto")
            scenario_bundles = c01_bundles + c02_bundles + c07_bundles
            digests = [item[1]["logical_digest"] for item in scenario_bundles]
            if len(digests) != len(set(digests)):
                raise RuntimeError(
                    "massas C01, C02 e C07 devem possuir hashes distintos"
                )
            for bundle, item in scenario_bundles:
                known = item["expectations"]["known_organizations"]
                if args.organization_code not in known:
                    raise RuntimeError(f"organização ausente na massa {bundle}")
                bundle_ready, bundle_problems = _preflight(
                    recorder, item, args.organization_id
                )
                if not bundle_ready:
                    raise RuntimeError(
                        f"preflight da massa {bundle} falhou: "
                        + ", ".join(bundle_problems)
                    )
            for scenario_id in args.scenario:
                for level in args.levels:
                    halt_scenario = False
                    for cycle in range(1, args.cycles + 1):
                        reason, observed = _resource_guard(
                            args.min_available_memory_bytes,
                            args.max_swap_used_bytes,
                        )
                        if reason:
                            skipped.append(
                                {
                                    "scenario_id": scenario_id,
                                    "level": level,
                                    "cycle": cycle,
                                    "reason": reason,
                                    **observed,
                                }
                            )
                            halt_scenario = True
                            break
                        check_start = len(checks)
                        recorder.scenario_id = scenario_id
                        responses: list[Any] = []
                        report_exports: list[
                            tuple[
                                httpx.Response | None, dict[str, httpx.Response | None]
                                ]
                        ] = []
                        response_lock = threading.Lock()
                        before_snapshot = (
                            _query_snapshot(
                                client,
                                samples,
                                args.organization_id,
                                args.execution_id,
                            )
                            if scenario_id == "C07"
                            else {}
                        )

                        def request_task(index: int) -> int:
                            if scenario_id == "C01":
                                offset = c01_wave_index + index
                                upload_bundle, upload_manifest = c01_bundles[offset]
                                response = _upload(
                                    recorder,
                                    upload_bundle,
                                    upload_manifest,
                                    args.organization_id,
                                )
                            elif scenario_id == "C02":
                                c02_bundle, c02_manifest = c02_bundles[c02_wave_index]
                                response = _upload(
                                    recorder,
                                    c02_bundle,
                                    c02_manifest,
                                    args.organization_id,
                                    {201, 409},
                                )
                            elif scenario_id in {"C03", "C04"}:
                                key_suffix = (
                                    "same" if scenario_id == "C03" else str(index)
                                )
                                response = recorder.request(
                                    "REPROCESS",
                                    "POST /executions/{id}/reprocess",
                                    "POST",
                                    f"/executions/{args.execution_id}/reprocess",
                                    {202},
                                    json={
                                        "technical_origin": "performance-concurrency",
                                        "idempotency_key": (
                                            f"{run_id}-{scenario_id}-{level}-"
                                            f"{cycle}-{key_suffix}"
                                        ),
                                    },
                                )
                            elif scenario_id in {"C05", "C07"}:
                                if scenario_id == "C07" and index == 0:
                                    c07_bundle, c07_manifest = c07_bundles[
                                        c07_wave_index
                                    ]
                                    response = _upload(
                                        recorder,
                                        c07_bundle,
                                        c07_manifest,
                                        args.organization_id,
                                    )
                                    with response_lock:
                                        responses.append(response)
                                    return 1
                                digests = []
                                for route, url, params in _query_routes(
                                    samples, args.organization_id, args.execution_id
                                ):
                                    response = recorder.request(
                                        "QUERY", route, "GET", url, {200}, params=params
                                    )
                                    digests.append((route, _json_digest(response)))
                                response = None
                                with response_lock:
                                    responses.extend(digests)  # type: ignore[arg-type]
                            elif scenario_id == "C06":
                                response = recorder.request(
                                    "REPORT",
                                    "POST /reports",
                                    "POST",
                                    "/reports",
                                    {201},
                                    json={
                                        "report_type": "workorder_consolidated",
                                        "execution_id": args.execution_id,
                                        "organization_id": args.organization_id,
                                        "reference_at": _now(),
                                        "filters": {},
                                    },
                                )
                                payload = _safe_json(response)
                                exports: dict[str, httpx.Response | None] = {}
                                if response is not None and response.status_code == 201:
                                    for export_format in ("csv", "json"):
                                        exports[export_format] = recorder.request(
                                            "EXPORT",
                                            "GET /reports/version/export "
                                            f"({export_format})",
                                            "GET",
                                            f"/reports/{payload['report_id']}/versions/"
                                            f"{payload['version']}/export",
                                            {200},
                                            params={"format": export_format},
                                        )
                                with response_lock:
                                    report_exports.append((response, exports))
                            else:
                                assert isolation_recorder is not None
                                workorder = samples["workorders"]["median"]
                                serial = samples["serials"]["median"]
                                for route, url, params in (
                                    (
                                        "GET /workorders/{id}",
                                        f"/workorders/{workorder}",
                                        {"execution_id": args.execution_id},
                                    ),
                                    (
                                        "GET /serials/{id}",
                                        f"/serials/{serial}",
                                        {},
                                    ),
                                    (
                                        "GET /workorders/{id}/consolidated-result",
                                        f"/workorders/{workorder}/consolidated-result",
                                        {"execution_id": args.execution_id},
                                    ),
                                ):
                                    recorder.request(
                                        "ISOLATION_CONTROL",
                                        route,
                                        "GET",
                                        url,
                                        {200},
                                        params=params,
                                    )
                                    response = isolation_recorder.request(
                                        "ISOLATION",
                                        route,
                                        "GET",
                                        url,
                                        {404},
                                        params=params,
                                    )
                            if scenario_id not in {"C05", "C07"}:
                                with response_lock:
                                    responses.append(
                                        (index, response)
                                        if scenario_id == "C01"
                                        else response
                                    )
                            return {"C05": 8, "C06": 3, "C07": 8, "C08": 6}.get(
                                scenario_id, 1
                            )

                        active_recorder = recorder
                        active_start = len(active_recorder.samples)
                        isolation_start = (
                            len(isolation_recorder.samples)
                            if scenario_id == "C08" and isolation_recorder
                            else 0
                        )
                        wave_clients = level + 1 if scenario_id == "C07" else level
                        wave = run_wave(
                            scenario_id, wave_clients, cycle, request_task
                        )
                        if scenario_id == "C07":
                            wave.level = level
                        _record_wave_result(wave, active_recorder.samples, active_start)
                        if scenario_id == "C08" and isolation_recorder:
                            isolated = isolation_recorder.samples[isolation_start:]
                            wave.successes += sum(item.success for item in isolated)
                            wave.unexpected_errors += sum(
                                not item.success for item in isolated
                            )
                        waves.append(wave)
                        if scenario_id == "C01":
                            upload_responses = [
                                item for _, item in sorted(responses)
                            ]
                            check_distinct_uploads(
                                checks, upload_responses, level, "C01"
                            )
                            c01_wave_index += level
                            for index, response in enumerate(upload_responses):
                                _, upload_manifest = c01_bundles[
                                    c01_wave_index - level + index
                                ]
                                check_pipeline_counts(
                                    checks,
                                    recorder,
                                    response,
                                    upload_manifest,
                                    f"C01.level_{level}.cycle_{cycle}.client_{index}",
                                )
                        elif scenario_id == "C02":
                            check_c02(checks, responses, level)
                            created = [
                                item
                                for item in responses
                                if item is not None and item.status_code == 201
                            ]
                            if created:
                                _, upload_manifest = c02_bundles[c02_wave_index]
                                check_pipeline_counts(
                                    checks,
                                    recorder,
                                    created[0],
                                    upload_manifest,
                                    f"C02.level_{level}.cycle_{cycle}.winner",
                                )
                            c02_wave_index += 1
                        elif scenario_id == "C03":
                            check_c03(checks, responses, level)
                        elif scenario_id == "C04":
                            check_c04(checks, responses, level)
                        elif scenario_id in {"C05", "C07"}:
                            upload_responses = [
                                item
                                for item in responses
                                if isinstance(item, httpx.Response)
                            ]
                            if scenario_id == "C07":
                                check_distinct_uploads(
                                    checks, upload_responses, 1, "C07"
                                )
                                if upload_responses:
                                    _, upload_manifest = c07_bundles[c07_wave_index]
                                    check_pipeline_counts(
                                        checks,
                                        recorder,
                                        upload_responses[0],
                                        upload_manifest,
                                        f"C07.level_{level}.cycle_{cycle}.writer",
                                    )
                            by_route: dict[str, set[str | None]] = {}
                            query_responses = [
                                item for item in responses if isinstance(item, tuple)
                            ]
                            for route, digest in query_responses:
                                by_route.setdefault(route, set()).add(digest)
                            after_snapshot = (
                                _query_snapshot(
                                    client,
                                    samples,
                                    args.organization_id,
                                    args.execution_id,
                                )
                                if scenario_id == "C07"
                                else {}
                            )
                            for route, digests in by_route.items():
                                if scenario_id == "C05":
                                    valid = len(digests) == 1 and None not in digests
                                else:
                                    valid_snapshots = {
                                        before_snapshot[route], after_snapshot[route]
                                    }
                                    valid = (
                                        None not in digests
                                        and digests <= valid_snapshots
                                    )
                                _check(
                                    checks,
                                    f"{scenario_id}.level_{level}.cycle_{cycle}."
                                    f"{route}.consistent",
                                    True,
                                    valid,
                                )
                            if scenario_id == "C07":
                                c07_wave_index += 1
                        elif scenario_id == "C06":
                            payloads = [_safe_json(item) for item in responses]
                            _check(
                                checks,
                                f"C06.level_{level}.cycle_{cycle}.versions",
                                level,
                                len(
                                    {
                                        (item.get("report_id"), item.get("version"))
                                        for item in payloads
                                    }
                                ),
                            )
                            for index, (report, exports) in enumerate(report_exports):
                                check_report_export(
                                    checks,
                                    report,
                                    exports,
                                    f"C06.level_{level}.cycle_{cycle}.client_{index}",
                                )
                        elif scenario_id == "C08":
                            measured = isolation_recorder.samples[isolation_start:]
                            controls = active_recorder.samples[active_start:]
                            _check(
                                checks,
                                f"C08.level_{level}.cycle_{cycle}.hidden",
                                level * 3,
                                sum(
                                    item.status_code == 404 and item.success
                                    for item in measured
                                ),
                            )
                            _check(
                                checks,
                                f"C08.level_{level}.cycle_{cycle}.control_visible",
                                level * 3,
                                sum(
                                    item.status_code == 200 and item.success
                                    for item in controls
                                ),
                            )
                        if wave.unexpected_errors or not all(
                            item["passed"] for item in checks[check_start:]
                        ):
                            skipped.append(
                                {
                                    "scenario_id": scenario_id,
                                    "level": level,
                                    "cycle": cycle + 1,
                                    "reason": "erro inesperado ou oráculo falhou",
                                }
                            )
                            halt_scenario = True
                            break
                    if halt_scenario:
                        break
            if isolation_recorder:
                recorder.samples.extend(isolation_recorder.samples)
        finally:
            monitor.stop()
            if isolation_client:
                isolation_client.close()

    environment["storage"]["free_bytes_final"] = shutil.disk_usage(output).free
    summary = summarize(recorder.samples)
    summary["waves"] = [asdict(item) for item in waves]
    summary["resources"] = summarize_resources(monitor.rows)
    summary["skipped_levels"] = skipped
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
    _write_csv(
        output / "waves.csv",
        [asdict(item) for item in waves],
        tuple(Wave.__dataclass_fields__),
    )
    _write_report(output / "report.md", environment, workload, summary, checks)
    print(f"Artefatos: {output}")
    if summary["unexpected_errors"] or not summary["correctness_passed"]:
        return 1
    return 2 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
