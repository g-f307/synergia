import json
from io import BytesIO
from unittest.mock import Mock

import pytest

from app.ai_assistance_config import AiAssistanceConfig
from app.ai_assistance_provider import LocalAiModelProvider, ProviderError


def provider():
    config = AiAssistanceConfig.from_environment(
        {
            "SYNERGIA_AI_ASSISTANCE_ENABLED": "true",
            "SYNERGIA_AI_ASSISTANCE_ENDPOINT": "http://127.0.0.1:11434",
            "SYNERGIA_AI_ASSISTANCE_MODEL": "test:latest",
            "SYNERGIA_AI_ASSISTANCE_DIGEST": "sha256:" + "a" * 64,
        }
    )
    return LocalAiModelProvider(config)


def response(data):
    stream = BytesIO(data)
    stream.__enter__ = lambda s: s
    stream.__exit__ = lambda s, *args: s.close()
    return stream


def test_single_generation_and_fixed_settings():
    p = provider()
    p.opener.open = Mock(
        side_effect=[
            response(b'{"version":"0.40.15"}'),
            response(
                json.dumps(
                    {"models": [{"name": "test:latest", "digest": "a" * 64}]}
                ).encode()
            ),
            response(
                (
                    ' {"model":"sha256-'
                    + "a" * 64
                    + '","done":true,"message":{"role":"assistant","content":"{}"}}'
                )
                .strip()
                .encode()
            ),
            response(
                json.dumps(
                    {"models": [{"name": "test:latest", "digest": "a" * 64}]}
                ).encode()
            ),
            response(
                json.dumps(
                    {"models": [{"name": "test:latest", "digest": "a" * 64}]}
                ).encode()
            ),
        ]
    )
    assert p._generate("system", "prompt", {}) == b"{}"
    calls = p.opener.open.call_args_list
    assert len(calls) == 5
    payload = json.loads(calls[2].args[0].data)
    assert payload["think"] is False
    assert payload["options"] == {"temperature": 0, "seed": 42, "num_predict": 512}
    assert payload["model"] == "sha256-" + "a" * 64
    assert "tools" not in payload


def test_digest_mismatch_transport():
    p = provider()
    p.opener.open = Mock(
        side_effect=[
            response(b'{"version":"0.40.15"}'),
            response(b'{"models":[]}'),
            response(b'{"version":"0.40.15"}'),
            response(b'{"models":[]}'),
        ]
    )
    for _ in range(2):
        with pytest.raises(ProviderError, match="runtime_pin_mismatch"):
            p._generate("system", "prompt", {})


def test_oversize_transport():
    p = provider()
    p.opener.open = Mock(side_effect=[response(b"x" * 8193), response(b"x" * 8193)])
    for _ in range(2):
        with pytest.raises(ProviderError, match="runtime_response_too_large"):
            p._generate("system", "prompt", {})


def test_timeout_slow_headers_and_lock_recovery(monkeypatch):
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import app.ai_assistance_provider as module

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(1)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = AiAssistanceConfig.from_environment(
        {
            "SYNERGIA_AI_ASSISTANCE_ENABLED": "true",
            "SYNERGIA_AI_ASSISTANCE_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
            "SYNERGIA_AI_ASSISTANCE_MODEL": "test:latest",
            "SYNERGIA_AI_ASSISTANCE_DIGEST": "sha256:" + "a" * 64,
        }
    )
    p = LocalAiModelProvider(config)
    monkeypatch.setattr(module, "TIMEOUT_SECONDS", 0.3)
    try:
        for _ in range(2):
            started = time.monotonic()
            with pytest.raises(ProviderError, match="runtime_timeout"):
                p.generate("system", "prompt", {})
            assert time.monotonic() - started < 1.5
    finally:
        server.shutdown()
        server.server_close()


def test_busy_lock():
    from app.ai_assistance_provider import _LOCK

    p = provider()
    assert _LOCK.acquire(blocking=False)
    try:
        with pytest.raises(ProviderError, match="runtime_busy"):
            p.generate("system", "prompt", {})
    finally:
        _LOCK.release()


def test_changed_loaded_digest_is_rejected():
    p = provider()
    good = json.dumps(
        {"models": [{"name": "test:latest", "digest": "a" * 64}]}
    ).encode()
    bad = json.dumps({"models": [{"name": "test:latest", "digest": "b" * 64}]}).encode()
    p.opener.open = Mock(
        side_effect=[
            response(b'{"version":"0.40.15"}'),
            response(good),
            response(
                (
                    ' {"model":"sha256-'
                    + "a" * 64
                    + '","done":true,"message":{"role":"assistant","content":"{}"}}'
                )
                .strip()
                .encode()
            ),
            response(good),
            response(bad),
        ]
    )
    with pytest.raises(ProviderError, match="runtime_pin_mismatch"):
        p._generate("system", "prompt", {})


