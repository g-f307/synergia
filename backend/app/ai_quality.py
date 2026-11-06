"""Authenticated synthetic scenarios and live, read-only local model generation."""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import threading
import time
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.ai_quality_core import (
    ASSETS,
    RuntimeUnavailable,
    TextOutput,
    baseline,
    explain,
)
from app.authorization import ActorContext, require_permission
from app.errors import ApiError
from app.model_audit import ModelAuditRepository, get_model_audit_repository

router = APIRouter(prefix="/ai/quality", tags=["ai-quality"])
MODEL = "qwen3:4b-instruct"
MODEL_DIGEST = "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
OPTIONS = {
    "num_ctx": 4096,
    "num_predict": 2048,
    "temperature": 0,
    "seed": 125,
    "num_thread": 6,
}
GENERATION_SECONDS = 30
MODEL_LOCK = threading.Lock()


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["model", "baseline"] = "model"


class Position(BaseModel):
    state: Literal["known", "not_provided"]
    value: str | int | None = None


class KnownValue(BaseModel):
    state: Literal["observed", "unavailable"]
    value: str | float | bool | None = None


class UnknownValue(BaseModel):
    state: Literal["missing", "not_exposed", "not_applicable"]


class Occurrence(BaseModel):
    evidence_id: str
    severity: Literal["error", "warning"]
    reason: str
    field: Position
    column: Position
    row: Position
    sheet: Position
    known_value: KnownValue
    unknown_value: UnknownValue


class FactGroup(BaseModel):
    code: str
    category: str
    causal_evidence: Literal["not_provided"]
    occurrences: list[Occurrence]


class QualityResult(BaseModel):
    group: FactGroup
    text: TextOutput
    origin: Literal["model", "deterministic"]
    state: Literal[
        "accepted_explanation", "fallback_deterministic", "insufficient_evidence"
    ]
    rejection_code: str | None = None
    response_sha256: str | None = None
    elapsed_ms: float


class Scenario(BaseModel):
    id: str
    groups: list[FactGroup]
    baseline: list[TextOutput]


class Catalog(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    model_status: Literal["disabled", "available", "unavailable"]
    scenarios: list[Scenario]


class ExplanationResponse(BaseModel):
    scenario_id: str
    mode: Literal["model", "baseline"]
    model: str
    groups: list[QualityResult]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, new_url):
        raise RuntimeUnavailable


