"""Closed, content-free assistance instrumentation. HTTP and worker lifetimes differ."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from threading import Lock

import psycopg
from prometheus_client import Counter, Gauge, Histogram

from app.ai_assistance_metrics import environment
from app.observability.metrics import REGISTRY
from app.observability.telemetry import safe_log

RESULTS = ("generated", "reused", "insufficient", "rejected", "unavailable", "timeout")
REJECTIONS = frozenset(
    {
        "runtime_busy",
        "runtime_timeout",
        "runtime_unavailable",
        "runtime_pin_mismatch",
        "runtime_redirect",
        "runtime_response_too_large",
        "runtime_invalid_response",
        "response_too_large",
        "invalid_json",
        "invalid_schema",
        "invalid_reference",
        "ungrounded_summary",
        "ungrounded_finding",
        "ungrounded_checks",
        "ungrounded_limitations",
        "missing_limitations",
    }
)
ERROR_CODES = REJECTIONS | {
    "none",
    "internal_error",
    "integrity_error",
    "scope_violation",
    "access_denied",
    "ai_context_invalid",
    "ai_context_unavailable",
    "request_validation_error",
    "ai_assistance_disabled",
    "ai_assistance_generation_disabled",
    "ai_assistance_not_found",
    "ai_assistance_execution_not_terminal",
    "ai_assistance_in_progress",
    "ai_assistance_runtime_unavailable",
    "ai_assistance_timeout",
    "ai_assistance_integrity_error",
    "rate_limit_exceeded",
    "unauthenticated",
    "invalid_access_token",
    "invalid_request",
    "cancelled",
    "maintenance_failed",
    "configuration_invalid",
    "database_unavailable",
    "actor_not_found",
    "conflict_or_not_found",
    "reservation_missing",
}
LABELS = ("environment",)
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30)
SIZE_BUCKETS = (512, 1024, 2048, 4096, 6144, 8192)


def closed_code(value) -> str:
    return (
        value if isinstance(value, str) and value in ERROR_CODES else "internal_error"
    )


def initialize():
    env = environment()
    for result in RESULTS:
        REQUESTS.labels(env, result)
    for code in ("integrity_error", "scope_violation"):
        SECURITY.labels(env, code)
    # A zero baseline lets Prometheus observe the first pin mismatch as a rise.
    GENERATIONS.labels(env, "deterministic", "unavailable", "runtime_pin_mismatch")
    INFLIGHT.labels(env)


def record_security(code):
    if code not in {"integrity_error", "scope_violation"}:
        raise ValueError("invalid security signal")
    SECURITY.labels(environment(), code).inc()
    log_event("ai.assistance.security.rejected", result="rejected", code=code)


REQUESTS = Counter(
    "synergia_ai_assistance_requests",
    "POST outcomes, exactly once per HTTP request; excludes admission denials.",
    (*LABELS, "result"),
    registry=REGISTRY,
)
DENIALS = Counter(
    "synergia_ai_assistance_request_denials",
    "Admission denials excluded from the inference availability ratio.",
    (*LABELS, "code"),
    registry=REGISTRY,
)
ORIGINS = Counter(
    "synergia_ai_assistance_response_origins",
    "Origins actually delivered by successful POSTs.",
    (*LABELS, "origin"),
    registry=REGISTRY,
)
SECURITY = Counter(
    "synergia_ai_assistance_security_rejections",
    "Detected integrity or confirmed scope violations.",
    (*LABELS, "code"),
    registry=REGISTRY,
)
CONTEXTS = Counter(
    "synergia_ai_assistance_contexts",
    "Successfully assembled snapshots.",
    (*LABELS, "result"),
    registry=REGISTRY,
)
CONTEXT_BYTES = Histogram(
    "synergia_ai_assistance_context_bytes",
    "Serialized canonical snapshot size.",
    LABELS,
    buckets=SIZE_BUCKETS,
    registry=REGISTRY,
)
TRUNCATIONS = Counter(
    "synergia_ai_assistance_context_truncations",
    "Truncated collections by closed code.",
    (*LABELS, "code"),
    registry=REGISTRY,
)
CONTEXT_DURATION = Histogram(
    "synergia_ai_assistance_context_seconds",
    "Context assembly duration, including failures and reads.",
    LABELS,
    buckets=BUCKETS,
    registry=REGISTRY,
)
GENERATIONS = Counter(
    "synergia_ai_assistance_generations",
    "Generator outcomes, separate from HTTP delivery.",
    (*LABELS, "origin", "result", "code"),
    registry=REGISTRY,
)
GENERATION_DURATION = Histogram(
    "synergia_ai_assistance_generation_seconds",
    "Generator duration including validation/fallback.",
    LABELS,
    buckets=BUCKETS,
    registry=REGISTRY,
)
INFERENCE_DURATION = Histogram(
    "synergia_ai_assistance_inference_seconds",
    "Provider duration, including pin/errors; no samples for reuse/insufficiency.",
    LABELS,
    buckets=BUCKETS,
    registry=REGISTRY,
)
RESPONSE_BYTES = Histogram(
    "synergia_ai_assistance_response_bytes",
    "Model content bytes before JSON validation; absent content has no sample.",
    LABELS,
    buckets=SIZE_BUCKETS,
    registry=REGISTRY,
)
TOTAL_DURATION = Histogram(
    "synergia_ai_assistance_total_seconds",
    "POST HTTP duration, including errors and timeouts.",
    LABELS,
    buckets=BUCKETS,
    registry=REGISTRY,
)
INFLIGHT = Gauge(
    "synergia_ai_assistance_generations_in_progress",
    "Provider calls still executing, including work after cancellation/timeout.",
    LABELS,
    registry=REGISTRY,
)
PERSISTENCE = Counter(
    "synergia_ai_assistance_persistence",
    "Repository operations after transaction outcome.",
    (*LABELS, "result", "code"),
    registry=REGISTRY,
)
_observation: ContextVar[RequestObservation | None] = ContextVar(
    "ai_assistance_observation", default=None
)


def log_event(
    event,
    *,
    result,
    code="none",
    state="none",
    origin="none",
    duration=0,
    correlation_id=None,
):
    fields = dict(
        component="ai_assistance",
        outcome=result
        if result in {*RESULTS, "success", "failure", "denied", "preview"}
        else "failure",
        error_code=closed_code(code),
        state=state
        if state
        in {
            "none",
            "ready",
            "processing",
            "insufficient_evidence",
            "rejected",
            "unavailable",
        }
        else "none",
        origin=origin if origin in {"none", "model", "deterministic"} else "none",
        duration_ms=round(max(duration, 0) * 1000, 3),
    )
    if correlation_id is not None:
        from uuid import UUID

        fields["correlation_id"] = str(UUID(str(correlation_id)))
    safe_log(
        logging.WARNING
        if result in {"failure", "denied", "unavailable", "timeout", "rejected"}
        else logging.INFO,
        event,
        **fields,
    )


class RequestObservation:
    """Shared by copied thread contexts; a late worker cannot finalize HTTP twice."""

    def __init__(self):
        self.lock = Lock()
        self.finished = False
        self.result = None
        self.origin = "none"
        self.state = "none"
        self.code = "none"

    def mark(self, result, origin="deterministic", state="none", code="none"):
        with self.lock:
            if not self.finished:
                self.result, self.origin, self.state, self.code = (
                    result,
                    origin,
                    state,
                    closed_code(code),
                )

    def fail(self, code):
        with self.lock:
            if not self.finished:
                self.code = closed_code(code)

    def finish(self, status, elapsed):
        with self.lock:
            if self.finished:
                return
            self.finished = True
            code, result, origin, state = (
                self.code,
                self.result,
                self.origin,
                self.state,
            )
        env = environment()
        TOTAL_DURATION.labels(env).observe(max(elapsed, 0))
        if status == 200 and result in RESULTS:
            ORIGINS.labels(
                env, origin if origin in {"model", "deterministic"} else "deterministic"
            ).inc()
        elif status == 504:
            result, code = "timeout", "ai_assistance_timeout"
        elif status >= 500 and code not in {
            "ai_assistance_disabled",
            "ai_assistance_generation_disabled",
        }:
            result = "unavailable"
        else:
            DENIALS.labels(
                env, closed_code(code if code != "none" else "invalid_request")
            ).inc()
            log_event(
                "ai.assistance.request.finished",
                result="denied",
                code=code,
                duration=elapsed,
            )
            return
        REQUESTS.labels(env, result).inc()
        if code == "ai_assistance_integrity_error":
            record_security("integrity_error")
        log_event(
            "ai.assistance.request.finished",
            result=result,
            state=state,
            origin=origin,
            code=code,
            duration=elapsed,
        )


def mark_result(response, *, reused=False, code="none"):
    result = (
        "reused"
        if reused
        else {
            "ready": "generated",
            "insufficient_evidence": "insufficient",
            "rejected": "rejected",
        }.get(response.state, "unavailable")
    )
    observation = _observation.get()
    if observation is not None:
        observation.mark(
            result, response.provenance.origin, response.state, code or "none"
        )


def mark_error(code):
    observation = _observation.get()
    if observation is not None:
        observation.fail(code)


@contextmanager
def inference():
    started = time.monotonic()
    env = environment()
    INFLIGHT.labels(env).inc()
    try:
        yield
    finally:
        INFERENCE_DURATION.labels(env).observe(max(time.monotonic() - started, 0))
        INFLIGHT.labels(env).dec()


def context_timing(operation):
    @wraps(operation)
    def call(*args, **kwargs):
        started = time.monotonic()
        result, code = "success", "none"
        try:
            return operation(*args, **kwargs)
        except Exception as exc:
            result, code = (
                "failure",
                closed_code(getattr(exc, "code", "internal_error")),
            )
            raise
        finally:
            elapsed = time.monotonic() - started
            CONTEXT_DURATION.labels(environment()).observe(max(elapsed, 0))
            log_event(
                "ai.assistance.context.finished",
                result=result,
                code=code,
                duration=elapsed,
            )

    return call


def persistence(operation):
    allowed = {
        "reserve",
        "abandon",
        "finish",
        "find",
        "get",
        "latest",
        "expire",
        "recover_reservations",
    }
    if operation not in allowed:
        raise ValueError("unknown persistence operation")

    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            result, code = "success", "none"
            started = time.monotonic()
            try:
                return function(*args, **kwargs)
            except Exception as exc:
                result = "failure"
                if type(exc).__name__ == "AssistancePersistenceError" and str(exc) in {
                    "integrity_error",
                    "conflict_or_not_found",
                    "actor_not_found",
                    "reservation_missing",
                }:
                    code = str(exc)
                elif isinstance(exc, psycopg.Error | OSError):
                    code = "database_unavailable"
                elif isinstance(exc, ValueError | TypeError):
                    code = "configuration_invalid"
                else:
                    code = "internal_error"
                raise
            finally:
                # A closed operation+outcome code replaces free operation labels.
                PERSISTENCE.labels(
                    environment(), result, operation + "_" + result
                ).inc()
                log_event(
                    "ai.assistance.persistence.finished",
                    result=result,
                    code=code,
                    duration=time.monotonic() - started,
                )

        return call

    return decorate
