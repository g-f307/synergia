"""Offline regression tests, not evidence of real model quality."""

from __future__ import annotations

import copy
import json
import sys
import tracemalloc
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ai_poc_foundation import (  # noqa: E402
    LocalModelConfig,
    LocalRuntimeTimeout,
    OllamaRuntime,
    PoCFoundationError,
)
from ai_quality_diagnosis import (  # noqa: E402
    baseline,
    build_context,
    run_attempt,
    validate_pair,
)
from build_ai_quality_dataset import DATASET, stable_workbook, verify  # noqa: E402
from run_ai_quality import main  # noqa: E402

SCENARIOS = json.loads((DATASET / "scenarios.json").read_text(encoding="utf-8"))
CASES = SCENARIOS["cases"]


def context_for(case: dict, extension: str = "csv") -> dict:
    return build_context(
        DATASET / case["split"] / f"{case['case_id']}.{extension}",
        source=case["source"],
        case_id=case["case_id"],
        references_available=case["references_available"],
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_ingestion_and_baseline_against_independent_annotations(case, extension):
    context = context_for(case, extension)
    expected = [(code, row, column) for code, _, row, column in case["expected"]]
    assert [
        (item["code"], item["row"], item["column"]) for item in context["occurrences"]
    ] == expected
    for item in context["occurrences"]:
        if item["row"] is not None:
            assert item["sheet"] == ("CSV" if extension == "csv" else "Dados")
    output = baseline(context)
    validate_pair(context, output)
    assert output["status"] == case["status"]
    assert {
        (item["occurrence_code"], item["category"]) for item in output["diagnoses"]
    } == {(code, category) for code, category, _, _ in case["expected"]}
    assert {ref for item in output["diagnoses"] for ref in item["evidence_ids"]} == {
        item["evidence_id"] for item in context["occurrences"]
    }
    assert context["counts"]["read_success"] is not case.get("unreadable", False)
    assert "Ignore previous instructions" not in json.dumps(context)
    assert "WO-SYN" not in json.dumps(context)


def test_manifest_and_workbook_are_reproducible():
    assert verify() == []
    assert stable_workbook(
        ["workorder", "status"], [["WO-SYN", "x"]]
    ) == stable_workbook(["workorder", "status"], [["WO-SYN", "x"]])
    manifest = json.loads((DATASET / "manifest.json").read_text())
    assert len(manifest["files"]) == 32
    assert len({item["file"] for item in manifest["files"]}) == 32
    assert SCENARIOS["gold_review"]["status"] == "approved_by_user"


def test_counts_exclude_invalid_rows_and_layout_errors():
    mixed = context_for(next(case for case in CASES if case["label"] == "mixed"))
    assert mixed["counts"] == {
        "rows_read": 2,
        "rows_valid": 1,
        "normalized_records": 1,
        "errors": 3,
        "warnings": 0,
        "read_success": True,
        "layout_valid": True,
    }
    layout = context_for(next(case for case in CASES if case["label"] == "layout"))
    assert layout["counts"]["rows_valid"] == 0
    assert layout["counts"]["layout_valid"] is False
    assert layout["normalized_records"] == []
    assert mixed["normalized_records"] == [
        {
            "sheet": "CSV",
            "row": 3,
            "state": None,
            "oqc_flag": None,
            "quantities": [{"field": "planned_quantity", "value": 8.0}],
        }
    ]


def test_normalized_projection_does_not_expose_unmapped_free_text():
    context = context_for(CASES[3])
    assert context["normalized_records"][0]["state"] is None
    assert "SYN-NOT-MAPPED" not in json.dumps(context)


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("case", "case_mismatch"),
        ("invented", "ungrounded_evidence"),
        ("swapped", "ungrounded_evidence"),
        ("duplicate", "duplicate_diagnosis"),
        ("extra", "invalid_output_schema"),
        ("review", "invalid_output_schema"),
        ("cause", "invalid_output_schema"),
        ("sensitive", "conteúdo sensível"),
    ],
)
def test_rejects_invalid_or_ungrounded_diagnoses(mutation, code):
    context = context_for(next(case for case in CASES if case["label"] == "mixed"))
    output = baseline(context)
    diagnosis = output["diagnoses"][0]
    if mutation == "case":
        output["case_id"] = "another-case"
    elif mutation == "invented":
        diagnosis["evidence_ids"] = ["ev-999"]
    elif mutation == "swapped":
        diagnosis["evidence_ids"] = output["diagnoses"][1]["evidence_ids"]
    elif mutation == "duplicate":
        output["diagnoses"].append(copy.deepcopy(diagnosis))
    elif mutation == "extra":
        diagnosis["execute_action"] = True
    elif mutation == "review":
        diagnosis["human_review_required"] = False
    elif mutation == "cause":
        diagnosis["probable_cause"]["kind"] = "fact"
    elif mutation == "sensitive":
        diagnosis["summary"] = "authorization: Bearer synthetic-forbidden"
    with pytest.raises(PoCFoundationError, match=code):
        validate_pair(context, output)


