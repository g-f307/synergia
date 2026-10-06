"""Local-only operational investigation PoC with controlled read tools."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from ai_poc_foundation import (
        ModelRuntime,
        PoCFoundationError,
        _reject_sensitive_content,
    )
except ModuleNotFoundError:
    from scripts.ai_poc_foundation import (
        ModelRuntime,
        PoCFoundationError,
        _reject_sensitive_content,
    )
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/schemas/ai-operational-summary-output.schema.json"
PROMPT = ROOT / "scripts/ai_poc_prompts/operational-v2.txt"


class OperationalPoCError(PoCFoundationError):
    """Controlled, non-sensitive failure in the operational PoC."""


@dataclass(frozen=True)
class ToolSpec:
    required: frozenset[str]
    optional: frozenset[str]


TOOL_SPECS = {
    "get_execution": ToolSpec(frozenset({"execution_id"}), frozenset()),
    "list_pending": ToolSpec(frozenset(), frozenset({"status", "priority", "limit"})),
    "list_events": ToolSpec(frozenset(), frozenset({"entity_id", "limit"})),
}


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OperationalPoCError("caso operacional inválido") from exc
    _reject_sensitive_content(payload)
    return payload


def load_case(path: Path) -> dict[str, Any]:
    case = _load(path)
    validator = Draft202012Validator(
        json.loads(
            (ROOT / "docs/schemas/ai-operational-summary-input.schema.json").read_text(
                encoding="utf-8"
            )
        ),
        format_checker=FormatChecker(),
    )
    errors = list(validator.iter_errors(case))
    if errors:
        raise OperationalPoCError("caso operacional fora do esquema")
    evidence_ids = [
        item["evidence_id"]
        for collection in ("pending_items", "classifications", "events")
        for item in case[collection]
    ]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise OperationalPoCError("evidence_id duplicado")
    return case


class ToolRegistry:
    """Allowlisted, read-only views over one validated case."""

    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case

    def call(
        self, name: str, arguments: dict[str, Any]
    ) -> list[dict[str, Any]] | dict[str, Any]:
        spec = TOOL_SPECS.get(name)
        if spec is None:
            raise OperationalPoCError("tool não autorizada")
        keys = set(arguments)
        if not spec.required <= keys or not keys <= spec.required | spec.optional:
            raise OperationalPoCError("parâmetros de tool não autorizados")
        limit = arguments.get("limit", 50)
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 50
        ):
            raise OperationalPoCError("limit fora do domínio")
        if name == "get_execution":
            if arguments["execution_id"] != self.case["execution"]["execution_id"]:
                return {}
            return {"evidence_id": "execution", **self.case["execution"]}
        if name == "list_pending":
            result = self.case["pending_items"]
            for key in ("status", "priority"):
                if key in arguments:
                    result = [item for item in result if item[key] == arguments[key]]
            return result[:limit]
        result = self.case["events"]
        if "entity_id" in arguments:
            result = [
                item
                for item in result
                if item.get("entity_id") == arguments["entity_id"]
            ]
        return result[:limit]


def tool_context(case: dict[str, Any]) -> dict[str, Any]:
    registry = ToolRegistry(case)
    return {
        "execution": registry.call(
            "get_execution", {"execution_id": case["execution"]["execution_id"]}
        ),
        "pending_items": registry.call("list_pending", {"limit": 50}),
        "events": registry.call("list_events", {"limit": 50}),
        "classification_count": len(case["classifications"]),
    }


def baseline(case: dict[str, Any]) -> dict[str, Any]:
    pending = case["pending_items"]
    findings = [
        {
            "finding_id": f"pending:{item['id']}",
            "title": f"Pendência {item['id']}",
            "severity": "critical" if item["priority"] == "critical" else "warning",
            "statement": item["reason"],
            "evidence_ids": [item["evidence_id"]],
        }
        for item in pending
    ]
    return {
        "schema_version": "1.1.0",
        "case_id": case["case_id"],
        "status": (
            "insufficient_evidence"
            if case["execution"]["lifecycle"] == "partial"
            and not (pending or case["classifications"] or case["events"])
            else "completed"
        ),
        "summary": (
            f"Execução {case['execution']['status']} com {len(pending)} pendência(s)."
        ),
        "findings": findings,
        "open_questions": []
        if pending or case["events"]
        else ["Quais evidências autorizadas estão disponíveis?"],
        "human_next_steps": ["Validar os achados com as evidências exibidas."],
    }


def validate_output(case: dict[str, Any], output: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    if not Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(
        output
    ):
        raise OperationalPoCError("saída fora do esquema operacional")
    if output.get("case_id") != case["case_id"]:
        raise OperationalPoCError("case_id divergente")
    available = {
        item["evidence_id"]
        for collection in ("pending_items", "classifications", "events")
        for item in case[collection]
    } | {"execution"}
    for finding in output["findings"]:
        if not set(finding["evidence_ids"]) <= available:
            raise OperationalPoCError("evidência não encontrada no caso")
    if output["status"] == "insufficient_evidence" and not output["open_questions"]:
        raise OperationalPoCError("abstenção sem pergunta aberta")
    _reject_sensitive_content(output)


def run_agent(
    case: dict[str, Any], runtime: ModelRuntime, model: str
) -> dict[str, Any]:
    prompt = PROMPT.read_text(encoding="utf-8")
    raw, _ = runtime.generate(
        prompt
        + "\nFERRAMENTAS:\n"
        + json.dumps(tool_context(case), ensure_ascii=False),
        model=model,
    )
    try:
        output = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OperationalPoCError("agente não produziu JSON") from exc
    validate_output(case, output)
    return output


def case_hash(case: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(case, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
