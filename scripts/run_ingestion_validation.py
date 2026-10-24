"""Isolated adapter volume runs; public evidence contains only approved metadata."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import logging
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ingestion_corpus import (  # noqa: E402
    canonical,
    decision,
    execute,
    workorder,
)

from app.ingestion_budget import IngestionLimitError, budget_for  # noqa: E402
from app.upload_security import UnsafeUpload, policy_for  # noqa: E402

SOURCES = ("WO Status", "Total Decision")
SCENARIOS = {
    "within_budget": (None, None),
    "row_limit": ("INGESTION_MAX_ROWS", "workbook_row_limit"),
    "cell_limit": ("INGESTION_MAX_CELLS", "workbook_dimension_limit"),
    "memory_limit": ("INGESTION_MAX_MEMORY_BYTES", "workbook_memory_limit"),
    "issue_limit": ("INGESTION_MAX_ISSUES", "ingestion_issue_limit"),
    "time_limit": ("INGESTION_MAX_SECONDS", "ingestion_time_limit"),
}


def peak_rss():
    # Linux getrusage may retain a parent's pre-exec RSS high-water mark.
    # /proc describes this worker's memory image, excluding fixture generation.
    status = Path("/proc/self/status")
    if sys.platform.startswith("linux") and status.exists():
        line = next(
            line
            for line in status.read_text().splitlines()
            if line.startswith("VmHWM:")
        )
        return int(line.split()[1]) * 1024
    import resource

    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def environment():
    cpu = platform.processor()
    if Path("/proc/cpuinfo").exists():
        cpu = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            "unavailable",
        )
    physical_memory = None
    if hasattr(os, "sysconf"):
        physical_memory = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    cgroup = Path("/sys/fs/cgroup/memory.max")
    memory_limit = cgroup.read_text().strip() if cgroup.exists() else "unavailable"
    return {
        "os": platform.system(),
        "release": platform.release(),
        "architecture": platform.machine(),
        "rss_measurement": "proc-self-VmHWM"
        if sys.platform.startswith("linux")
        else "getrusage",
        "python": platform.python_version(),
        "cpu_model": cpu,
        "logical_cpus": os.cpu_count(),
        "physical_memory_bytes": physical_memory,
        "cgroup_memory_limit_bytes": int(memory_limit)
        if memory_limit.isdigit()
        else None,
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("openpyxl", "psycopg", "fastapi")
        },
    }


def configuration(source):
    budget = asdict(budget_for(source))
    # Never emit arbitrary environment strings, connection strings or sheet names.
    return {
        "ingestion": {
            key: value
            for key, value in budget.items()
            if isinstance(value, int | float)
        },
        "authorized_contract_sheets": sorted(budget_for(source).allowed_sheets or []),
        "upload": {
            key: value
            for key, value in asdict(policy_for(source)).items()
            if isinstance(value, int | float)
        },
    }


def worker(path, source):
    logging.disable(logging.CRITICAL)
    started = time.monotonic()
    baseline = peak_rss()
    report = {"configuration": configuration(source), "file_bytes": path.stat().st_size}
    try:
        summary, _ = execute(path, source)
        report.update(outcome="completed", reconciliation=summary)
    except (UnsafeUpload, IngestionLimitError) as exc:
        report.update(
            outcome="rejected",
            reason_code=(
                getattr(exc, "code", None) or getattr(exc, "reason_code", None)
            ),
        )
        details = exc.details() if isinstance(exc, IngestionLimitError) else exc.details
        report["limit"] = {
            k: v
            for k, v in (details or {}).items()
            if k in {"limit", "observed"} and isinstance(v, int | float)
        }
    except (ValueError, OSError, MemoryError):
        report.update(outcome="failed", reason_code="validation_failed")
    report.update(
        duration_seconds=round(time.monotonic() - started, 4),
        baseline_peak_rss_bytes=baseline,
        peak_rss_bytes=peak_rss(),
    )
    return report


def run_child(path, source, scenario, timeout):
    env = os.environ.copy()
    env["SYNERGIA_INGESTION_VALIDATION_WORKER"] = "1"
    variable, expected = SCENARIOS[scenario]
    if variable:
        suffix = "_WO_STATUS" if source == "WO Status" else "_TOTAL_DECISION"
        env[variable + suffix] = "0.000001" if scenario == "time_limit" else "1"
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                str(path),
                "--source",
                source,
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        report = (
            json.loads(completed.stdout)
            if completed.returncode == 0
            else {"outcome": "failed", "reason_code": "worker_failed"}
        )
    except subprocess.TimeoutExpired:
        report = {"outcome": "failed", "reason_code": "watchdog_timeout"}
    except (OSError, ValueError):
        report = {"outcome": "failed", "reason_code": "worker_failed"}
    # stdout/stderr and OS error text are never forwarded to public artifacts.
    report.update(source=source, scenario=scenario)
    report["passed"] = (
        report["outcome"] == "completed"
        and report.get("reconciliation", {}).get("balanced") is True
        and not report.get("reconciliation", {}).get("blocking", True)
        if expected is None
        else report["outcome"] == "rejected" and report.get("reason_code") == expected
    )
    return report


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--profile", choices=("ci", "local"), default="ci")
    result.add_argument("--rows", type=int)
    result.add_argument("--source", choices=SOURCES + ("both",), default="both")
    result.add_argument("--output", type=Path)
    result.add_argument("--timeout", type=float, default=900)
    result.add_argument("--real-workbook", type=Path)
    result.add_argument("--allow-real", action="store_true")
    result.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    return result


def expected_counts(source, rows):
    windows = (
        {
            "NFP": (rows, 0, 0),
            "OWM SN": (rows + 8, 8, 0),
            "CTNR STATUS": (rows // 2, 0, 0),
            "LOT PENDING_OQC": (16, 10, 6),
        }
        if source == "WO Status"
        else {"Sheet1": (rows, 0, 0)}
    )
    return {
        sheet: {
            "read": read,
            "ignored": ignored,
            "imported": read - ignored,
            "normalized": read - ignored - rejected,
            "rejected": rejected,
            "duplicated": 0,
        }
        for sheet, (read, ignored, rejected) in windows.items()
    }


def main():
    cli = parser()
    args = cli.parse_args()
    if (
        not math.isfinite(args.timeout)
        or args.timeout <= 0
        or (args.rows is not None and args.rows < 4)
    ):
        cli.error("Timeout deve ser positivo e o perfil exige ao menos quatro linhas")
    if args.worker:
        if os.getenv("SYNERGIA_INGESTION_VALIDATION_WORKER") != "1":
            cli.error("Worker interno: utilize os perfis públicos do comando")
        if args.source not in SOURCES:
            cli.error("Worker exige uma fonte")
        print(canonical(worker(args.worker, args.source)).decode(), end="")
        return 0
    real = args.real_workbook is not None
    if real and args.rows is not None:
        cli.error("Arquivo integral não aceita redução por --rows")
    if real and (
        not args.allow_real
        or args.source not in SOURCES
        or os.getenv("CI", "").lower() in {"true", "1"}
    ):
        cli.error(
            "Arquivo real exige --allow-real, fonte explícita e ambiente fora da CI"
        )
    rows = args.rows or (1000 if args.profile == "ci" else 10000)
    sources = SOURCES if args.source == "both" else (args.source,)
    runs = []
    with tempfile.TemporaryDirectory() as directory:
        for source in sources:
            if real:
                path = args.real_workbook
            else:
                path = Path(directory) / "synthetic.xlsx"
                content = (
                    workorder(rows=rows, tail=8)[0]
                    if source == "WO Status"
                    else decision(rows=rows)
                )
                path.write_bytes(content)
            for scenario in ("within_budget",) if real else SCENARIOS:
                runs.append(run_child(path, source, scenario, args.timeout))
                if not real and scenario == "within_budget":
                    expected = expected_counts(source, rows)
                    actual = {
                        s["sheet"]: {
                            key: s[key] for key in expected.get(s["sheet"], {})
                        }
                        for s in runs[-1].get("reconciliation", {}).get("sheets", [])
                    }
                    runs[-1]["expected_normalized_by_sheet"] = {
                        sheet: counts["normalized"]
                        for sheet, counts in expected.items()
                    }
                    runs[-1]["expected_counts_by_sheet"] = expected
                    runs[-1]["passed"] = runs[-1]["passed"] and actual == expected
                print(
                    json.dumps(
                        {
                            "source": source,
                            "scenario": scenario,
                            "passed": runs[-1]["passed"],
                        }
                    ),
                    file=sys.stderr,
                    flush=True,
                )
    report = {
        "report_version": "1.0.0",
        "contains_source_values": False,
        "input_kind": "restricted_opt_in" if real else "synthetic",
        "environment": environment(),
        "profile": args.profile,
        "generated_rows_per_family": None if real else rows,
        "watchdog_seconds": args.timeout,
        "runs": runs,
        "passed": all(run["passed"] for run in runs),
        "limitations": [
            "RSS is a process high-water mark, not a per-phase delta",
            "Generation runs outside the measured worker",
            "No database writes in volume or restricted-file runs",
            "Measurements do not authorize raising production limits",
        ],
    }
    content = canonical(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)
    print(content.decode(), end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
