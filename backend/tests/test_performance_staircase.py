from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from run_performance_staircase import _cpu_fractions, _stop_reason  # noqa: E402


def _sample() -> dict:
    return {
        "api_oom_kill": 0,
        "pg_oom_kill": 0,
        "api_memory_bytes": 50,
        "api_memory_limit_bytes": 100,
        "pg_memory_bytes": 50,
        "pg_memory_limit_bytes": 100,
        "host_memory_available_bytes": 1024 * 1024 * 1024,
        "storage_used_fraction": 0.5,
    }


def test_stop_reason_identifies_first_bounded_resource() -> None:
    before = {
        "api": {"memory_events_before": {"oom_kill": 0}},
        "postgres": {"memory_events_before": {"oom_kill": 0}},
    }
    sample = _sample()
    sample["api_memory_bytes"] = 90
    assert _stop_reason(sample, before, 0.9) == "api_memory_threshold"

    sample = _sample()
    sample["pg_oom_kill"] = 1
    assert _stop_reason(sample, before, 0.9) == "postgres_memory_oom"

    sample = _sample()
    sample["storage_used_fraction"] = 0.85
    assert _stop_reason(sample, before, 0.9) == "storage_safety"


def test_cpu_fraction_is_relative_to_effective_cgroup_limit() -> None:
    previous = {
        "monotonic_seconds": 10.0,
        "api_cpu_usage_usec": 1_000_000,
        "pg_cpu_usage_usec": 2_000_000,
    }
    sample = {
        "monotonic_seconds": 12.0,
        "api_cpu_usage_usec": 3_000_000,
        "pg_cpu_usage_usec": 3_000_000,
        "api_cpu_fraction": None,
        "pg_cpu_fraction": None,
    }
    isolation = {
        "api": {"cpu_limit": {"cpus": 2.0}},
        "postgres": {"cpu_limit": {"cpus": 1.0}},
    }

    _cpu_fractions(sample, previous, isolation)

    assert sample["api_cpu_fraction"] == 0.5
    assert sample["pg_cpu_fraction"] == 0.5
