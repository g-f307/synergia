from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai_poc_foundation import (  # noqa: E402, I001
    DatasetSpec,
    ExecutionMetrics,
    LocalModelConfig,
    PoCFoundationError,
    execute_case,
    ingest,
    run_baseline,
    summarize_metrics,
    validate_output,
)

SPEC = DatasetSpec(
    required_columns=("record_id", "status", "amount"),
    column_types={"record_id": "string", "status": "string", "amount": "number"},
    domains={"status": frozenset({"valid", "warning", "error"})},
)
CSV = ROOT / "data/synthetic/ai-poc-foundation/sample.csv"
SCHEMA = ROOT / "scripts/ai_poc_schemas/quality-output-v1.json"
PROMPT = ROOT / "scripts/ai_poc_prompts/quality-v1.txt"
XLSX = ROOT / "data/synthetic/ai-poc-foundation/sample.xlsx"


class FakeRuntime:
    def generate(self, prompt: str, *, model: str) -> tuple[str, int]:
        assert "csv-001" in prompt
        return json.dumps({"schema_version": "1.0.0", "diagnoses": []}), 12


def test_ingests_and_normalizes_csv() -> None:
    assert ingest(CSV, SPEC) == [
        {"record_id": "csv-001", "status": "valid", "amount": 10.0},
        {"record_id": "csv-002", "status": "warning", "amount": 20.0},
    ]


def test_ingests_xlsx_fixture() -> None:
    assert ingest(XLSX, SPEC) == [
        {"record_id": "xlsx-001", "status": "valid", "amount": 10.0},
        {"record_id": "xlsx-002", "status": "warning", "amount": 20.0},
    ]


@pytest.mark.parametrize("suffix", [".txt", ".json"])
def test_rejects_invalid_extension(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"input{suffix}"
    path.write_text("record_id,status,amount\na,valid,1\n", encoding="utf-8")
    with pytest.raises(PoCFoundationError, match="extensão"):
        ingest(path, SPEC)


def test_rejects_invalid_domain(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("record_id,status,amount\na,unknown,1\n", encoding="utf-8")
    with pytest.raises(PoCFoundationError, match="domínio"):
        ingest(path, SPEC)


def test_rejects_unexpected_column(tmp_path: Path) -> None:
    path = tmp_path / "extra.csv"
    path.write_text(
        "record_id,status,amount,secret\na,valid,1,nope\n", encoding="utf-8"
    )
    with pytest.raises(PoCFoundationError, match="não previstas"):
        ingest(path, SPEC)


def test_rejects_invalid_output() -> None:
    with pytest.raises(PoCFoundationError, match="fora do esquema"):
        validate_output(
            {"schema_version": "1.0.0", "diagnoses": [{"code": "x"}]}, SCHEMA
        )


def test_baseline_and_agent_share_the_same_normalized_cases() -> None:
    records = ingest(CSV, SPEC)
    baseline = run_baseline("quality", records)
    assert baseline["schema_version"] == "1.0.0"
    assert [item["code"] for item in baseline["diagnoses"]] == ["STATUS_WARNING"]


def test_rejects_sensitive_model_output(tmp_path: Path) -> None:
    class LeakyRuntime(FakeRuntime):
        def generate(self, prompt: str, *, model: str) -> tuple[str, int]:
            return json.dumps(
                {
                    "schema_version": "1.0.0",
                    "diagnoses": [
                        {
                            "code": "x",
                            "severity": "warning",
                            "message": "password=secret",
                        }
                    ],
                }
            ), 1

    with pytest.raises(PoCFoundationError, match="conteúdo sensível"):
        execute_case(
            ingest(CSV, SPEC),
            PROMPT,
            SCHEMA,
            LeakyRuntime(),
            LocalModelConfig(model="synthetic-test"),
            output_dir=tmp_path,
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:11434@evil.example/api/generate",
        "http://evil.example:11434/api/generate",
        "http://[::1]:11434/api/generate?redirect=1",
    ],
)
def test_rejects_non_local_model_endpoints(endpoint: str) -> None:
    with pytest.raises(PoCFoundationError, match="endpoint"):
        LocalModelConfig(endpoint=endpoint, model="synthetic-test")


def test_accepts_ipv6_loopback_endpoint() -> None:
    config = LocalModelConfig(
        endpoint="http://[::1]:11434/api/generate", model="synthetic-test"
    )
    from scripts.ai_poc_foundation import OllamaRuntime

    OllamaRuntime(config)


def test_blocks_runtime_redirect() -> None:
    from scripts.ai_poc_foundation import _NoRedirectHandler

    with pytest.raises(PoCFoundationError, match="redirecionamento"):
        _NoRedirectHandler().redirect_request(
            None, None, 302, "found", {}, "http://evil.example"
        )


def test_p95_uses_nearest_rank() -> None:
    from scripts.ai_poc_foundation import ExecutionMetrics, summarize_metrics

    values = [
        ExecutionMetrics(str(index), "test", "", value, 1, 1, 1)
        for index, value in enumerate((1.0, 100.0))
    ]
    assert summarize_metrics(values)["p95_latency_ms"] == 100.0
    assert summarize_metrics(values)["mean_latency_ms"] == 50.5


def test_cli_report_separates_groups_and_uses_effective_model() -> None:
    from scripts.run_ai_poc import build_report

    baseline = ExecutionMetrics("b", "deterministic-baseline", "same", 1.0, 0, 0, 0)
    agent = [
        ExecutionMetrics("a1", "local-model", "same", 1.0, 10, 10, 20),
        ExecutionMetrics("a2", "local-model", "same", 100.0, 10, 0.1, 30),
    ]
    report = build_report(
        kind="quality",
        input_name="sample.csv",
        requested_repetitions=2,
        baseline_metrics=[baseline],
        agent_metrics=agent,
    )
    assert report["model"] == "local-model"
    assert report["repetitions"] == 2
    assert report["baseline"]["executions"][0]["input_sha256"] == "same"
    assert report["agent"]["summary"]["p95_latency_ms"] == 100.0
    assert report["agent"]["summary"]["mean_latency_ms"] == 50.5


def test_execution_writes_unique_sanitized_evidence(tmp_path: Path) -> None:
    records = ingest(CSV, SPEC)
    config = LocalModelConfig(model="synthetic-test")
    _, first = execute_case(
        records, PROMPT, SCHEMA, FakeRuntime(), config, output_dir=tmp_path
    )
    _, second = execute_case(
        records, PROMPT, SCHEMA, FakeRuntime(), config, output_dir=tmp_path
    )
    assert first.execution_id != second.execution_id
    assert len(list(tmp_path.glob("*.json"))) == 4
    assert summarize_metrics([first, second])["mean_tokens_per_second"] > 0
