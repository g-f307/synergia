import asyncio
import time
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_ai_assistance_generator import Fake, context
from test_ai_assistance_service import Contexts, Repository, make_actor

import app.ai_assistance_routes as routes
from app.ai_assistance_config import AiAssistanceConfig
from app.ai_assistance_generator import AiAssistanceGenerator
from app.ai_assistance_routes import (
    enabled_config,
    get_assistance_service,
    get_read_service,
)
from app.ai_assistance_service import AiAssistanceService
from app.authorization import get_actor_context, get_authorization_repository
from app.main import create_app


@pytest.fixture
def client():
    ctx = context("insufficient")
    provider = Fake(b"never")
    service = AiAssistanceService(
        Contexts(ctx), AiAssistanceGenerator(provider), Repository()
    )
    app = create_app()
    app.dependency_overrides[enabled_config] = lambda: AiAssistanceConfig(enabled=True)
    app.dependency_overrides[get_actor_context] = lambda: make_actor(
        ctx, "ai.assistance.generate", "ai.assistance.read"
    )
    app.dependency_overrides[get_assistance_service] = lambda: service
    app.dependency_overrides[get_read_service] = lambda: service
    app.dependency_overrides[get_authorization_repository] = lambda: type(
        "Audit", (), {"audit_denial": lambda *args: None}
    )()
    with TestClient(app) as value:
        yield value, ctx, provider


def test_post_and_get_without_inference(client):
    http, ctx, provider = client
    path = f"/executions/{ctx.subject.execution_id}/ai-assistance"
    assert http.get(path + "/latest").status_code == 404
    post = http.post(path)
    assert post.status_code == 200
    assert post.json()["state"] == "insufficient_evidence"
    assert http.post(path, json={}).json() == post.json()
    assert http.get(path + "/latest").json() == post.json()
    assert provider.calls == 0
    assert post.headers["x-correlation-id"]
    assert post.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("body", [b"null", b"[]", b'{"model":"x"}', b"{"])
