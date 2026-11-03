"""Sample the dedicated local runtime; unavailable metrics stay null, never zero."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import threading
from pathlib import Path


def command(args: list[str]) -> str | None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=3)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def memory() -> dict:
    try:
        values = {
            line.split(":")[0]: int(line.split()[1]) * 1024
            for line in Path("/proc/meminfo").read_text().splitlines()
            if len(line.split()) == 3
        }
        return {
            "ram_available_bytes": values["MemAvailable"],
            "swap_used_bytes": values["SwapTotal"] - values["SwapFree"],
        }
    except (OSError, ValueError, KeyError):
        return {"ram_available_bytes": None, "swap_used_bytes": None}


def gpu_memory() -> list[dict] | None:
    raw = command(
        [
            "nvidia-smi",
            "--query-gpu=memory.total,memory.used",
            "--format=csv,noheader,nounits",
        ]
    )
    if raw is None:
        return None
    try:
        return [
            {"total_bytes": int(a) * 1024**2, "used_bytes": int(b) * 1024**2}
            for a, b in (line.split(",") for line in raw.splitlines())
        ]
    except ValueError:
        return None


def hardware() -> dict:
    """Stable identity for resume; no hostname, username, serial or dynamic free RAM."""
    try:
        info = Path("/proc/cpuinfo").read_text()
        cpu = next(
            line.split(":", 1)[1].strip()
            for line in info.splitlines()
            if line.startswith("model name")
        )
        total = next(
            int(line.split()[1]) * 1024
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemTotal:")
        )
    except (OSError, ValueError, StopIteration):
        cpu, total = platform.machine(), None
    return {
        "os": platform.system(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "cpu": cpu,
        "ram_total_bytes": total,
        "gpu_names_drivers": command(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ]
        ),
    }


def sample() -> dict:
    raw = command(["ps", "-C", "ollama,llama-server", "-o", "rss="])
    try:
        rss = sum(int(value) * 1024 for value in raw.split()) if raw else None
    except ValueError:
        rss = None
    return {**memory(), "model_rss_bytes": rss, "gpus": gpu_memory()}


def resource_failure(before: dict, current: dict, limits: dict) -> str | None:
    ram = current["ram_available_bytes"]
    if ram is None:
        return "ram_telemetry_unavailable"
    if ram < limits["minimum_available_ram_bytes"]:
        return "available_ram_limit"
    initial, used = before["swap_used_bytes"], current["swap_used_bytes"]
    if initial is None or used is None:
        return "swap_telemetry_unavailable"
    if used - initial > limits["max_swap_growth_bytes"]:
        return "swap_growth_limit"
    for gpu in current["gpus"] or []:
        if (
            gpu["total_bytes"] - gpu["used_bytes"]
            < limits["reserved_gpu_headroom_bytes"]
        ):
            return "gpu_headroom_limit"
    return None


class Sampler:
    """Resource violations stop the batch at the next request/checkpoint.

    This observer does not kill a separately managed Ollama process or promise an
    OS-enforced memory cap. In-flight HTTP calls remain bounded by their timeout.
    RSS can double-count shared pages. VRAM includes other desktop processes.
    """

    def __init__(self, limits: dict, disk_path: Path, reference: dict | None = None):
        self.limits = limits
        self.disk_path = disk_path
        self.before = sample()
        self.reference = reference or self.before
        self.values = [self.before]
        self.failure = resource_failure(self.reference, self.before, limits)
        if (
            shutil.disk_usage(disk_path).free
            < limits["minimum_available_disk_bytes_before_run"]
        ):
            self.failure = "available_disk_limit"
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._poll, daemon=True)

    def _poll(self):
        while not self.stop.wait(self.limits["rss_sampling_interval_seconds"]):
            current = sample()
            self.values.append(current)
            self.failure = self.failure or resource_failure(
                self.reference, current, self.limits
            )

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=12)
        current = sample()
        self.values.append(current)
        self.failure = self.failure or resource_failure(
            self.reference, current, self.limits
        )

    def report(self) -> dict:
        def peak(key):
            known = [v[key] for v in self.values if v[key] is not None]
            return max(known) if known else None

        vram = [
            sum(g["used_bytes"] for g in v["gpus"])
            for v in self.values
            if v["gpus"] is not None
        ]
        return {
            "samples": len(self.values),
            "before": self.before,
            "after": self.values[-1],
            "sampled_rss_peak_bytes": peak("model_rss_bytes"),
            "sampled_total_gpu_used_peak_bytes": max(vram) if vram else None,
            "swap_used_peak_bytes": peak("swap_used_bytes"),
            "resource_failure": self.failure,
            "unavailable": {
                "rss": "process_not_found_or_ps_unavailable"
                if peak("model_rss_bytes") is None
                else None,
                "vram": "nvidia_smi_unavailable_or_unsupported" if not vram else None,
            },
            "scope": "dedicated_runtime_rss_and_whole_gpu_usage_not_per_model_vram",
        }


def stable_json(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
