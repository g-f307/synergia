"""Integrated synthetic-only AI surface: auth, live generation and fallback."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app import ai_quality as api
from app.ai_quality_core import RuntimeUnavailable, baseline
from app.authorization import get_actor_context
from app.main import app


class Runtime:
    def __init__(self, error=None, raw=None):
        self.error, self.raw, self.calls = error, raw, []

    def generate(self, prompt, *, model):
        self.calls.append((prompt, model))
        if self.error:
            raise self.error
        group = json.loads(prompt.splitlines()[-1])["facts"]
        return self.raw or json.dumps(baseline(group)), 0


@pytest.fixture
def service():
    runtime = Runtime()
    service = api.QualityService(lambda: runtime)
    app.dependency_overrides[api.get_quality_service] = lambda: service
    yield service, runtime
    app.dependency_overrides.pop(api.get_quality_service, None)


def test_catalog_and_live_generation_use_only_frozen_facts(service):
    service, runtime = service
    with TestClient(app) as client:
        catalog = client.get("/ai/quality/scenarios")
        assert catalog.status_code == 200
        assert len(catalog.json()["scenarios"]) == 6
        missing = next(s for s in catalog.json()["scenarios"] if s["id"] == "QE-A01")
        assert missing["groups"][0]["occurrences"][0]["known_value"] == {
            "state": "unavailable"
        }
        grouped = next(s for s in catalog.json()["scenarios"] if s["id"] == "QE-A02")
        before = copy.deepcopy(service.scenarios)
        response = client.post(
            "/ai/quality/scenarios/QE-A02/explanations", json={"mode": "model"}
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data["groups"]) == 1
    assert data["groups"][0]["group"] == grouped["groups"][0]
    assert len(data["groups"][0]["group"]["occurrences"]) == 2
    assert data["groups"][0]["origin"] == "model"
    assert len(runtime.calls) == 1
    assert service.scenarios == before


@pytest.mark.parametrize(
    "error,code",
    [
        (TimeoutError(), "runtime_timeout"),
        (RuntimeUnavailable(), "runtime_unavailable"),
    ],
)
def test_runtime_failure_returns_visible_fallback(service, error, code):
    service, runtime = service
    runtime.error = error
    with TestClient(app) as client:
        data = client.post("/ai/quality/scenarios/QE-A01/explanations", json={}).json()
    item = data["groups"][0]
    assert item["origin"] == "deterministic"
    assert item["rejection_code"] == code
    assert item["state"] == "fallback_deterministic"
    assert len(runtime.calls) == 1
    assert "O valor ausente não pode ser determinado." in item["text"]["explanation"]


def test_refused_prose_is_hashed_and_never_returned(service):
    _, runtime = service
    invented = "O serial é B porque o operador o omitiu intencionalmente."
    runtime.raw = json.dumps(
        {
            "explanation": invented,
            "human_checks": ["Conferir os registros relacionados na fonte."],
        }
    )
    with TestClient(app) as client:
        response = client.post("/ai/quality/scenarios/QE-A01/explanations", json={})
    item = response.json()["groups"][0]
    assert item["rejection_code"] == "unsupported_explanation"
    assert item["response_sha256"]
    assert invented not in response.text


def test_baseline_and_empty_scenario_do_not_generate(service):
    _, runtime = service
    with TestClient(app) as client:
        response = client.post(
            "/ai/quality/scenarios/QE-A02/explanations", json={"mode": "baseline"}
        )
        empty = client.post("/ai/quality/scenarios/QD3-E01/explanations", json={})
    assert response.status_code == empty.status_code == 200
    assert response.json()["groups"][0]["origin"] == "deterministic"
    assert empty.json()["groups"] == []
    assert not runtime.calls


def test_concurrent_request_uses_fallback_without_calling_model(service):
    subject, runtime = service
    subject.lock.acquire()
    try:
        result = subject.generate("QE-A02", "model")
    finally:
        subject.lock.release()
    assert result.groups[0].rejection_code == "runtime_busy"
    assert not runtime.calls


@pytest.mark.parametrize(
    "body",
    [
        {"context": {"real_data": "not accepted"}},
        {"prompt": "arbitrary"},
        {"endpoint": "http://example.invalid"},
        {"mode": "mutate"},
    ],
)
def test_user_cannot_send_prompts_data_endpoints_or_mutations(service, body):
    with TestClient(app) as client:
        assert (
            client.post(
                "/ai/quality/scenarios/QE-A01/explanations", json=body
            ).status_code
            == 422
        )


def test_unknown_scenario_is_not_an_arbitrary_file_or_resource(service):
    with TestClient(app) as client:
        assert (
            client.post(
                "/ai/quality/scenarios/unknown/explanations", json={}
            ).status_code
            == 404
        )


@pytest.mark.real_authorization
def test_routes_require_session():
    with TestClient(app) as client:
        assert client.get("/ai/quality/scenarios").status_code == 401
        assert (
            client.post(
                "/ai/quality/scenarios/QE-A01/explanations", json={}
            ).status_code
            == 401
        )


def test_routes_require_execution_read(service):
    previous = app.dependency_overrides[get_actor_context]

    def no_permission(request):
        return replace(previous(request), permissions={})

    # Preserve FastAPI's Request dependency annotation.
    from fastapi import Request

    no_permission.__annotations__["request"] = Request
    app.dependency_overrides[get_actor_context] = no_permission
    try:
        with TestClient(app) as client:
            assert client.get("/ai/quality/scenarios").status_code == 403
            assert (
                client.post(
                    "/ai/quality/scenarios/QE-A01/explanations", json={}
                ).status_code
                == 403
            )
    finally:
        app.dependency_overrides[get_actor_context] = previous


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:11434",
        "http://example.invalid:11434",
        "http://127.0.0.1:11434/path",
        "http://user:pass@127.0.0.1:11434",
        "http://[",
        "http://127.0.0.1:11434?query=yes",
    ],
)
def test_transport_rejects_nonlocal_or_ambiguous_endpoint(monkeypatch, endpoint):
    monkeypatch.setenv("SYNERGIA_AI_QUALITY_ENDPOINT", endpoint)
    with pytest.raises(RuntimeUnavailable):
        api.LocalRuntime()


def test_transport_pins_digest_before_generation(monkeypatch):
    runtime = api.LocalRuntime()
    calls = []

    def request(route, payload=None):
        calls.append(route)
        if route == "version":
            return {"version": "0.40.12"}
        return {"models": [{"name": api.MODEL, "digest": "wrong"}]}

    monkeypatch.setattr(runtime, "request", request)
    with pytest.raises(RuntimeUnavailable):
        runtime.generate("synthetic", model=api.MODEL)
    assert calls == ["version", "tags"]


def test_transport_blocks_redirects_and_expired_deadline():
    runtime = api.LocalRuntime()
    runtime.deadline = 0
    with pytest.raises(TimeoutError):
        runtime.request("generate", {})
    with pytest.raises(RuntimeUnavailable):
        api.NoRedirect().redirect_request(
            None, None, 302, "", {}, "http://example.invalid"
        )
