from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_performance_baseline as performance_runner  # noqa: E402
import run_performance_concurrency as concurrency_runner  # noqa: E402
from run_performance_baseline import (  # noqa: E402
    HttpRecorder,
    Sample,
    _csv_value,
    _expected_oracle,
    _guard_rupture_environment,
    _percentile,
    _preflight,
    collect_environment,
    collect_postgres_environment,
    parse_metadata,
    parse_processes,
    summarize,
    summarize_resources,
)
from run_performance_concurrency import (  # noqa: E402
    _json_digest,
    _resource_guard,
    check_c02,
    check_c03,
    check_c04,
    check_pipeline_counts,
    run_wave,
)


def _sample(duration: float, *, success: bool = True) -> Sample:
    return Sample(
        scenario_id="V00",
        operation="QUERY",
        route="serial-detail",
        measured=True,
        started_at="2026-09-14T00:00:00+00:00",
        finished_at="2026-09-14T00:00:01+00:00",
        duration_ms=duration,
        first_byte_ms=duration / 2,
        status_code=200 if success else 500,
        expected_status="200",
        success=success,
        response_bytes=10,
        correlation_id="00000000-0000-4000-8000-000000000001",
        error_code=None if success else "unexpected",
    )


def test_percentiles_use_nearest_rank_and_summary_ignores_warmup() -> None:
    samples = [_sample(value) for value in (1, 2, 3, 4, 100)]
    warmup = _sample(999)
    warmup.measured = False
    samples.extend((warmup, _sample(5, success=False)))

    assert _percentile([1, 2, 3, 4, 100], 0.95) == 100
    summary = summarize(samples)

    assert summary["measured_samples"] == 6
    assert summary["unexpected_errors"] == 1
    operation = summary["operations"][0]
    assert operation["latency_ms"]["p50"] == 3
    assert operation["latency_ms"]["p95"] == 100
    assert operation["first_byte_ms"]["p95"] == 50
    assert operation["error_rate"] == pytest.approx(1 / 6)


def test_rupture_volume_refuses_unisolated_or_undocumented_environment() -> None:
    mass = {"entities": {"workorders": 8_500, "serials": 110_000}}
    with pytest.raises(ValueError, match="não assumir zero"):
        _guard_rupture_environment("V06", {"entities": {"workorders": 8_500}}, None, {})
    with pytest.raises(ValueError, match="isolation-kind"):
        _guard_rupture_environment("V06", mass, None, {})
    with pytest.raises(ValueError, match="limites explícitos"):
        _guard_rupture_environment("V06", mass, "isolated-container", {})
    metadata = {
        "backend_limits": "2 CPU/8 GiB",
        "postgres_limits": "2 CPU/4 GiB",
        "storage_type": "volume isolado 100 GiB",
        "container_runtime": "Docker 27",
    }
    _guard_rupture_environment("V06", mass, "isolated-container", metadata)
    with pytest.raises(ValueError, match="vm_limits"):
        _guard_rupture_environment("V06", mass, "isolated-vm", metadata)
    _guard_rupture_environment(
        "V05", {"entities": {"workorders": 6_800, "serials": 88_000}}, None, {}
    )


def test_http_recorder_keeps_only_safe_error_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Correlation-ID"]
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "duplicate_file",
                    "message": "must not be copied to samples",
                }
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://performance.test"
    )
    recorder = HttpRecorder(client, "C02")

    response = recorder.request("UPLOAD", "POST /imports", "POST", "/imports", {201})

    assert response is not None
    assert recorder.samples[0].error_code == "duplicate_file"
    assert not hasattr(recorder.samples[0], "response_body")


def test_preflight_rejects_canonical_file_above_active_policy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/imports/policy"
        return httpx.Response(
            200,
            json={
                "policies": [
                    {
                        "source": source,
                        "allowed_extensions": [extension],
                        "max_bytes": 100,
                    }
                    for source, extension in (
                        ("N-FP", "xlsx"),
                        ("OWM", "json"),
                        ("GMES/OQC", "csv"),
                        ("TMS", "json"),
                    )
                ],
                "organizations": [{"id": "org-1"}],
            },
        )

    recorder = HttpRecorder(
        httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://performance.test"
        ),
        "V05",
    )
    manifest = {
        "files": [
            {"source": "N-FP", "format": "xlsx", "size_bytes": 10},
            {"source": "OWM", "format": "json", "size_bytes": 101},
            {"source": "OWM", "format": "csv", "size_bytes": 1_000},
            {"source": "GMES/OQC", "format": "csv", "size_bytes": 10},
            {"source": "TMS", "format": "json", "size_bytes": 10},
        ]
    }

    ready, problems = _preflight(recorder, manifest, "org-1")

    assert ready is False
    assert problems == ["too_large:OWM:101"]


