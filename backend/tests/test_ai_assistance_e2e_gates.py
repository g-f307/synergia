"""Portões integrados da #192: flags, transporte HTTP/pin, isolamento e fallback."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from test_ai_assistance_service import Contexts, Repository, make_actor

from app.ai_assistance_config import AiAssistanceConfig
from app.ai_assistance_fallback import required_limitations
from app.ai_assistance_generator import AiAssistanceGenerator
from app.ai_assistance_provider import LocalAiModelProvider
from app.ai_assistance_routes import get_assistance_service, get_read_service
from app.ai_assistance_service import AiAssistanceService
from app.authorization import (
    ActorContext,
    get_actor_context,
    get_authorization_repository,
)
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from generate_ai_assistance_corpus import build_case_context  # noqa: E402

MODEL = "qwen3:4b-instruct"
DIGEST = "sha256:0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"


def context(case_id: str = "AA-01"):
    return build_case_context(
        ROOT / "data" / "synthetic" / "ai-assistance-v1" / "cases" / f"{case_id}.json"
    )


class _SyntheticOllamaState:
    def __init__(self, payload: bytes, digest: str = DIGEST):
        self.payload = payload
        self.digest = digest
        self.calls = 0


def _start_synthetic_ollama(state: _SyntheticOllamaState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return None

        def do_GET(self):
            if self.path == "/api/version":
                body = json.dumps({"version": "0.40.15"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path in {"/api/tags", "/api/ps"}:
                body = json.dumps(
                    {
                        "models": [
                            {
                                "name": MODEL,
                                "digest": state.digest.removeprefix("sha256:"),
                            }
                        ]
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            if self.path == "/api/chat":
                length = int(self.headers.get("Content-Length", "0"))
                _ = self.rfile.read(length)
                state.calls += 1
                body = json.dumps(
                    {
                        "model": DIGEST.replace(":", "-", 1),
                        "done": True,
                        "message": {
                            "role": "assistant",
                            "content": state.payload.decode("utf-8", errors="replace"),
                        },
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _valid_model_payload(ctx) -> bytes:
    refs = sorted(ctx.evidence_refs())
    return json.dumps(
        {
            "summary": (
                f"A execução registra {ctx.counts.errors} erros, "
                f"{ctx.counts.warnings} avisos e "
                f"{ctx.counts.pending_items} pendências."
            ),
            "findings": [
                {
                    "title": "Registros disponíveis",
                    "explanation": "Há registros disponíveis para conferência.",
                    "evidence_refs": refs[:3],
                }
            ],
            "human_checks": ["Conferência humana das referências disponíveis."],
            "limitations": required_limitations(ctx),
        },
        ensure_ascii=False,
    ).encode()


def _configure_env(
    monkeypatch, *, enabled: str, generation_enabled: str, endpoint: str
):
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENABLED", enabled)
    monkeypatch.setenv(
        "SYNERGIA_AI_ASSISTANCE_GENERATION_ENABLED", generation_enabled
    )
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENDPOINT", endpoint)
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_MODEL", MODEL)
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_DIGEST", DIGEST)


def test_http_transport_pin_idempotency_flag_and_runtime_degradation(monkeypatch):
    ctx = context("AA-01")
    state = _SyntheticOllamaState(_valid_model_payload(ctx))
    server, endpoint = _start_synthetic_ollama(state)
    repo = Repository()
    actor_a = make_actor(ctx, "ai.assistance.generate", "ai.assistance.read")
    actor_b = ActorContext(
        user_id=uuid4(),
        session_id=uuid4(),
        token_id=uuid4(),
        permissions={
            "execution.read": frozenset({uuid4()}),
            "ai.assistance.generate": frozenset({uuid4()}),
            "ai.assistance.read": frozenset({uuid4()}),
        },
        correlation_id=uuid4(),
    )
    current_actor = {"actor": actor_a}
    audit_stub = type("Audit", (), {"audit_denial": lambda *args: None})()
    path = f"/executions/{ctx.subject.execution_id}/ai-assistance"

    try:
        _configure_env(
            monkeypatch, enabled="true", generation_enabled="true", endpoint=endpoint
        )
        config = AiAssistanceConfig(
            enabled=True,
            generation_enabled=True,
            endpoint=endpoint,
            model=MODEL,
            digest=DIGEST,
        )
        service = AiAssistanceService(
            Contexts(ctx),
            AiAssistanceGenerator(LocalAiModelProvider(config)),
            repo,
        )
        app = create_app()
        app.dependency_overrides[get_actor_context] = lambda: current_actor["actor"]
        app.dependency_overrides[get_assistance_service] = lambda: service
        app.dependency_overrides[get_read_service] = lambda: service
        app.dependency_overrides[get_authorization_repository] = lambda: audit_stub

        with TestClient(app) as client:
            cap = client.get("/me/ai-assistance-capability")
            assert cap.status_code == 200
            assert cap.json() == {"enabled": True, "read": True, "generate": True}

            first = client.post(path, json={})
            assert first.status_code == 200
            assert first.json()["state"] == "ready"
            assert first.json()["provenance"]["origin"] == "model"
            assert state.calls == 1

            # Reload / latest + repeat POST must reuse without new inference
            latest = client.get(path + "/latest")
            assert latest.status_code == 200
            assert latest.json() == first.json()
            repeat = client.post(path, json={})
            assert repeat.status_code == 200
            assert repeat.json() == first.json()
            assert state.calls == 1

            # Org B uniform 404 isolation
            current_actor["actor"] = actor_b
            assert client.get(path + "/latest").status_code == 404
            assert client.post(path, json={}).status_code == 404
            current_actor["actor"] = actor_a

            # Suspend generation while keeping read and readiness alive
            _configure_env(
                monkeypatch,
                enabled="true",
                generation_enabled="false",
                endpoint=endpoint,
            )
            assert client.get(path + "/latest").status_code == 200
            suspended = client.post(path, json={})
            assert suspended.status_code == 503
            assert (
                suspended.json()["error"]["code"] == "ai_assistance_generation_disabled"
            )
            assert client.get("/health/live").status_code == 200

            # Disable feature flag on server
            _configure_env(
                monkeypatch,
                enabled="false",
                generation_enabled="true",
                endpoint=endpoint,
            )
            cap_off = client.get("/me/ai-assistance-capability")
            assert cap_off.status_code == 200
            assert cap_off.json() == {
                "enabled": False,
                "read": False,
                "generate": False,
            }
            disabled_post = client.post(path, json={})
            assert disabled_post.status_code == 503
            assert disabled_post.json()["error"]["code"] == "ai_assistance_disabled"
            disabled_get = client.get(path + "/latest")
            assert disabled_get.status_code == 503
            assert disabled_get.json()["error"]["code"] == "ai_assistance_disabled"
    finally:
        server.shutdown()
        server.server_close()

    # Stopped runtime: new generation returns controlled 503/unavailable
    _configure_env(
        monkeypatch, enabled="true", generation_enabled="true", endpoint=endpoint
    )
    stopped_service = AiAssistanceService(
        Contexts(ctx),
        AiAssistanceGenerator(
            LocalAiModelProvider(
                AiAssistanceConfig(
                    enabled=True,
                    generation_enabled=True,
                    endpoint=endpoint,
                    model=MODEL,
                    digest=DIGEST,
                )
            )
        ),
        Repository(),
    )
    app2 = create_app()
    app2.dependency_overrides[get_actor_context] = lambda: actor_a
    app2.dependency_overrides[get_assistance_service] = lambda: stopped_service
    app2.dependency_overrides[get_read_service] = lambda: stopped_service
    app2.dependency_overrides[get_authorization_repository] = lambda: audit_stub
    with TestClient(app2) as client2:
        resp = client2.post(path, json={})
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "ai_assistance_runtime_unavailable"
        assert client2.get("/health/live").status_code == 200


def test_invalid_outputs_and_out_of_context_refs_are_100_percent_rejected(monkeypatch):
    ctx = context("AA-01")
    invalid_payloads = [
        b"not json at all",
        json.dumps({"summary": "ok"}).encode(),
        json.dumps(
            {
                "summary": "Select * from executions caused by bug.",
                "findings": [],
                "human_checks": [],
                "limitations": required_limitations(ctx),
            }
        ).encode(),
        json.dumps(
            {
                "summary": "A execução registra 1 erros, 0 avisos e 0 pendências.",
                "findings": [
                    {
                        "title": "Ref inventada",
                        "explanation": "Há registros disponíveis para conferência.",
                        "evidence_refs": ["DIV-" + "f" * 32],
                    }
                ],
                "human_checks": ["Conferência humana das referências disponíveis."],
                "limitations": required_limitations(ctx),
            }
        ).encode(),
    ]
    for payload in invalid_payloads:
        state = _SyntheticOllamaState(payload)
        server, endpoint = _start_synthetic_ollama(state)
        try:
            _configure_env(
                monkeypatch,
                enabled="true",
                generation_enabled="true",
                endpoint=endpoint,
            )
            config = AiAssistanceConfig(
                enabled=True,
                generation_enabled=True,
                endpoint=endpoint,
                model=MODEL,
                digest=DIGEST,
            )
            generator = AiAssistanceGenerator(LocalAiModelProvider(config))
            result = generator.generate(ctx)
            assert result.state == "rejected"
            assert result.origin == "deterministic"
            assert result.findings == []
            assert result.limitations
        finally:
            server.shutdown()
            server.server_close()


def test_http_pin_mismatch_returns_unavailable(monkeypatch):
    ctx = context("AA-01")
    state = _SyntheticOllamaState(
        _valid_model_payload(ctx), digest="sha256:" + "f" * 64
    )
    server, endpoint = _start_synthetic_ollama(state)
    try:
        _configure_env(
            monkeypatch, enabled="true", generation_enabled="true", endpoint=endpoint
        )
        config = AiAssistanceConfig(
            enabled=True,
            generation_enabled=True,
            endpoint=endpoint,
            model=MODEL,
            digest=DIGEST,
        )
        generator = AiAssistanceGenerator(LocalAiModelProvider(config))
        result = generator.generate(ctx)
        assert result.state == "unavailable"
        assert result.origin == "deterministic"
        assert result.rejection_code == "runtime_pin_mismatch"
        assert state.calls == 0
    finally:
        server.shutdown()
        server.server_close()
