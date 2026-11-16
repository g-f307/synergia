import json

import pytest
from fastapi.testclient import TestClient

import app.ai_assistance_health as health
from app.ai_assistance_provider import ProviderError
from app.main import create_app

TOKEN = "synthetic-observability-191-" + "x" * 32
PATH = "/operations/ai-assistance/health"


def configure(monkeypatch):
    for key, value in {
        "ENABLED": "true",
        "GENERATION_ENABLED": "true",
        "ENDPOINT": "http://127.0.0.1:11434",
        "MODEL": "synthetic:1",
        "DIGEST": "sha256:" + "a" * 64,
    }.items():
        monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_" + key, value)
    monkeypatch.setenv("OBSERVABILITY_METRICS_TOKEN", TOKEN)


def test_probe_requires_technical_auth_before_any_request(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(
        health, "probe_assistance", lambda: pytest.fail("unauthorized probe")
    )
    with TestClient(create_app()) as http:
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            assert http.get(PATH, headers=headers).status_code == 401


@pytest.mark.parametrize(
    "disabled,status", [("ENABLED", "disabled"), ("GENERATION_ENABLED", "suspended")]
)
def test_disabled_and_suspended_do_not_touch_runtime(monkeypatch, disabled, status):
    configure(monkeypatch)
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_" + disabled, "false")
    monkeypatch.setattr(
        health, "LocalAiModelProvider", lambda *a, **k: pytest.fail("runtime touched")
    )
    with TestClient(create_app()) as http:
        response = http.get(PATH, headers={"Authorization": "Bearer " + TOKEN})
    assert response.status_code == 200
    assert response.json()["status"] == status
    assert not response.json()["generation_enabled"]


@pytest.mark.parametrize(
    "code,status",
    [
        (None, "healthy"),
        ("runtime_busy", "busy"),
        ("runtime_timeout", "unavailable"),
        ("runtime_redirect", "unavailable"),
        ("runtime_pin_mismatch", "unavailable"),
        ("runtime_response_too_large", "unavailable"),
        ("private-secret", "unavailable"),
    ],
)
def test_probe_is_informative_and_sanitized(monkeypatch, code, status):
    configure(monkeypatch)

    class Provider:
        def __init__(self, *a, **k):
            pass

        def probe(self):
            if code:
                raise ProviderError(code)

    monkeypatch.setattr(health, "LocalAiModelProvider", Provider)
    with TestClient(create_app()) as http:
        result = http.get(PATH, headers={"Authorization": "Bearer " + TOKEN})
    assert result.status_code == 200 and result.json()["status"] == status
    assert set(result.json()) == {"status", "code", "generation_enabled", "duration_ms"}
    assert result.json()["duration_ms"] >= 0
    assert not any(
        value in result.text
        for value in (TOKEN, "127.0.0.1", "synthetic:1", "a" * 64, "private-secret")
    )


def test_runtime_failure_does_not_affect_readiness(monkeypatch):
    import app.observability.health as checks
    from app.observability.health import ComponentStatus

    configure(monkeypatch)
    monkeypatch.setattr(
        checks,
        "probe_postgresql",
        lambda _: ComponentStatus("postgresql", "healthy", True, 0),
    )
    monkeypatch.setattr(
        checks,
        "probe_storage",
        lambda _: ComponentStatus("storage", "healthy", True, 0),
    )

    class Provider:
        def __init__(self, *a, **k):
            pass

        def probe(self):
            raise ProviderError("runtime_unavailable")

    monkeypatch.setattr(health, "LocalAiModelProvider", Provider)
    with TestClient(create_app()) as http:
        assert (
            http.get(PATH, headers={"Authorization": "Bearer " + TOKEN}).json()[
                "status"
            ]
            == "unavailable"
        )
        assert http.get("/health/ready").status_code == 200
        assert http.get("/health/live").status_code == 200


@pytest.mark.parametrize("scenario", ["healthy", "redirect", "oversize", "slow"])
def test_real_probe_transport_never_sends_inference(monkeypatch, scenario):
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import app.ai_assistance_provider as transport
    from app.ai_assistance_config import AiAssistanceConfig
    from app.ai_assistance_provider import LocalAiModelProvider

    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            if scenario == "slow":
                time.sleep(1)
                return
            if scenario == "redirect":
                self.send_response(302)
                self.send_header("Location", "http://example.invalid/")
                self.end_headers()
                return
            data = (
                b"x" * 8193
                if scenario == "oversize"
                else (
                    b'{"version":"0.40.15"}'
                    if self.path == "/api/version"
                    else json.dumps(
                        {"models": [{"name": "synthetic:1", "digest": "a" * 64}]}
                    ).encode()
                )
            )
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            calls.append("FORBIDDEN_POST")
            self.send_error(500)

        def log_message(self, *args):
            pass

    configure(monkeypatch)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv(
        "SYNERGIA_AI_ASSISTANCE_ENDPOINT", f"http://127.0.0.1:{server.server_port}"
    )
    if scenario == "slow":
        monkeypatch.setattr(transport, "PROBE_TIMEOUT_SECONDS", 0.4)
    try:
        import os

        provider = LocalAiModelProvider(AiAssistanceConfig.from_environment(os.environ))
        if scenario == "healthy":
            provider.probe()
            assert calls == ["/api/version", "/api/tags"]
        else:
            expected = {
                "redirect": "runtime_redirect",
                "oversize": "runtime_response_too_large",
                "slow": "runtime_timeout",
            }[scenario]
            with pytest.raises(ProviderError, match=expected):
                provider.probe()
        assert "FORBIDDEN_POST" not in calls
        assert transport._LOCK.acquire(blocking=False)
        transport._LOCK.release()
    finally:
        server.shutdown()
        server.server_close()