def test_redirect_is_not_followed():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", "http://example.invalid/")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = AiAssistanceConfig.from_environment(
        {
            "SYNERGIA_AI_ASSISTANCE_ENABLED": "true",
            "SYNERGIA_AI_ASSISTANCE_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
            "SYNERGIA_AI_ASSISTANCE_MODEL": "test:latest",
            "SYNERGIA_AI_ASSISTANCE_DIGEST": "sha256:" + "a" * 64,
        }
    )
    try:
        with pytest.raises(ProviderError, match="runtime_redirect"):
            LocalAiModelProvider(config).generate("system", "prompt", {})
    finally:
        server.shutdown()
        server.server_close()


def test_cancel_releases_lock(monkeypatch):
    import app.ai_assistance_provider as module

    class Context:
        def Pipe(self, duplex):
            raise KeyboardInterrupt

    monkeypatch.setattr(module.multiprocessing, "get_context", lambda _: Context())
    with pytest.raises(KeyboardInterrupt):
        provider().generate("system", "prompt", {})
    assert module._LOCK.acquire(blocking=False)
    module._LOCK.release()


def test_spawned_provider_success_and_single_inference():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    events = []
    models = json.dumps(
        {"models": [{"name": "test:latest", "digest": "a" * 64}]}
    ).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"version":"0.40.15"}' if self.path == "/api/version" else models
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            events.append(
                json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            )
            body = (
                (
                    ' {"model":"sha256-'
                    + "a" * 64
                    + '","done":true,"message":{"role":"assistant","content":"{}"}}'
                )
                .strip()
                .encode()
            )
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = AiAssistanceConfig.from_environment(
        {
            "SYNERGIA_AI_ASSISTANCE_ENABLED": "true",
            "SYNERGIA_AI_ASSISTANCE_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
            "SYNERGIA_AI_ASSISTANCE_MODEL": "test:latest",
            "SYNERGIA_AI_ASSISTANCE_DIGEST": "sha256:" + "a" * 64,
        }
    )
    try:
        assert LocalAiModelProvider(config).generate("system", "prompt", {}) == b"{}"
        assert len(events) == 1
        assert "tools" not in events[0]
    finally:
        server.shutdown()
        server.server_close()


def test_slow_drip_body_respects_total_deadline(monkeypatch):
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import app.ai_assistance_provider as module

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            for _ in range(100):
                try:
                    self.wfile.write(b"x")
                    self.wfile.flush()
                except OSError:
                    return
                time.sleep(0.05)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = AiAssistanceConfig.from_environment(
        {
            "SYNERGIA_AI_ASSISTANCE_ENABLED": "true",
            "SYNERGIA_AI_ASSISTANCE_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
            "SYNERGIA_AI_ASSISTANCE_MODEL": "test:latest",
            "SYNERGIA_AI_ASSISTANCE_DIGEST": "sha256:" + "a" * 64,
        }
    )
    monkeypatch.setattr(module, "TIMEOUT_SECONDS", 0.3)
    try:
        started = time.monotonic()
        with pytest.raises(ProviderError, match="runtime_timeout"):
            LocalAiModelProvider(config).generate("system", "prompt", {})
        assert time.monotonic() - started < 1.5
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("scenario", ["digest", "oversize", "unavailable"])
def test_public_provider_releases_lock_after_runtime_failure(scenario):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if scenario == "oversize":
                body, status = b"x" * 8193, 200
            elif scenario == "unavailable":
                body, status = b"", 503
            elif self.path == "/api/version":
                body, status = b'{"version":"0.40.15"}', 200
            else:
                body, status = b'{"models":[]}', 200
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = AiAssistanceConfig.from_environment(
        {
            "SYNERGIA_AI_ASSISTANCE_ENABLED": "true",
            "SYNERGIA_AI_ASSISTANCE_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
            "SYNERGIA_AI_ASSISTANCE_MODEL": "test:latest",
            "SYNERGIA_AI_ASSISTANCE_DIGEST": "sha256:" + "a" * 64,
        }
    )
    expected = {
        "digest": "runtime_pin_mismatch",
        "oversize": "runtime_response_too_large",
        "unavailable": "runtime_unavailable",
    }[scenario]
    try:
        p = LocalAiModelProvider(config)
        for _ in range(2):
            with pytest.raises(ProviderError, match=expected):
                p.generate("system", "prompt", {})
    finally:
        server.shutdown()
        server.server_close()
