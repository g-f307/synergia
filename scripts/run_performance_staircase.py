from __future__ import annotations

import argparse
import csv
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

import httpx

from generate_synthetic_data import validate_manifest

ROOT = Path(__file__).resolve().parents[1]


def _podman_inspect(name: str) -> dict[str, Any]:
    result = subprocess.run(
        ["podman", "inspect", name],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)[0]


def _cgroup(container: dict[str, Any]) -> Path:
    pid = container["State"]["Pid"]
    if not pid or container["State"]["Status"] != "running":
        raise ValueError("Container não está em execução")
    membership = Path(f"/proc/{pid}/cgroup").read_text().strip()
    prefix, path = membership.split("::", 1)
    if prefix != "0" or "libpod-" not in path:
        raise ValueError("Container sem cgroup v2 próprio")
    directory = Path("/sys/fs/cgroup") / path.lstrip("/")
    if not directory.is_dir():
        raise ValueError("Cgroup do container não está acessível")
    return directory


def _integer_file(path: Path) -> int:
    value = path.read_text().strip()
    if value == "max":
        raise ValueError(f"Limite não configurado: {path.name}")
    return int(value)


def _events(directory: Path) -> dict[str, int]:
    return {
        key: int(value)
        for key, value in (
            line.split()
            for line in (directory / "memory.events").read_text().splitlines()
        )
    }


def _host_available() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise ValueError("MemAvailable não disponível")


def _isolation(api: dict[str, Any], postgres: dict[str, Any]) -> dict[str, Any]:
    if api["Pod"] != postgres["Pod"] or not api["Pod"]:
        raise ValueError("API e PostgreSQL precisam pertencer ao mesmo pod isolado")
    result = {}
    for role, container in (("api", api), ("postgres", postgres)):
        config = container["HostConfig"]
        limit = int(config["Memory"])
        if limit <= 0 or config["MemorySwap"] != limit:
            raise ValueError(f"{role} exige limite de memória e swap desativada")
        directory = _cgroup(container)
        cgroup_limit = _integer_file(directory / "memory.max")
        if cgroup_limit != limit:
            raise ValueError(f"{role} não recebeu o limite de cgroup declarado")
        result[role] = {
            "container_id": container["Id"],
            "host_pid": container["State"]["Pid"],
            "memory_limit_bytes": limit,
            "memory_swap_limit_bytes": config["MemorySwap"],
            "nano_cpus": config.get("NanoCpus"),
            "cgroup": str(directory),
            "memory_events_before": _events(directory),
        }
    if (
        sum(item["memory_limit_bytes"] for item in result.values())
        > 0.8 * _host_available()
    ):
        raise ValueError(
            "Limites dos containers excedem 80% da memória disponível do host"
        )
    return result


def _bundle(value: str) -> tuple[str, Path]:
    scenario, separator, directory = value.partition("=")
    if not separator or not scenario.startswith("V") or not directory:
        raise argparse.ArgumentTypeError("Use V00=/caminho/da/massa")
    return scenario, Path(directory)


def _readiness(base_url: str) -> None:
    with httpx.Client(timeout=5) as client:
        response = client.get(f"{base_url}/health")
    if response.status_code != 200:
        raise ValueError(f"API indisponível: HTTP {response.status_code}")
    components = response.json().get("components", [])
    if not any(
        item.get("component") == "postgresql" and item.get("status") == "healthy"
        for item in components
    ):
        raise ValueError("PostgreSQL não está saudável")


def _token(base_url: str, email: str, password_env: str) -> str:
    password = os.environ.get(password_env)
    if not password:
        raise ValueError(f"Senha sintética ausente em {password_env}")
    with httpx.Client(timeout=10) as client:
        response = client.post(
            f"{base_url}/auth/login", json={"email": email, "password": password}
        )
    if response.status_code != 200:
        raise ValueError(f"Login sintético falhou: HTTP {response.status_code}")
    return response.json()["access_token"]