def test_rejects_nonempty_and_invalid_body(client, body):
    http, ctx, _ = client
    path = f"/executions/{ctx.subject.execution_id}/ai-assistance"
    response = http.post(
        path, content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ai_assistance_invalid_contract"
    assert "model" not in response.text


@pytest.mark.security
def test_oversized_empty_json_is_rejected_without_generation(client):
    http, ctx, provider = client
    path = f"/executions/{ctx.subject.execution_id}/ai-assistance"
    response = http.post(path, content=b" " * 1024 + b"{}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ai_assistance_invalid_contract"
    assert provider.calls == 0


@pytest.mark.security
def test_request_stream_stops_at_limit_and_has_a_deadline(monkeypatch):
    from app.errors import ApiError

    class Oversized:
        async def stream(self):
            yield b" " * 1024
            yield b"{}"
            pytest.fail("oversized remainder must not be consumed")

    class Slow:
        async def stream(self):
            yield b"{"
            await asyncio.sleep(5)
            pytest.fail("slow body must be cancelled")
            yield b"}"

    for request in (Oversized(), Slow()):
        monkeypatch.setattr(routes, "BODY_TIMEOUT_SECONDS", 0.01)
        with pytest.raises(ApiError) as exc:
            asyncio.run(routes.empty_body(request))
        assert exc.value.status_code == 422
        assert exc.value.code == "ai_assistance_invalid_contract"


def test_disabled_before_authentication(monkeypatch):
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENABLED", "false")
    with TestClient(create_app()) as http:
        response = http.post(f"/executions/{uuid4()}/ai-assistance")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_assistance_disabled"


def test_timeout_returns_stable_error(client, monkeypatch):
    http, ctx, _ = client
    app = http.app
    service = app.dependency_overrides[get_assistance_service]()
    monkeypatch.setattr(service, "generate", lambda *_: time.sleep(0.2))
    monkeypatch.setattr(routes, "ASSISTANCE_TIMEOUT_SECONDS", 0.01)
    response = http.post(f"/executions/{ctx.subject.execution_id}/ai-assistance")
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "ai_assistance_timeout"


def test_internal_error_is_sanitized(client, monkeypatch):
    http, ctx, _ = client
    service = http.app.dependency_overrides[get_assistance_service]()

    def fail(*_):
        raise RuntimeError("secret runtime endpoint")

    monkeypatch.setattr(service, "generate", fail)
    response = http.post(f"/executions/{ctx.subject.execution_id}/ai-assistance")
    assert response.status_code == 503
    assert "secret" not in response.text


def test_missing_permission_and_other_organization(client):
    http, ctx, _ = client
    path = f"/executions/{ctx.subject.execution_id}/ai-assistance"
    http.app.dependency_overrides[get_actor_context] = lambda: make_actor(ctx)
    response = http.post(path)
    assert response.status_code == 403
    actor = make_actor(ctx, "ai.assistance.generate")
    actor.permissions["ai.assistance.generate"] = frozenset({uuid4()})
    http.app.dependency_overrides[get_actor_context] = lambda: actor
    response = http.post(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ai_assistance_not_found"


def test_client_cancellation_does_not_interrupt_worker(client, monkeypatch):
    http, ctx, _ = client
    service = http.app.dependency_overrides[get_assistance_service]()
    entered, release, finished = Event(), Event(), Event()

    def work(*_):
        entered.set()
        try:
            assert release.wait(3)
        finally:
            finished.set()

    monkeypatch.setattr(service, "generate", work)

    async def scenario():
        task = asyncio.create_task(
            routes.generate_assistance(
                execution_id=ctx.subject.execution_id,
                request=None,
                config=AiAssistanceConfig(enabled=True),
                actor=make_actor(ctx, "ai.assistance.generate"),
                audit=None,
                service=service,
                body=None,
            )
        )
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        assert await asyncio.to_thread(finished.wait, 2)

    asyncio.run(scenario())


def test_rejected_output_fallback_over_http(client):
    http, _, _ = client
    ctx = context()
    provider = Fake(b'{"private_raw":"secret"}')
    service = AiAssistanceService(
        Contexts(ctx), AiAssistanceGenerator(provider), Repository()
    )
    http.app.dependency_overrides[get_actor_context] = lambda: make_actor(
        ctx, "ai.assistance.generate"
    )
    http.app.dependency_overrides[get_assistance_service] = lambda: service
    http.app.dependency_overrides[get_read_service] = lambda: service
    response = http.post(f"/executions/{ctx.subject.execution_id}/ai-assistance")
    assert response.status_code == 200 and response.json()["state"] == "rejected"
    assert "private_raw" not in response.text and provider.calls == 1


def test_provider_unavailable_over_http(client):
    from app.ai_assistance_provider import ProviderError

    http, _, _ = client
    ctx = context()
    provider = Fake(ProviderError("runtime_unavailable"))
    service = AiAssistanceService(
        Contexts(ctx), AiAssistanceGenerator(provider), Repository()
    )
    http.app.dependency_overrides[get_actor_context] = lambda: make_actor(
        ctx, "ai.assistance.generate"
    )
    http.app.dependency_overrides[get_assistance_service] = lambda: service
    http.app.dependency_overrides[get_read_service] = lambda: service
    response = http.post(f"/executions/{ctx.subject.execution_id}/ai-assistance")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_assistance_runtime_unavailable"
    assert provider.calls == 1


@pytest.mark.parametrize(
    "status,code",
    [
        (409, "ai_assistance_in_progress"),
        (429, "rate_limit_exceeded"),
        (500, "ai_assistance_integrity_error"),
        (503, "ai_assistance_runtime_unavailable"),
    ],
)
def test_failure_codes_through_http(client, monkeypatch, status, code):
    from app.errors import ApiError

    http, ctx, _ = client
    service = http.app.dependency_overrides[get_assistance_service]()

    def fail(*args):
        raise ApiError(
            status,
            code,
            "Falha segura",
            headers={"Retry-After": "30"} if status == 429 else None,
        )

    monkeypatch.setattr(service, "generate", fail)
    response = http.post(f"/executions/{ctx.subject.execution_id}/ai-assistance")
    assert response.status_code == status and response.json()["error"]["code"] == code
    if status == 429:
        assert response.headers["retry-after"] == "30"


def test_latest_denials_are_audited(client):
    http, ctx, provider = client
    denials = []
    http.app.dependency_overrides[get_authorization_repository] = lambda: type(
        "Audit", (), {"audit_denial": lambda self, *args: denials.append(args)}
    )()
    path = f"/executions/{ctx.subject.execution_id}/ai-assistance/latest"
    http.app.dependency_overrides[get_actor_context] = lambda: make_actor(ctx)
    assert http.get(path).status_code == 403
    actor = make_actor(ctx, "ai.assistance.read")
    actor.permissions["ai.assistance.read"] = frozenset({uuid4()})
    http.app.dependency_overrides[get_actor_context] = lambda: actor
    assert http.get(path).status_code == 404
    assert len(denials) == 2 and provider.calls == 0


def test_get_disabled(monkeypatch):
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENABLED", "false")
    with TestClient(create_app()) as http:
        response = http.get(f"/executions/{uuid4()}/ai-assistance/latest")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_assistance_disabled"


def test_generation_kill_switch_keeps_existing_result(client):
    http, ctx, provider = client
    path = f"/executions/{ctx.subject.execution_id}/ai-assistance"
    original = http.post(path).json()
    http.app.dependency_overrides[enabled_config] = lambda: AiAssistanceConfig(
        enabled=True, generation_enabled=False
    )
    denied = http.post(path)
    assert denied.status_code == 503
    assert denied.json()["error"]["code"] == "ai_assistance_generation_disabled"
    assert http.get(path + "/latest").json() == original
    assert provider.calls == 0


def test_read_service_does_not_construct_runtime_or_limiter(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("reading must not initialize provider or generation limits")

    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/test")
    monkeypatch.setattr(routes, "LocalAiModelProvider", forbidden)
    monkeypatch.setattr(routes, "AssistanceLimits", forbidden)
    service = routes.get_read_service(AiAssistanceConfig(enabled=True))
    assert service.generator is None and service.limits is None
    from app.errors import ApiError

    with pytest.raises(ApiError) as error:
        service.generate(None, uuid4())
    assert error.value.code == "ai_assistance_generation_disabled"


def test_structured_logs_include_correlation_without_raw_error(
    client, monkeypatch, caplog
):
    import logging

    from app.observability.telemetry import SafeJsonFormatter

    http, ctx, _ = client
    service = http.app.dependency_overrides[get_assistance_service]()
    logger = logging.getLogger("synergia.telemetry")
    logger.addHandler(caplog.handler)
    correlation = str(uuid4())
    try:
        success = http.post(
            f"/executions/{ctx.subject.execution_id}/ai-assistance",
            headers={"X-Correlation-ID": correlation},
        )
        assert success.status_code == 200

        ctx = context()
        service = AiAssistanceService(
            Contexts(ctx),
            AiAssistanceGenerator(
                Fake(RuntimeError("secret endpoint http://private.invalid/raw"))
            ),
            Repository(),
        )
        http.app.dependency_overrides[get_actor_context] = lambda: make_actor(
            ctx, "ai.assistance.generate"
        )
        http.app.dependency_overrides[get_assistance_service] = lambda: service
        http.app.dependency_overrides[get_read_service] = lambda: service
        response = http.post(
            f"/executions/{ctx.subject.execution_id}/ai-assistance",
            headers={"X-Correlation-ID": correlation},
        )
    finally:
        logger.removeHandler(caplog.handler)
    assert response.status_code == 503
    records = [
        r
        for r in caplog.records
        if r.msg
        in (
            "http.request.failed",
            "http.request.completed",
            "ai.assistance.unexpected_error",
        )
    ]
    assert records
    assert {r.synergia_fields.get("status_code") for r in records} >= {200, 503}
    rendered = "\n".join(SafeJsonFormatter().format(r) for r in records)
    assert correlation in rendered
    assert any(
        r.msg == "ai.assistance.unexpected_error"
        and r.synergia_fields.get("correlation_id") == correlation
        for r in records
    )
    assert "secret" not in rendered and "private.invalid" not in rendered
    assert "stack_trace" not in rendered