class LocalRuntime:
    """No tools, arbitrary URLs, model downloads or user-provided prompts."""

    def __init__(self):
        self.endpoint = os.getenv(
            "SYNERGIA_AI_QUALITY_ENDPOINT", "http://127.0.0.1:11434"
        )
        try:
            parsed = urlsplit(self.endpoint)
            local = (
                parsed.hostname == "localhost"
                or ipaddress.ip_address(parsed.hostname or "").is_loopback
            )
            valid_port = parsed.port is not None
        except ValueError:
            raise RuntimeUnavailable from None
        if (
            parsed.scheme != "http"
            or not local
            or not valid_port
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise RuntimeUnavailable
        self.endpoint = self.endpoint.rstrip("/")
        self.deadline = time.monotonic() + GENERATION_SECONDS
        self.pinned = False

    def request(self, route, payload=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        request = urllib.request.Request(
            self.endpoint + "/api/" + route,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"},
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        )
        try:
            with opener.open(
                request, timeout=min(remaining, 3 if payload is None else remaining)
            ) as response:
                # Bound response allocation even if the local runtime misbehaves.
                raw = response.read(64 * 1024 + 1)
                if len(raw) > 64 * 1024:
                    raise RuntimeUnavailable
                return json.loads(raw)
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError from exc
            raise RuntimeUnavailable from exc
        except (ValueError, UnicodeError) as exc:
            raise RuntimeUnavailable from exc

    def verify_pin(self):
        if not self.pinned:
            version = self.request("version")
            models = self.request("tags")
            listed = models.get("models") if isinstance(models, dict) else None
            if (
                not isinstance(version, dict)
                or version.get("version") != "0.40.12"
                or not isinstance(listed, list)
                or not any(
                    isinstance(m, dict)
                    and m.get("name") == MODEL
                    and m.get("digest") == MODEL_DIGEST
                    for m in listed
                )
            ):
                raise RuntimeUnavailable
            self.pinned = True

    def generate(self, prompt, *, model):
        self.verify_pin()
        result = self.request(
            "generate",
            {
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "keep_alive": 600,
                "options": OPTIONS,
                "format": json.loads(
                    (ASSETS / "output.schema.json").read_text(encoding="utf-8")
                ),
            },
        )
        if not isinstance(result, dict) or not isinstance(result.get("response"), str):
            raise RuntimeUnavailable
        return result["response"], 0


class UnavailableRuntime:
    def generate(self, prompt, *, model):
        raise RuntimeUnavailable


class QualityService:
    def __init__(self, runtime_factory=LocalRuntime):
        self.runtime_factory = runtime_factory
        self.lock = MODEL_LOCK
        self.scenarios = json.loads(
            (ASSETS / "scenarios.json").read_text(encoding="utf-8")
        )

    def catalog(self):
        status = "disabled"
        if self.model_enabled():
            try:
                self.runtime_factory().verify_pin()
                status = "available"
            except (RuntimeUnavailable, OSError, TimeoutError):
                status = "unavailable"
        return Catalog(
            model_status=status,
            scenarios=[
                Scenario(
                    id=s["id"],
                    groups=copy.deepcopy(s["groups"]),
                    baseline=[baseline(g) for g in s["groups"]],
                )
                for s in self.scenarios
            ],
        )

    @staticmethod
    def model_enabled():
        return os.getenv("SYNERGIA_AI_QUALITY_MODEL_ENABLED", "false").lower() == "true"

    def generate(self, scenario_id: str, mode: str):
        scenario = next((s for s in self.scenarios if s["id"] == scenario_id), None)
        if scenario is None:
            raise ApiError(404, "ai_scenario_not_found", "Cenário não encontrado")
        if mode == "model" and not self.model_enabled():
            raise ApiError(
                503, "ai_quality_disabled", "Geração por modelo desabilitada"
            )
        acquired = mode == "model" and self.lock.acquire(blocking=False)
        try:
            runtime = None
            if mode == "model":
                try:
                    runtime = (
                        self.runtime_factory() if acquired else UnavailableRuntime()
                    )
                except RuntimeUnavailable:
                    runtime = UnavailableRuntime()
            groups = [
                explain(group, runtime, model=MODEL) for group in scenario["groups"]
            ]
            if mode == "model" and not acquired:
                for item in groups:
                    item["rejection_code"] = "runtime_busy"
            return ExplanationResponse(
                scenario_id=scenario_id, mode=mode, model=MODEL, groups=groups
            )
        finally:
            if acquired:
                self.lock.release()


@lru_cache(maxsize=1)
def get_quality_service():
    return QualityService()


@router.get("/scenarios", response_model=Catalog, response_model_exclude_none=True)
def catalog(
    actor: Annotated[ActorContext, Depends(require_permission("execution.read"))],
    service: Annotated[QualityService, Depends(get_quality_service)],
):
    return service.catalog()


@router.post(
    "/scenarios/{scenario_id}/explanations",
    response_model=ExplanationResponse,
    response_model_exclude_none=True,
)
def generate(
    scenario_id: str,
    payload: GenerateRequest,
    actor: Annotated[ActorContext, Depends(require_permission("execution.read"))],
    service: Annotated[QualityService, Depends(get_quality_service)],
    audit: Annotated[ModelAuditRepository, Depends(get_model_audit_repository)],
):
    if payload.mode != "model":
        return service.generate(scenario_id, payload.mode)
    operation_id = uuid4()
    audit.record(actor, operation_id, "llm.requested")
    started = time.monotonic()
    try:
        result = service.generate(scenario_id, payload.mode)
    except Exception:
        audit.record(
            actor,
            operation_id,
            "llm.failed",
            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
        )
        raise
    audit.record(
        actor,
        operation_id,
        "llm.completed",
        duration_ms=max(0, round((time.monotonic() - started) * 1000)),
        fallback=any(group.rejection_code is not None for group in result.groups),
    )
    return result
