"""Controlled explanations shared by the integrated UI and offline evaluation."""

from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ASSETS = Path(__file__).with_name("ai_quality_assets")
CAUSE_LIMIT = "A causa não pode ser determinada pelas evidências disponíveis."
VALUE_LIMIT = "O valor ausente não pode ser determinado."
LABELS = {
    "required_field": "Há campo obrigatório sem preenchimento",
    "invalid_quantity": "Há quantidade fora do formato permitido",
    "invalid_date": "Há data fora do formato permitido",
    "invalid_identifier": "Há identificador fora do formato permitido",
    "duplicate_serial": "Há repetição de serial",
    "duplicate_row": "Há repetição de registro",
    "missing_column": "Há coluna obrigatória ausente",
    "invalid_header": "Há problema no cabeçalho",
    "invalid_structure": "Há problema na estrutura",
    "invalid_formula": "Há erro de fórmula",
    "broken_reference": "Há referência de fórmula inválida",
    "unknown_state": "Há estado sem mapeamento",
    "unknown_oqc_flag": "Há indicador OQC sem mapeamento",
    "missing_reference_data": "A base de referência não foi fornecida",
    "empty_row": "Há linha sem preenchimento",
    "empty_file": "O arquivo não contém registros",
    "read_error": "Não foi possível ler o arquivo",
}


class ExplanationError(ValueError):
    """Only fixed rejection codes; never include refused text."""


class RuntimeUnavailable(Exception):
    pass


class TextOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    explanation: str = Field(min_length=20, max_length=400)
    human_checks: list[str] = Field(min_length=1, max_length=3)


def language(group: dict) -> dict:
    observation = LABELS.get(
        group["code"], "Há ocorrência sem interpretação disponível"
    )
    limit = CAUSE_LIMIT
    if any(o["unknown_value"]["state"] == "missing" for o in group["occurrences"]):
        limit += " " + VALUE_LIMIT
    return {
        "allowed_explanations": [
            f"{observation}. A ocorrência requer conferência humana. {limit}",
            f"{observation}. É necessário conferir a fonte antes de agir. {limit}",
        ],
        "allowed_human_checks": [
            "Conferir os campos e as posições indicadas nas evidências.",
            "Confirmar o valor esperado na fonte antes de agir.",
            "Solicitar a referência necessária à conferência.",
        ]
        if group["category"] in {"reference", "unknown"}
        else [
            "Conferir os campos e as posições indicadas nas evidências.",
            "Conferir os registros relacionados na fonte.",
            "Confirmar o preenchimento com a pessoa responsável pela fonte.",
        ],
    }


def baseline(group: dict) -> dict:
    choices = language(group)
    return {
        "explanation": choices["allowed_explanations"][0],
        "human_checks": choices["allowed_human_checks"][:1],
    }


def validate_text(group: dict, output) -> None:
    try:
        checked = TextOutput.model_validate(output)
    except ValidationError as exc:
        raise ExplanationError("invalid_output_schema") from exc
    checks = checked.human_checks
    if len(set(checks)) != len(checks) or any(not 10 <= len(c) <= 150 for c in checks):
        raise ExplanationError("invalid_output_schema")
    choices = language(group)
    if checked.explanation not in choices["allowed_explanations"]:
        raise ExplanationError("unsupported_explanation")
    if any(c not in choices["allowed_human_checks"] for c in checks):
        raise ExplanationError("unsupported_human_check")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ExplanationError("duplicate_json_key")
        result[key] = value
    return result


def explain(group: dict, runtime=None, *, model="baseline") -> dict:
    group = copy.deepcopy(group)
    output = baseline(group)
    rejection = response_hash = None
    origin = "deterministic"
    started = time.perf_counter()
    try:
        if runtime is not None:
            prompt = (ASSETS / "prompt.txt").read_text(encoding="utf-8")
            raw, _ = runtime.generate(
                prompt
                + "\n"
                + json.dumps(
                    {
                        "facts": group,
                        **language(group),
                        "schema": json.loads(
                            (ASSETS / "output.schema.json").read_text(encoding="utf-8")
                        ),
                    },
                    ensure_ascii=False,
                ),
                model=model,
            )
            response_hash = hashlib.sha256(raw.encode()).hexdigest()
            if len(raw.encode()) > 4096:
                raise ExplanationError("output_too_large")
            candidate = json.loads(raw, object_pairs_hook=unique_object)
            validate_text(group, candidate)
            output = candidate
            origin = "model"
    except json.JSONDecodeError:
        rejection = "invalid_json"
    except TimeoutError:
        rejection = "runtime_timeout"
    except ExplanationError as exc:
        rejection = str(exc)
    except (RuntimeUnavailable, OSError):
        rejection = "runtime_unavailable"
    uncertain = (
        group["category"] == "unknown"
        or group["code"] in {"missing_reference_data", "read_error"}
        or any(o["unknown_value"]["state"] == "missing" for o in group["occurrences"])
    )
    return {
        "group": group,
        "text": output,
        "origin": origin,
        "state": "fallback_deterministic"
        if rejection
        else (
            "insufficient_evidence"
            if uncertain
            else (
                "accepted_explanation"
                if origin == "model"
                else "fallback_deterministic"
            )
        ),
        "rejection_code": rejection,
        "response_sha256": response_hash,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }
