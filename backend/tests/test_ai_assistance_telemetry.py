import json
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient
from test_ai_assistance_generator import Fake, context, valid
from test_ai_assistance_service import Contexts, Repository, make_actor

import app.ai_assistance_routes as routes
from app.ai_assistance_config import AiAssistanceConfig
from app.ai_assistance_generator import AiAssistanceGenerator
from app.ai_assistance_provider import ProviderError
from app.ai_assistance_service import AiAssistanceService
from app.ai_assistance_telemetry import (
    RESULTS,
    RequestObservation,
)
from app.authorization import get_actor_context
from app.errors import ApiError
from app.main import create_app
from app.observability.metrics import REGISTRY
from app.observability.telemetry import SafeJsonFormatter

pytest_plugins = ("test_ai_assistance_routes",)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)


def sample(name, **labels):
    return (
        REGISTRY.get_sample_value(
            "synergia_ai_assistance_" + name, {"environment": "test", **labels}
        )
        or 0
    )


def test_first_pin_incident_has_an_initialized_zero_baseline(monkeypatch):
    from prometheus_client import CollectorRegistry, Counter

    from app import ai_assistance_telemetry as telemetry

    registry = CollectorRegistry()
    generations = Counter(
        "synergia_ai_assistance_generations",
        "Isolated pin counter.",
        ("environment", "origin", "result", "code"),
        registry=registry,
    )
    monkeypatch.setattr(telemetry, "GENERATIONS", generations)
    labels = {
        "environment": "test",
        "origin": "deterministic",
        "result": "unavailable",
        "code": "runtime_pin_mismatch",
    }
    metric = "synergia_ai_assistance_generations_total"
    assert registry.get_sample_value(metric, labels) is None
    telemetry.initialize()
    assert registry.get_sample_value(metric, labels) == 0
    generations.labels(**labels).inc()
    telemetry.initialize()  # A second app creation must never reset the incident.
    assert registry.get_sample_value(metric, labels) == 1


def install(http, ctx, provider):
    service = AiAssistanceService(
        Contexts(ctx), AiAssistanceGenerator(provider), Repository()
    )
    http.app.dependency_overrides[routes.get_assistance_service] = lambda: service
    http.app.dependency_overrides[routes.get_read_service] = lambda: service
    http.app.dependency_overrides[get_actor_context] = lambda: make_actor(
        ctx, "ai.assistance.generate", "ai.assistance.read"
    )
    return service, f"/executions/{ctx.subject.execution_id}/ai-assistance"


@pytest.mark.parametrize("outcome", RESULTS)
def test_http_outcomes_are_exactly_once(client, outcome):
    http, _, _ = client
    ctx = (
        context("insufficient") if outcome in {"insufficient", "reused"} else context()
    )
    raw = (
        json.dumps(valid(ctx)).encode()
        if ctx.sufficiency != "insufficient"
        else b"never"
    )
    if outcome == "rejected":
        raw = b"private invalid model response"
    if outcome in {"unavailable", "timeout"}:
        raw = ProviderError(
            "runtime_timeout" if outcome == "timeout" else "runtime_unavailable"
        )
    provider = Fake(raw)
    _, path = install(http, ctx, provider)
    if outcome == "reused":
        assert http.post(path).status_code == 200
    before = {result: sample("requests_total", result=result) for result in RESULTS}
    reply = http.post(path)
    assert reply.status_code == {"unavailable": 503, "timeout": 504}.get(outcome, 200)
    assert {
        result: sample("requests_total", result=result) - value
        for result, value in before.items()
    } == {result: int(result == outcome) for result in RESULTS}
    assert sample("generations_in_progress") == 0
    assert provider.calls == (0 if outcome in {"insufficient", "reused"} else 1)


@pytest.mark.parametrize(
    "status,code",
    [
        (403, "access_denied"),
        (404, "ai_assistance_not_found"),
        (409, "ai_assistance_in_progress"),
        (429, "rate_limit_exceeded"),
    ],
)
def test_admission_denials_do_not_pollute_availability(
    client, monkeypatch, status, code
):
    http, ctx, _ = client
    service = http.app.dependency_overrides[routes.get_assistance_service]()

    def denied(*args):
        raise ApiError(status, code, "safe")

    monkeypatch.setattr(service, "generate", denied)
    before = sum(sample("requests_total", result=result) for result in RESULTS)
    old = sample("request_denials_total", code=code)
    assert (
        http.post(f"/executions/{ctx.subject.execution_id}/ai-assistance").status_code
        == status
    )
    assert sample("request_denials_total", code=code) == old + 1
    assert sum(sample("requests_total", result=result) for result in RESULTS) == before


def test_disabled_and_suspended_are_not_runtime_outages(client, monkeypatch):
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENABLED", "false")
    before = sample("requests_total", result="unavailable")
    with TestClient(create_app()) as http:
        assert (
            http.post(
                "/executions/00000000-0000-4000-8000-000000000001/ai-assistance"
            ).status_code
            == 503
        )
    http, ctx, _ = client
    http.app.dependency_overrides[routes.enabled_config] = lambda: AiAssistanceConfig(
        enabled=True, generation_enabled=False
    )
    assert (
        http.post(f"/executions/{ctx.subject.execution_id}/ai-assistance").status_code
        == 503
    )
    assert sample("requests_total", result="unavailable") == before


def test_http_timeout_keeps_worker_gauge_until_finish_without_second_outcome(
    client, monkeypatch
):
    http, _, _ = client
    ctx = context()
    entered, release, finished = Event(), Event(), Event()

    class Slow(Fake):
        def generate(self, *args):
            entered.set()
            assert release.wait(5)
            return super().generate(*args)

    provider = Slow(json.dumps(valid(ctx)).encode())
    service, path = install(http, ctx, provider)
    original = service.generate

    def work(*args):
        try:
            return original(*args)
        finally:
            finished.set()

    monkeypatch.setattr(service, "generate", work)
    monkeypatch.setattr(routes, "ASSISTANCE_TIMEOUT_SECONDS", 0.1)
    before_timeout = sample("requests_total", result="timeout")
    before_generated = sample("requests_total", result="generated")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(http.post, path)
        try:
            assert entered.wait(2)
            assert sample("generations_in_progress") == 1
            assert future.result(timeout=2).status_code == 504
            assert sample("generations_in_progress") == 1
        finally:
            release.set()
        assert finished.wait(2)
    assert sample("generations_in_progress") == 0
    assert sample("requests_total", result="timeout") == before_timeout + 1
    assert sample("requests_total", result="generated") == before_generated
    assert service.repository.result is not None
    assert http.post(path).status_code == 200
    assert provider.calls == 1


def test_observation_ignores_late_worker_and_repeated_finalization():
    observation = RequestObservation()
    old = sample("requests_total", result="timeout")
    observation.finish(504, 0.1)
    observation.mark("generated", "model", "ready")
    observation.finish(200, 0.2)
    assert sample("requests_total", result="timeout") == old + 1


def test_phase_metrics_cover_errors_and_skip_absent_inference(client):
    http, _, _ = client
    ctx = context("insufficient")
    _, path = install(http, ctx, Fake(b"never"))
    before = sample("inference_seconds_count")
    assert http.post(path).status_code == 200
    assert http.post(path).status_code == 200
    assert sample("inference_seconds_count") == before
    ctx = context()
    _, path = install(http, ctx, Fake(ProviderError("runtime_unavailable")))
    assert http.post(path).status_code == 503
    assert sample("inference_seconds_count") == before + 1


def test_labels_and_logs_exclude_raw_content_and_identifiers(client, caplog):
    http, _, _ = client
    marker = "PRIVATE_AI_191_MARKER"
    ctx = context()
    provider = Fake(marker.encode())
    provider.model = marker
    _, path = install(http, ctx, provider)
    logger = logging.getLogger("synergia.telemetry")
    logger.addHandler(caplog.handler)
    try:
        assert http.post(path).status_code == 200
    finally:
        logger.removeHandler(caplog.handler)
    records = [r for r in caplog.records if r.msg.startswith("ai.assistance.")]
    assert records
    rendered = "\n".join(SafeJsonFormatter().format(r) for r in records)
    assert marker not in rendered and str(ctx.subject.execution_id) not in rendered
    for record in records:
        payload = json.loads(SafeJsonFormatter().format(record))
        assert {
            "correlation_id",
            "state",
            "origin",
            "duration_ms",
            "error_code",
        } <= set(payload)
    for metric in REGISTRY.collect():
        if not metric.name.startswith("synergia_ai_assistance_"):
            continue
        for value in metric.samples:
            assert set(value.labels) <= {
                "environment",
                "result",
                "origin",
                "code",
                "le",
            }
            assert marker not in str(value.labels)
            assert str(ctx.subject.organization_id) not in str(value.labels)


def test_confirmed_scope_violation_is_distinct_from_missing_result(client):
    from app.authorization import get_authorization_repository

    http, ctx, _ = client
    service = http.app.dependency_overrides[routes.get_assistance_service]()

    class Audit:
        def execution_organization(self, _):
            return ctx.subject.organization_id

        def audit_denial(self, *args):
            pass

    http.app.dependency_overrides[get_authorization_repository] = Audit
    actor = make_actor(ctx, "ai.assistance.generate")
    from uuid import uuid4

    actor.permissions["ai.assistance.generate"] = frozenset({uuid4()})
    http.app.dependency_overrides[get_actor_context] = lambda: actor
    before = sample("security_rejections_total", code="scope_violation")
    assert (
        http.post(f"/executions/{ctx.subject.execution_id}/ai-assistance").status_code
        == 404
    )
    assert sample("security_rejections_total", code="scope_violation") == before + 1
    assert service.repository.result is None
    Audit.execution_organization = lambda self, _: None
    assert (
        http.post(f"/executions/{ctx.subject.execution_id}/ai-assistance").status_code
        == 404
    )
    assert sample("security_rejections_total", code="scope_violation") == before + 1


def test_context_failure_is_timed_without_recording_private_exception():
    from test_ai_assistance_context import Reader, build

    reader = Reader()

    def fail(*args):
        raise ValueError("PRIVATE_CONTEXT_FAILURE_191")

    reader.counts = fail
    before = sample("context_seconds_count")
    with pytest.raises(ApiError) as error:
        build(reader)
    assert error.value.code == "ai_context_invalid"
    assert sample("context_seconds_count") == before + 1


@pytest.mark.parametrize(
    "kind,code",
    [
        ("database", "database_unavailable"),
        ("configuration", "configuration_invalid"),
        ("internal", "internal_error"),
    ],
)
def test_persistence_error_codes_are_closed_and_distinguishable(kind, code, caplog):
    import psycopg

    from app.ai_assistance_telemetry import persistence

    error = {
        "database": psycopg.OperationalError,
        "configuration": ValueError,
        "internal": RuntimeError,
    }[kind]

    @persistence("finish")
    def fail():
        raise error("PRIVATE_EXCEPTION_191")

    logger = logging.getLogger("synergia.telemetry")
    logger.addHandler(caplog.handler)
    try:
        with pytest.raises(error):
            fail()
    finally:
        logger.removeHandler(caplog.handler)
    record = next(
        r for r in caplog.records if r.msg == "ai.assistance.persistence.finished"
    )
    rendered = SafeJsonFormatter().format(record)
    assert json.loads(rendered)["error_code"] == code
    assert "PRIVATE_EXCEPTION_191" not in rendered