def test_incomplete_reference_requires_abstention():
    context = context_for(
        next(case for case in CASES if case["label"] == "incomplete_reference")
    )
    output = baseline(context)
    output["status"] = "completed"
    with pytest.raises(PoCFoundationError, match="unsupported_certainty"):
        validate_pair(context, output)


class FakeRuntime:
    response_model = "fake-test-model"

    def __init__(self, response):
        self.response = response
        self.prompt = ""

    def generate(self, prompt, *, model):
        self.prompt = prompt
        if isinstance(self.response, Exception):
            raise self.response
        return self.response, 12


@pytest.mark.parametrize(
    "response,expected",
    [
        ("not JSON", "invalid_json"),
        ("{}", "invalid_output_schema"),
        (TimeoutError("private detail"), "runtime_timeout"),
        (RuntimeError("sensitive unexpected detail"), "unexpected_failure"),
        (
            PoCFoundationError("local runtime unavailable"),
            "runtime_or_sensitive_content_failure",
        ),
    ],
)
def test_every_failure_is_recorded_without_raw_response_or_baseline(
    tmp_path, response, expected
):
    report = run_attempt(
        context_for(CASES[1]),
        runtime=FakeRuntime(response),
        model="fake-test-model",
        output_dir=tmp_path,
    )
    assert report["outcome"] == "failed"
    assert report["failure"] == expected
    assert not list(tmp_path.glob("*/output.json"))
    assert len(list(tmp_path.glob("*/attempt.json"))) == 1
    assert "private detail" not in json.dumps(report)
    assert "sensitive unexpected detail" not in json.dumps(report)
    assert not tracemalloc.is_tracing()


def test_success_keeps_model_provenance_and_unique_attempts(tmp_path):
    context = context_for(CASES[1])
    runtime = FakeRuntime(json.dumps(baseline(context)))
    reports = [
        run_attempt(
            context,
            runtime=runtime,
            model="fake-test-model",
            output_dir=tmp_path,
            parameters={"seed": 125},
        )
        for _ in range(2)
    ]
    assert reports[0]["attempt_id"] != reports[1]["attempt_id"]
    assert all(report["outcome"] == "succeeded" for report in reports)
    assert all(report["model_reported"] == "fake-test-model" for report in reports)
    assert all(report["parameters"] == {"seed": 125} for report in reports)
    assert "expected" not in runtime.prompt
    assert "acceptable_hypotheses" not in runtime.prompt
    assert reports[0]["input_sha256"] == reports[1]["input_sha256"]
    assert reports[0]["python_peak_memory_bytes"] > 0


def test_cli_baseline_and_frozen_input_guard(tmp_path):
    path = DATASET / "development/QD2-D01.csv"
    assert (
        main(
            [
                "--input",
                str(path),
                "--case-id",
                "QD2-D01",
                "--mode",
                "baseline",
                "--output-dir",
                str(tmp_path),
                "--synthetic-only",
            ]
        )
        == 0
    )
    assert len(list(tmp_path.glob("*/output.json"))) == 1
    with pytest.raises(SystemExit):
        main(
            [
                "--input",
                str(path),
                "--case-id",
                "wrong-case",
                "--output-dir",
                str(tmp_path),
                "--synthetic-only",
            ]
        )