def _sample(api_directory: Path, pg_directory: Path, storage: Path) -> dict[str, Any]:
    api_events = _events(api_directory)
    pg_events = _events(pg_directory)
    return {
        "at": datetime.now(UTC).isoformat(),
        "api_memory_bytes": _integer_file(api_directory / "memory.current"),
        "api_memory_limit_bytes": _integer_file(api_directory / "memory.max"),
        "api_oom_kill": api_events.get("oom_kill", 0),
        "pg_memory_bytes": _integer_file(pg_directory / "memory.current"),
        "pg_memory_limit_bytes": _integer_file(pg_directory / "memory.max"),
        "pg_oom_kill": pg_events.get("oom_kill", 0),
        "host_memory_available_bytes": _host_available(),
        "storage_free_bytes": shutil.disk_usage(storage).free,
    }


def _stop_reason(
    sample: dict[str, Any], before: dict[str, Any], threshold: float
) -> str | None:
    if sample["api_oom_kill"] > before["api"]["memory_events_before"].get(
        "oom_kill", 0
    ):
        return "api_memory_oom"
    if sample["pg_oom_kill"] > before["postgres"]["memory_events_before"].get(
        "oom_kill", 0
    ):
        return "postgres_memory_oom"
    if sample["api_memory_bytes"] / sample["api_memory_limit_bytes"] >= threshold:
        return "api_memory_threshold"
    if sample["pg_memory_bytes"] / sample["pg_memory_limit_bytes"] >= threshold:
        return "postgres_memory_threshold"
    if sample["host_memory_available_bytes"] < 512 * 1024 * 1024:
        return "host_memory_safety"
    if sample["storage_free_bytes"] / shutil.disk_usage(Path.cwd()).total < 0.15:
        return "storage_safety"
    return None


