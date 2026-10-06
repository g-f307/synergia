"""Isolated, advisory quality PoC. No database, writes to sources or tools for AI."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
import time
import tracemalloc
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from ai_poc_foundation import (
    LocalRuntimeTimeout,
    ModelRuntime,
    PoCFoundationError,
    _reject_sensitive_content,
)
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.normalization import RULES_PATH, STATE_MAP, normalize_tables  # noqa: E402
from app.validation import SCHEMAS, read_tables, validate_tables  # noqa: E402

SCHEMA_DIR = ROOT / "docs/schemas"
PROMPT = ROOT / "scripts/ai_poc_prompts/quality-v2.1.txt"
LAYOUT_CODES = {"invalid_header", "missing_column", "invalid_structure"}
CATEGORIES = {
    "read_error": "reading",
    "empty_file": "completeness",
    "invalid_header": "layout",
    "missing_column": "layout",
    "invalid_structure": "layout",
    "required_field": "completeness",
    "empty_row": "completeness",
    "invalid_quantity": "format",
    "invalid_date": "format",
    "invalid_identifier": "format",
    "invalid_formula": "format",
    "broken_reference": "reference",
    "duplicate_row": "consistency",
    "duplicate_serial": "consistency",
    "unmatched_key": "reference",
    "unknown_organization": "reference",
    "missing_reference_data": "reference",
    "unknown_state": "unknown",
    "unknown_oqc_flag": "unknown",
}


class DiagnosisError(PoCFoundationError):
    """Controlled failure code safe for local attempt metadata."""


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def schema(kind: str) -> dict[str, Any]:
    return json.loads(
        (SCHEMA_DIR / f"ai-quality-diagnosis-v2-{kind}.schema.json").read_text()
    )


def validate_document(value: Any, kind: str) -> None:
    # Never expose jsonschema's raw instance/error messages in attempt artifacts.
    if not Draft202012Validator(schema(kind)).is_valid(value):
        raise DiagnosisError(f"invalid_{kind}_schema")
    _reject_sensitive_content(value)


def build_context(
    path: Path,
    *,
    source: str,
    case_id: str,
    references_available: bool = True,
) -> dict[str, Any]:
    """Use production's pure validation/normalization, not its persistence pipeline.

    Only diagnostic metadata enters the model context, never arbitrary cell values.
    rows_valid excludes error rows and all rows in sheets with layout errors.
    """
    if source not in SCHEMAS or path.suffix.lower() not in {".csv", ".xlsx"}:
        raise PoCFoundationError("unsupported_source_or_extension")
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise PoCFoundationError("missing_or_oversized_file")
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    tables = []
    read_success = True
    try:
        if path.suffix.lower() == ".xlsx":
            with ZipFile(path) as archive:
                if sum(item.file_size for item in archive.infolist()) > 20 * 1024**2:
                    raise PoCFoundationError("expanded_file_too_large")
        tables, initial = read_tables(path, path.suffix.lower(), source)
    except PoCFoundationError:
        raise
    except Exception:
        # Parsers raise multiple library-specific exceptions. No raw error is kept.
        # KeyboardInterrupt/SystemExit are deliberately not caught.
        read_success = False
        initial = [
            {
                "code": "read_error",
                "severity": "error",
                "reason": "Não foi possível ler o arquivo sintético",
                "sheet": None,
                "row": None,
                "column": None,
            }
        ]
    if sum(len(rows) for _, _, rows in tables) > 10_000:
        raise PoCFoundationError("too_many_rows")
    report = validate_tables(tables, source, initial_issues=initial)
    issues = report["issues"] if read_success else initial
    bad_sheets = {item["sheet"] for item in issues if item["code"] in LAYOUT_CODES}
    bad_rows = {
        (item["sheet"], item["row"]) for item in issues if item["severity"] == "error"
    }
    eligible = {
        (sheet, getattr(row, "row_number", index))
        for sheet, _, rows in tables
        for index, row in enumerate(rows, 2)
        if sheet not in bad_sheets
        and (sheet, getattr(row, "row_number", index)) not in bad_rows
        and any(value not in (None, "") for value in row)
    }
    normalized = normalize_tables(tables, source, eligible_rows=eligible)
    issues = [*issues, *normalized["issues"]]
    if not references_available:
        issues.append(
            {
                "code": "missing_reference_data",
                "severity": "warning",
                "reason": "Base de referência não fornecida",
                "sheet": None,
                "row": None,
                "column": None,
            }
        )
    context = {
        "schema_version": "2.0.0",
        "case_id": case_id,
        "source": source,
        "file_sha256": file_hash,
        "normalized_records": [
            {
                "sheet": record["sheet"],
                "row": record["row"],
                "state": record["values"].get("status")
                if record["values"].get("status") in set(STATE_MAP.values())
                else None,
                "oqc_flag": record["values"].get("oqc_flag")
                if isinstance(record["values"].get("oqc_flag"), bool)
                else None,
                "quantities": [
                    {"field": field, "value": float(record["values"][field])}
                    for field in SCHEMAS[source].quantities
                    if record["values"].get(field) not in (None, "")
                ],
            }
            for record in normalized["records"]
        ],
        "counts": {
            "rows_read": report["row_count"],
            "rows_valid": len(eligible),
            "normalized_records": normalized["record_count"],
            "errors": sum(item["severity"] == "error" for item in issues),
            "warnings": sum(item["severity"] == "warning" for item in issues),
            "read_success": read_success,
            "layout_valid": read_success and not bad_sheets,
        },
        "occurrences": [
            {
                "evidence_id": f"ev-{index}",
                **{
                    key: item.get(key)
                    for key in ("code", "severity", "reason", "sheet", "row", "column")
                },
            }
            for index, item in enumerate(issues, 1)
        ],
    }
    validate_document(context, "input")
    return context


def baseline(context: dict[str, Any]) -> dict[str, Any]:
    """Rule-only reference. Has no access to the evaluation set or gold."""
    validate_document(context, "input")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occurrence in context["occurrences"]:
        groups[occurrence["code"]].append(occurrence)
    uncertain = any(
        code == "missing_reference_data" or CATEGORIES.get(code, "unknown") == "unknown"
        for code in groups
    )
    output = {
        "schema_version": "2.0.0",
        "case_id": context["case_id"],
        "status": "insufficient_evidence" if uncertain else "completed",
        "open_questions": ["Qual referência confirma o valor esperado?"]
        if uncertain
        else [],
        "diagnoses": [
            {
                "occurrence_code": code,
                "category": CATEGORIES.get(code, "unknown"),
                "summary": items[0]["reason"],
                "probable_cause": {
                    "kind": "hypothesis",
                    "description": (
                        "Possível divergência na origem; causa não confirmada."
                    ),
                },
                "verification_action": (
                    "Conferir a origem nas posições citadas antes de agir."
                ),
                "confidence": "low",
                "human_review_required": True,
                "evidence_ids": [item["evidence_id"] for item in items],
            }
            for code, items in sorted(groups.items())
        ],
    }
    validate_pair(context, output)
    return output


def validate_pair(context: dict[str, Any], output: Any) -> None:
    validate_document(context, "input")
    validate_document(output, "output")
    if output["case_id"] != context["case_id"]:
        raise DiagnosisError("case_mismatch")
    evidence = {item["evidence_id"]: item["code"] for item in context["occurrences"]}
    if len(evidence) != len(context["occurrences"]):
        raise DiagnosisError("duplicate_input_evidence")
    seen = set()
    for diagnosis in output["diagnoses"]:
        code = diagnosis["occurrence_code"]
        if code in seen:
            raise DiagnosisError("duplicate_diagnosis")
        seen.add(code)
        if any(evidence.get(ref) != code for ref in diagnosis["evidence_ids"]):
            raise DiagnosisError("ungrounded_evidence")
    # Missing diagnoses are measurable false negatives, not repaired by baseline.
    if output["status"] == "insufficient_evidence" and not output["open_questions"]:
        raise DiagnosisError("missing_open_question")
    uncertain_codes = {
        code
        for code in evidence.values()
        if code == "missing_reference_data"
        or CATEGORIES.get(code, "unknown") == "unknown"
    }
    if uncertain_codes:
        if output["status"] != "insufficient_evidence":
            raise DiagnosisError("unsupported_certainty")
        if any(
            item["confidence"] != "low"
            for item in output["diagnoses"]
            if item["occurrence_code"] in uncertain_codes
        ):
            raise DiagnosisError("unsupported_certainty")
    if output["status"] == "completed" and output["open_questions"]:
        raise DiagnosisError("unexpected_open_question")


def run_attempt(
    context: dict[str, Any],
    *,
    runtime: ModelRuntime | None,
    model: str,
    output_dir: Path,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist every attempt, including invalid JSON/runtime failure; no fallback.

    Raw invalid model responses are hashed, never persisted (may contain secrets).
    Peak memory measures Python allocations only, not model RSS/VRAM.
    """
    attempt_dir = output_dir / str(uuid.uuid4())
    attempt_dir.mkdir(parents=True, exist_ok=False)
    prompt = PROMPT.read_text(encoding="utf-8")
    report = {
        "attempt_id": attempt_dir.name,
        "started_at": datetime.now(UTC).isoformat(),
        "python_version": platform.python_version(),
        "case_id": context.get("case_id"),
        "mode": "agent" if runtime else "baseline",
        "model_requested": model,
        "model_reported": None,
        "parameters": parameters or {},
        "input_sha256": digest(context),
        "prompt_sha256": digest(prompt),
        "schema_sha256": digest(schema("output")),
        "schema_version": "2.0.0",
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "validation_sha256": hashlib.sha256(
            (ROOT / "backend/app/validation.py").read_bytes()
        ).hexdigest(),
        "normalization_sha256": hashlib.sha256(
            (ROOT / "backend/app/normalization.py").read_bytes()
        ).hexdigest(),
        "input_schema_sha256": digest(schema("input")),
        "normalization_rules_sha256": hashlib.sha256(
            RULES_PATH.read_bytes()
        ).hexdigest(),
        "outcome": "failed",
        "failure": None,
        "generated_tokens": 0,
        "schema_valid": False,
        "diagnostic_projection": None,
        "runtime_metrics": {},
    }
    started = time.perf_counter()
    tracemalloc.start()
    try:
        validate_document(context, "input")
        if runtime is None:
            output = baseline(context)
        else:
            raw, count = runtime.generate(
                prompt
                + "\nSCHEMA:\n"
                + json.dumps(schema("output"))
                + "\nCONTEXTO:\n"
                + json.dumps(context, ensure_ascii=False),
                model=model,
            )
            report["response_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
            report["generated_tokens"] = count
            reported = getattr(runtime, "response_model", None)
            if isinstance(reported, str) and re.fullmatch(
                r"[A-Za-z0-9_.:/-]{1,160}", reported
            ):
                _reject_sensitive_content(reported)
                report["model_reported"] = reported
            output = json.loads(raw)
            report["runtime_metrics"] = getattr(runtime, "response_metrics", {})
        report["schema_valid"] = Draft202012Validator(schema("output")).is_valid(output)
        validate_document(output, "output")
        # Closed-schema structural facts permit scoring rejected answers without
        # persisting their free text. This is never used as an accepted diagnosis.
        report["diagnostic_projection"] = {
            "status": output["status"],
            "open_questions_count": len(output["open_questions"]),
            "diagnoses": [
                {
                    key: item[key]
                    for key in (
                        "occurrence_code",
                        "category",
                        "confidence",
                        "evidence_ids",
                    )
                }
                for item in output["diagnoses"]
            ],
        }
        validate_pair(context, output)
        (attempt_dir / "output.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report["outcome"] = "succeeded"
    except json.JSONDecodeError:
        report["failure"] = "invalid_json"
    except (TimeoutError, LocalRuntimeTimeout):
        report["failure"] = "runtime_timeout"
    except DiagnosisError as exc:
        report["failure"] = str(exc)
    except PoCFoundationError:
        report["failure"] = "runtime_or_sensitive_content_failure"
    except Exception:
        report["failure"] = "unexpected_failure"
    finally:
        report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        report["python_peak_memory_bytes"] = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        (attempt_dir / "attempt.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return report