def test_invalid_extension_never_reaches_parser(tmp_path):
    with pytest.raises(PoCFoundationError, match="unsupported_source"):
        build_context(tmp_path / "data.exe", source="N-FP", case_id="bad")


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(),
        urllib.error.URLError(TimeoutError()),
    ],
)
def test_real_runtime_adapter_classifies_deadline(monkeypatch, tmp_path, error):
    class Opener:
        def open(self, request, timeout):
            raise error

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    runtime = OllamaRuntime(LocalModelConfig(model="test-model"))
    with pytest.raises(LocalRuntimeTimeout):
        runtime.generate("test", model="test-model")
    report = run_attempt(
        context_for(CASES[1]), runtime=runtime, model="test-model", output_dir=tmp_path
    )
    assert report["failure"] == "runtime_timeout"


def test_runtime_transmits_parameters_and_json_schema(monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"response": "{}", "eval_count": 3, "model": "actual-model"}'

    class Opener:
        def open(self, request, timeout):
            requests.append(json.loads(request.data))
            return Response()

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    runtime = OllamaRuntime(
        LocalModelConfig(model="test-model"),
        options={"temperature": 0, "seed": 125},
        output_schema={"type": "object"},
    )
    assert runtime.generate("test", model="test-model") == ("{}", 3)
    assert requests == [
        {
            "model": "test-model",
            "prompt": "test",
            "stream": False,
            "options": {"temperature": 0, "seed": 125},
            "format": {"type": "object"},
        }
    ]
    assert runtime.response_model == "actual-model"


def test_fabricated_evidence_is_a_failed_attempt_not_a_baseline(tmp_path):
    context = context_for(CASES[1])
    output = baseline(context)
    output["diagnoses"][0]["evidence_ids"] = ["ev-999"]
    report = run_attempt(
        context,
        runtime=FakeRuntime(json.dumps(output)),
        model="test-model",
        output_dir=tmp_path,
    )
    assert report["failure"] == "ungrounded_evidence"
    assert not list(tmp_path.glob("*/output.json"))


def test_sources_remain_unchanged_after_context_and_baseline():
    before = (DATASET / "manifest.json").read_bytes()
    for case in CASES:
        for extension in ("csv", "xlsx"):
            baseline(context_for(case, extension))
    assert verify() == []
    assert (DATASET / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("timeout", ["0", "-1", "901", "nan"])
def test_cli_rejects_invalid_timeout(tmp_path, timeout):
    with pytest.raises(SystemExit):
        main(
            [
                "--input",
                str(DATASET / "development/QD2-D01.csv"),
                "--case-id",
                "QD2-D01",
                "--synthetic-only",
                "--output-dir",
                str(tmp_path),
                "--timeout-seconds",
                timeout,
            ]
        )


def test_cli_records_effective_timeout_and_context(monkeypatch, tmp_path):
    received = {}

    def runtime_factory(config, *, options, output_schema):
        received["timeout"] = config.timeout_seconds
        received["options"] = options
        return FakeRuntime(json.dumps(baseline(context_for(CASES[0]))))

    monkeypatch.setattr("run_ai_quality.OllamaRuntime", runtime_factory)
    assert (
        main(
            [
                "--input",
                str(DATASET / "development/QD2-D01.csv"),
                "--case-id",
                "QD2-D01",
                "--synthetic-only",
                "--mode",
                "agent",
                "--output-dir",
                str(tmp_path),
                "--timeout-seconds",
                "240",
            ]
        )
        == 0
    )
    assert received["timeout"] == 240
    assert received["options"]["num_ctx"] == 4096
    assert "request_timeout_seconds" not in received["options"]
    report = json.loads(next(tmp_path.glob("*/attempt.json")).read_text())
    assert report["parameters"]["request_timeout_seconds"] == 240


def test_unknown_state_requires_abstention():
    context = context_for(CASES[3])
    output = baseline(context)
    output["status"] = "completed"
    with pytest.raises(PoCFoundationError, match="unsupported_certainty"):
        validate_pair(context, output)


def test_completed_diagnosis_cannot_have_unresolved_questions():
    context = context_for(CASES[2])
    output = baseline(context)
    output["open_questions"] = ["Qual formato é esperado?"]
    with pytest.raises(PoCFoundationError, match="unexpected_open_question"):
        validate_pair(context, output)