def _run_step(
    args: argparse.Namespace,
    scenario: str,
    bundle: Path,
    token: str,
    isolation: dict[str, Any],
    output: Path,
) -> dict[str, Any]:
    run_id = f"{args.run_id}-{scenario.lower()}"
    command = [
        sys.executable,
        str(ROOT / "scripts/run_performance_baseline.py"),
        "--bundle",
        str(bundle),
        "--base-url",
        args.base_url,
        "--environment-name",
        args.environment_name,
        "--organization-id",
        args.organization_id,
        "--organization-code",
        args.organization_code,
        "--scenario-id",
        scenario,
        "--run-id",
        run_id,
        "--output",
        str(output),
        "--process",
        f"backend={isolation['api']['host_pid']}",
        "--metadata",
        "container_runtime=Podman 5.8.4 rootless cgroup v2",
        "--metadata",
        f"backend_limits=2 CPU/{isolation['api']['memory_limit_bytes']} B no swap",
        "--metadata",
        (
            "postgres_limits=2 CPU/"
            f"{isolation['postgres']['memory_limit_bytes']} B no swap"
        ),
        "--metadata",
        "storage_type=container overlay on btrfs",
        "--metadata",
        "resource_collection=runner procfs pg_stat and staircase cgroup v2",
        "--metadata",
        "network_topology=generator host loopback, API and PG same Podman pod",
        "--isolation-kind",
        "isolated-container",
    ]
    environment = dict(os.environ)
    environment["SYNERGIA_PERFORMANCE_TOKEN"] = token
    events_file = output / f"{run_id}-cgroup.csv"
    log_file = output / f"{run_id}-runner.log"
    reason = None
    started = time.monotonic()
    with log_file.open("w") as log, events_file.open("w", newline="") as events:
        process = subprocess.Popen(
            command, env=environment, stdout=log, stderr=subprocess.STDOUT
        )
        writer = None
        while process.poll() is None:
            sample = _sample(
                Path(isolation["api"]["cgroup"]),
                Path(isolation["postgres"]["cgroup"]),
                output,
            )
            if writer is None:
                writer = csv.DictWriter(events, fieldnames=list(sample))
                writer.writeheader()
            writer.writerow(sample)
            events.flush()
            reason = _stop_reason(sample, isolation, args.memory_stop_fraction)
            if reason or time.monotonic() - started > args.max_step_seconds:
                reason = reason or "step_timeout"
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                if reason.endswith(("threshold", "safety")):
                    subprocess.run(
                        ["podman", "stop", "--time", "2", args.api_container],
                        check=True,
                    )
                break
            time.sleep(args.sample_interval)
        exit_code = process.wait()
    run_directory = output / run_id
    summary_file = run_directory / "summary.json"
    correctness_file = run_directory / "correctness.json"
    summary = json.loads(summary_file.read_text()) if summary_file.exists() else None
    correctness = (
        json.loads(correctness_file.read_text()) if correctness_file.exists() else None
    )
    if not reason and exit_code != 0:
        reason = "runner_failed"
    if (
        not reason
        and correctness
        and not all(item.get("passed") for item in correctness["checks"])
    ):
        reason = "correctness_failed"
    if not reason and summary and summary.get("unexpected_errors", 0) > 0:
        reason = "unexpected_errors"
    return {
        "scenario_id": scenario,
        "bundle": str(bundle),
        "run_id": run_id,
        "duration_seconds": round(time.monotonic() - started, 3),
        "exit_code": exit_code,
        "stop_reason": reason,
        "summary": summary,
        "correctness": correctness,
        "cgroup_samples": str(events_file),
        "runner_log": str(log_file),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Degraus isolados até a primeira saturação"
    )
    parser.add_argument("--bundle", action="append", type=_bundle, required=True)
    parser.add_argument("--api-container", required=True)
    parser.add_argument("--postgres-container", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--environment-name", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--organization-code", required=True)
    parser.add_argument("--login-email", required=True)
    parser.add_argument("--password-env", default="SYNERGIA_PERF_SYNTHETIC_PASSWORD")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/performance")
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--max-step-seconds", type=float, default=900.0)
    parser.add_argument("--memory-stop-fraction", type=float, default=0.9)
    args = parser.parse_args()
    if not 0 < args.memory_stop_fraction < 1 or args.sample_interval <= 0:
        parser.error("threshold e intervalo de amostra inválidos")
    if (
        args.output.exists()
        and (args.output / f"{args.run_id}-staircase.json").exists()
    ):
        parser.error("run-id já utilizado")
    args.output.mkdir(parents=True, exist_ok=True)
    manifests = []
    previous = (-1, -1)
    for scenario, directory in args.bundle:
        manifest = validate_manifest(directory / "manifest.json")
        count = (manifest["entities"]["workorders"], manifest["entities"]["serials"])
        if count <= previous:
            parser.error("massas devem crescer em Workorders e seriais")
        previous = count
        manifests.append(
            {"scenario_id": scenario, "path": str(directory), "mass": manifest}
        )
    api = _podman_inspect(args.api_container)
    postgres = _podman_inspect(args.postgres_container)
    isolation = _isolation(api, postgres)
    _readiness(args.base_url)
    token = _token(args.base_url, args.login_email, args.password_env)
    result = {
        "run_id": args.run_id,
        "started_at": datetime.now(UTC).isoformat(),
        "isolation": isolation,
        "manifests": manifests,
        "steps": [],
        "first_limit": None,
    }
    for scenario, directory in args.bundle:
        step = _run_step(args, scenario, directory, token, isolation, args.output)
        result["steps"].append(step)
        if step["stop_reason"]:
            result["first_limit"] = step["stop_reason"]
            break
    result["finished_at"] = datetime.now(UTC).isoformat()
    path = args.output / f"{args.run_id}-staircase.json"
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n"
    )
    print(
        json.dumps(
            {"steps": len(result["steps"]), "first_limit": result["first_limit"]}
        )
    )
    return 0 if result["first_limit"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