def test_environment_is_non_comparable_until_required_metadata_exists(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(performance_runner, "_git_value", lambda *arguments: "")
    manifest = {
        "schema_version": "1.1",
        "generator_version": "1.1.0",
        "profile": "minimal",
        "scenario": "valid",
        "seed": 1,
        "logical_digest": "abc",
        "configuration": {"workorders": 4, "serials": 12},
        "entities": {"workorders": 4, "serials": 12},
        "files": [],
    }
    incomplete = collect_environment("local", tmp_path, manifest, {})
    complete = collect_environment(
        "local",
        tmp_path,
        manifest,
        parse_metadata(
            [
                "backend_limits=2cpu/2GiB",
                "container_runtime=Docker 27",
                "network_topology=local",
                "postgres_limits=2cpu/4GiB",
                "resource_collection=runner",
                "storage_type=ssd",
            ]
        ),
    )

    assert incomplete["comparability"] == "non_comparable"
    assert complete["comparability"] == "comparable"
    assert complete["missing_required_metadata"] == []
    assert complete["comparability_issues"] == []
    assert collect_postgres_environment(None) == {"collection_status": "not_configured"}


def test_resource_summary_calculates_deltas_and_process_cpu() -> None:
    resources = summarize_resources(
        [
            {
                "timestamp": "2026-09-14T00:00:00+00:00",
                "target": "backend",
                "cpu_seconds": 10.0,
                "rss_bytes": 100,
                "read_bytes": 20,
                "write_bytes": 30,
            },
            {
                "timestamp": "2026-09-14T00:00:10+00:00",
                "target": "backend",
                "cpu_seconds": 15.0,
                "rss_bytes": 200,
                "read_bytes": 120,
                "write_bytes": 230,
            },
        ]
    )["backend"]

    assert resources["cpu_percent_average"] == 50
    assert resources["cpu_seconds_delta"] == 5
    assert resources["rss_bytes_max"] == 200
    assert resources["read_bytes_delta"] == 100
    assert resources["write_bytes_delta"] == 200


def test_manifest_oracle_rebuilds_complete_valid_result() -> None:
    manifest = json.loads(
        (ROOT / "data/synthetic/fixtures/minimal-valid/manifest.json").read_text()
    )

    oracle = _expected_oracle(manifest)

    assert oracle["counts"] == {
        "files": 4,
        "files_received": 4,
        "files_accepted": 4,
        "files_rejected": 0,
        "rows_read": 32,
        "valid_records": 32,
        "rejected_records": 0,
        "normalized_records": 32,
        "workorders": 4,
        "lots": 4,
        "serials": 12,
        "classifications": 28,
        "pending_items": 0,
        "errors": 0,
        "warnings": 0,
    }
    assert oracle["classification_count"] == 28
    assert oracle["workorder_count"] == 4
    assert oracle["oqc_count"] == 28
    assert all(len(oracle[key]) == 64 for key in (
        "classification_digest", "workorder_digest", "oqc_digest"
    ))


def test_csv_oracle_matches_export_serialization() -> None:
    assert _csv_value(None) == ""
    assert _csv_value(False) == "false"
    assert _csv_value(True) == "true"
    assert _csv_value(["SYN-LOT-001"]) == '["SYN-LOT-001"]'
    assert _csv_value("=unsafe") == "'=unsafe"


@pytest.mark.parametrize(
    "function,value",
    [
        (parse_metadata, "missing-separator"),
        (parse_processes, "backend=not-a-pid"),
    ],
)
def test_invalid_cli_metadata_is_rejected(function, value) -> None:
    with pytest.raises(ValueError):
        function([value])


def _response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def test_concurrent_wave_counts_wall_throughput_and_starts_all_clients() -> None:
    started = []
    lock = threading.Lock()

    def task(index: int) -> int:
        with lock:
            started.append(index)
        return 2

    wave = run_wave("C05", 4, 1, task)

    assert sorted(started) == [0, 1, 2, 3]
    assert wave.clients == 4
    assert wave.requests == 8
    assert wave.duration_ms > 0
    assert wave.throughput_requests_per_second > 0


def test_c02_accepts_one_upload_and_links_all_contractual_duplicates() -> None:
    created = _response(201, {"execution_id": "winner"})
    duplicate = lambda: _response(  # noqa: E731
        409,
        {
            "error": {
                "code": "duplicate_file",
                "details": {"duplicate_of_execution_id": "winner"},
            }
        },
    )
    checks = []

    check_c02(checks, [duplicate(), created, duplicate(), duplicate()], 4)

    assert checks
    assert all(item["passed"] for item in checks)
    json.dumps(checks)


def test_c02_rejects_unrelated_conflict_as_duplicate() -> None:
    checks = []
    check_c02(
        checks,
        [
            _response(201, {"execution_id": "winner"}),
            _response(
                409,
                {
                    "error": {
                        "code": "unrelated_conflict",
                        "details": {"duplicate_of_execution_id": "winner"},
                    }
                },
            ),
        ],
        2,
    )

    assert any(
        not item["passed"] and item["check"].endswith("contractual_duplicate_code")
        for item in checks
    )


def test_reprocessing_oracles_distinguish_same_and_distinct_keys() -> None:
    same_key = [
        _response(
            202,
            {
                "execution_id": "reserved",
                "idempotent_replay": replay,
            },
        )
        for replay in (False, True, True, True)
    ]
    distinct_keys = [
        _response(
            202,
            {
                "execution_id": f"reserved-{index}",
                "idempotent_replay": False,
            },
        )
        for index in range(4)
    ]
    checks = []

    check_c03(checks, same_key, 4)
    check_c04(checks, distinct_keys, 4)

    assert checks
    assert all(item["passed"] for item in checks)


def test_query_digest_excludes_only_top_level_generated_at() -> None:
    first = _response(
        200,
        {"generated_at": "2026-09-15T00:00:00Z", "items": [{"quantity": None}]},
    )
    second = _response(
        200,
        {"generated_at": "2026-09-15T00:00:01Z", "items": [{"quantity": None}]},
    )
    changed = _response(
        200,
        {"generated_at": "2026-09-15T00:00:01Z", "items": [{"quantity": 0}]},
    )

    assert _json_digest(first) == _json_digest(second)
    assert _json_digest(first) != _json_digest(changed)


def test_resource_guard_checks_memory_and_swap_before_each_cycle(monkeypatch) -> None:
    monkeypatch.setattr(concurrency_runner, "_memory_available", lambda: 1024)
    monkeypatch.setattr(concurrency_runner, "_swap_used", lambda: 2048)

    memory_reason, observed = _resource_guard(2048, 1024)
    swap_reason, _ = _resource_guard(512, 1024)
    no_reason, _ = _resource_guard(512, None)

    assert memory_reason == "memória disponível abaixo da guarda configurada"
    assert observed == {"available_memory_bytes": 1024, "swap_used_bytes": 2048}
    assert swap_reason == "swap utilizada acima da guarda configurada"
    assert no_reason is None


def test_pipeline_oracle_keeps_missing_count_distinct_from_zero() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/imports/execution-1/pipeline-summary"
        return _response(
            200,
            {
                "rows_read": 1100,
                "valid_records": 1100,
                "rejected_records": 0,
                # normalized_records deliberately absent
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://performance.test"
    )
    recorder = HttpRecorder(client, "C01")
    checks = []

    check_pipeline_counts(
        checks,
        recorder,
        _response(201, {"execution_id": "execution-1"}),
        {
            "expectations": {
                "valid_pipeline": {
                    "rows_read": 1100,
                    "valid_records": 1100,
                    "rejected_records": 0,
                    "normalized_records": 1100,
                }
            }
        },
        "C01.client_0",
    )

    assert sum(item["passed"] for item in checks) == 3
    assert checks[-1]["actual"] is None
    assert recorder.samples[0].measured is False
