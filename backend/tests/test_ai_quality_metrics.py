from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_ai_quality import main, score, summarize  # noqa: E402


def sample(*, category="completeness", evidence="ev-1", outcome="succeeded"):
    context = {"occurrences": [{"code": "required_field", "evidence_id": "ev-1"}]}
    gold = {
        "expected": [["required_field", "completeness", 2, "A"]],
        "status": "completed",
    }
    report = {
        "mode": "agent",
        "schema_valid": True,
        "outcome": outcome,
        "failure": None if outcome == "succeeded" else "ungrounded_evidence",
        "elapsed_ms": 1,
        "python_peak_memory_bytes": 100,
        "diagnostic_projection": {
            "status": "completed",
            "open_questions_count": 0,
            "diagnoses": [
                {
                    "occurrence_code": "required_field",
                    "category": category,
                    "confidence": "low",
                    "evidence_ids": [evidence],
                }
            ],
        },
    }
    return {
        "file": "development/example.csv",
        "counts": {
            "read_success": True,
            "layout_valid": True,
            "rows_read": 1,
            "rows_valid": 0,
        },
        "report": report,
        "score": score(context, gold, report),
        "model_process_rss_peak_bytes": 200,
    }


def test_wrong_category_counts_false_positive_and_false_negative():
    result = sample(category="layout")["score"]
    assert (result["tp"], result["fp"], result["fn"]) == (0, 1, 1)
    assert result["classification_exact"] is False
    assert result["confusion"] == [["completeness", "layout"]]


def test_rejected_answer_still_has_raw_classification_but_not_case_success():
    result = sample(evidence="ev-99", outcome="failed")["score"]
    assert result["classification_exact"] is True
    assert result["case_correct"] is False
    assert result["correct_references"] == 0
    assert result["reference_count"] == 1


def test_failure_denominator_consistency_p95_and_deduplicated_ingestion():
    records = [sample(), sample(), sample(evidence="ev-99", outcome="failed")]
    records[-1]["report"]["elapsed_ms"] = 100
    result = summarize(records)
    assert result["agent"]["attempts"] == 3
    assert result["agent"]["accepted_rate"] == pytest.approx(2 / 3)
    assert result["agent"]["valid_semantic_consistency"] == 0
    assert result["agent"]["structured_reference_precision"] == pytest.approx(2 / 3)
    assert result["agent"]["p95_latency_ms"] == 100
    assert result["ingestion"]["files"] == 1
    assert result["ingestion"]["valid_row_rate"] == 0


def test_three_successful_equal_projections_are_consistent():
    result = summarize([sample(), sample(), sample()])
    assert result["agent"]["valid_semantic_consistency"] == 1
    assert result["agent"]["f1_micro"] == 1


def test_empty_expected_case_with_invalid_schema_is_not_counted_as_correct():
    report = copy.deepcopy(sample()["report"])
    report.update(schema_valid=False, outcome="failed", diagnostic_projection=None)
    result = score({"occurrences": []}, {"expected": [], "status": "completed"}, report)
    assert result["classification_exact"] is False
    assert result["case_correct"] is False


def test_partial_round_does_not_claim_consistency():
    assert summarize([sample()])["agent"]["valid_semantic_consistency"] is None
    assert summarize([])["ingestion"]["read_success_rate"] is None


def test_evaluation_cannot_reduce_repetitions(tmp_path):
    with pytest.raises(SystemExit):
        main(
            [
                "--split",
                "evaluation",
                "--repetitions",
                "1",
                "--output-dir",
                str(tmp_path),
            ]
        )


def test_resume_skips_completed_attempts_and_rejects_changed_freeze(
    monkeypatch, tmp_path
):
    import evaluate_ai_quality as evaluation
    from ai_quality_diagnosis import baseline

    calls = []

    class Runtime:
        response_model = "test-model"

        def generate(self, prompt, *, model):
            calls.append(model)
            context = json.loads(prompt.split("\nCONTEXTO:\n", 1)[1])
            return json.dumps(baseline(context)), 1

    monkeypatch.setattr(evaluation, "local_metadata", lambda config: {"digest": "test"})
    monkeypatch.setattr(evaluation, "OllamaRuntime", lambda *args, **kwargs: Runtime())
    args = [
        "--split",
        "development",
        "--repetitions",
        "1",
        "--output-dir",
        str(tmp_path),
    ]
    assert main(args) == 0
    records = json.loads((tmp_path / "records.json").read_text())["records"]
    assert len(records) == 16
    assert len(calls) == 8
    assert all(item["report"]["outcome"] == "succeeded" for item in records)
    assert main([*args, "--resume"]) == 0
    assert len(calls) == 8
    assert len(json.loads((tmp_path / "records.json").read_text())["records"]) == 16
    monkeypatch.setattr(evaluation, "fingerprint", lambda: {"modified": True})
    with pytest.raises(SystemExit):
        main([*args, "--resume"])
