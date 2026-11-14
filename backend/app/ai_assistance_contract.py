"""Operational assistance 1.0.0: shared trust boundary, independent of inference."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from fastapi import FastAPI
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    model_validator,
)

CONTRACT_VERSION = "1.0.0"
PRODUCT_NOTICE = (
    "Assistência gerada por IA: pode conter erros. "
    "A conferência humana das evidências é necessária."
)
HTTP_STATES = {
    "200": "Resultado concluído, inclusive insufficient_evidence",
    "403": "Falta de permissão",
    "404": "Execução inexistente ou invisível na organização",
    "409": "Execução ativa ou geração em andamento",
    "422": "Contrato inválido",
    "503": "Recurso desabilitado ou runtime indisponível antes do início",
    "504": "Timeout após início da geração",
}


def serialize_context(context: dict) -> bytes:
    serialized = json.dumps(
        context,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(serialized) > 8192:
        raise ValueError("serialized assistance context exceeds 8192 bytes")
    return serialized


def validate_raw_response(raw: bytes) -> bytes:
    if len(raw) > 8192:
        raise ValueError("raw assistance response exceeds 8192 bytes")
    raw.decode("utf-8", errors="strict")
    return raw


def plain_text(value: str) -> str:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    )
    # Plain declarative text only. This is a lexical guard, not semantic proof;
    # generation must additionally validate grounding before publishing (#187).
    if (
        not value.strip()
        or any(unicodedata.category(char).startswith("C") for char in value)
        or re.search(r"[<>`\[\]{}]|://|www\.|javascript:|data:|!\[", normalized)
        or re.search(
            r"\b(execute|executar|rode|rodar|run|delete|apague|exclua|altere|"
            r"modifique|envie|acesse|clique|reprocesse|ignore|sudo|curl|"
            r"reinicie|reiniciar|aprove|rejeite|cancele|edite|substitua|"
            r"salve|publique|habilite|desabilite|apagar|excluir|alterar|"
            r"executando|reprocessar|aprovar|rejeitar|cancelar|remover|"
            r"approve|reject|update|insert|remove|click|send|upload|download|"
            r"restart|reboot|edit|replace|save|enable|disable|rm|chmod|bash|sh)\b",
            normalized,
        )
    ):
        raise ValueError("only non-actionable declarative plain text is allowed")
    return value


Text = Annotated[str, Field(min_length=1, max_length=600), AfterValidator(plain_text)]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
EvidenceRef = Annotated[
    str, Field(pattern=r"^(DIV|PEN|CLA|EVI|HIS)-[A-Za-z0-9_-]{1,64}$")
]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class AiAssistanceRequest(StrictContract):
    """An absent body or {}. Never accepts prompts, facts or model settings."""


class AiAssistanceFinding(StrictContract):
    title: Annotated[Text, Field(max_length=120)]
    explanation: Text
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def grounded(self, info: ValidationInfo) -> AiAssistanceFinding:
        allowed = (info.context or {}).get("evidence_refs", frozenset())
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("duplicate evidence reference")
        if not set(self.evidence_refs) <= set(allowed):
            raise ValueError("evidence references must exist in the authorized context")
        return self


class AiAssistanceTimings(StrictContract):
    context_ms: int = Field(ge=0, le=30000)
    generation_ms: int = Field(ge=0, le=30000)
    total_ms: int = Field(ge=0, le=30000)

    @model_validator(mode="after")
    def coherent(self) -> AiAssistanceTimings:
        if self.context_ms + self.generation_ms > self.total_ms:
            raise ValueError("total time must include context and generation")
        return self


class AiAssistanceProvenance(StrictContract):
    contract_version: Literal["1.0.0"]
    model: str | None = Field(max_length=128)
    digest: str | None = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    context_hash: Sha256
    prompt_hash: Sha256
    origin: Literal["model", "deterministic"]
    timings: AiAssistanceTimings

    @model_validator(mode="after")
    def coherent(self) -> AiAssistanceProvenance:
        if self.origin == "model" and (not self.model or not self.digest):
            raise ValueError("model origin requires model and digest")
        if self.model is not None and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", self.model
        ):
            raise ValueError("invalid model identifier")
        if bool(self.model) != bool(self.digest):
            raise ValueError("model and digest must be present together")
        return self


class AiAssistanceResponse(StrictContract):
    assistance_id: UUID
    execution_id: UUID
    state: Literal["ready", "insufficient_evidence", "unavailable", "rejected"]
    summary: Text
    findings: list[AiAssistanceFinding] = Field(max_length=5)
    human_checks: list[Text] = Field(max_length=3)
    limitations: list[Text] = Field(max_length=5)
    provenance: AiAssistanceProvenance
    created_at: AwareDatetime

    @model_validator(mode="after")
    def coherent(self) -> AiAssistanceResponse:
        if self.state != "ready":
            if self.findings or not self.limitations:
                raise ValueError("non-ready states require limitations and no findings")
            if self.provenance.origin != "deterministic":
                raise ValueError("non-ready states must use deterministic fallback")
        return self


def contract_examples() -> dict:
    summaries = {
        "ready": "Os fatos autorizados estão disponíveis para conferência humana.",
        "insufficient_evidence": "As evidências disponíveis são insuficientes.",
        "unavailable": "A assistência está indisponível.",
        "rejected": "A resposta gerada foi recusada pela validação.",
    }
    return {
        state: {
            "assistance_id": "00000000-0000-4000-8000-000000000001",
            "execution_id": "00000000-0000-4000-8000-000000000002",
            "state": state,
            "summary": summary,
            "findings": [],
            "human_checks": ["A conferência humana das evidências é necessária."],
            "limitations": [PRODUCT_NOTICE],
            "provenance": {
                "contract_version": CONTRACT_VERSION,
                "model": None,
                "digest": None,
                "context_hash": "0" * 64,
                "prompt_hash": "0" * 64,
                "origin": "deterministic",
                "timings": {"context_ms": 0, "generation_ms": 0, "total_ms": 0},
            },
            "created_at": "2026-11-14T00:00:00Z",
        }
        for state, summary in summaries.items()
    }


def install_contract_openapi(application: FastAPI) -> None:
    """Publish the shared contract without advertising unimplemented routes (#189)."""
    original = application.openapi

    def openapi() -> dict:
        schema = original()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in (AiAssistanceRequest, AiAssistanceResponse):
            model_schema = model.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )
            components.update(model_schema.pop("$defs", {}))
            components[model.__name__] = model_schema
        components["AiAssistanceResponse"]["examples"] = list(
            contract_examples().values()
        )
        schema["x-ai-assistance"] = {
            "contract_version": CONTRACT_VERSION,
            "request": {"$ref": "#/components/schemas/AiAssistanceRequest"},
            "response": {"$ref": "#/components/schemas/AiAssistanceResponse"},
            "examples": contract_examples(),
            "http_states": HTTP_STATES,
            "notice": PRODUCT_NOTICE,
        }
        return schema

    application.openapi = openapi
