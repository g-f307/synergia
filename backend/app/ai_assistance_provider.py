"""Bounded, single-flight local inference transport for assistance."""

from __future__ import annotations

import json
import multiprocessing
import threading
import time
import urllib.error
import urllib.request
from typing import Protocol

from app.ai_assistance_config import AiAssistanceConfig


class ProviderError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class AiModelProvider(Protocol):
    model: str
    digest: str

    def generate(self, system: str, prompt: str, schema: dict) -> bytes: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ProviderError("runtime_redirect")


_LOCK = threading.Lock()
TIMEOUT_SECONDS = 30


def _worker(connection, config, allowed_service, system, prompt, schema):
    try:
        provider = LocalAiModelProvider(config, allowed_service=allowed_service)
        result = provider._generate(system, prompt, schema)
        connection.send(("ok", result))
    except ProviderError as exc:
        connection.send(("error", exc.code))
    except BaseException:
        connection.send(("error", "runtime_unavailable"))
    finally:
        connection.close()


class LocalAiModelProvider:
    """A configured Ollama instance; one generation, no tools and no proxy."""

    def __init__(self, config: AiAssistanceConfig, *, allowed_service: str = ""):
        # Revalidate even if a caller constructed the frozen dataclass directly.
        checked = AiAssistanceConfig.from_environment(
            {
                "SYNERGIA_AI_ASSISTANCE_ENABLED": "true" if config.enabled else "false",
                "SYNERGIA_AI_ASSISTANCE_ENDPOINT": config.endpoint,
                "SYNERGIA_AI_ASSISTANCE_MODEL": config.model,
                "SYNERGIA_AI_ASSISTANCE_DIGEST": config.digest,
                "SYNERGIA_AI_ASSISTANCE_ALLOWED_SERVICE": allowed_service,
                "SYNERGIA_AI_ASSISTANCE_RETENTION_DAYS": str(config.retention_days),
            }
        )
        if not checked.enabled or config != checked:
            raise ValueError("invalid assistance runtime configuration")
        self.endpoint, self.model, self.digest = (
            checked.endpoint,
            checked.model,
            checked.digest,
        )
        self.config = checked
        self.allowed_service = allowed_service
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )

    def _request(
        self, route: str, deadline: float, payload: dict | None = None
    ) -> bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("runtime_timeout")
        request = urllib.request.Request(
            self.endpoint + route,
            data=None
            if payload is None
            else json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=remaining) as response:
                raw = response.read(8193)
                if len(raw) > 8192:
                    raise ProviderError("runtime_response_too_large")
                if time.monotonic() > deadline:
                    raise ProviderError("runtime_timeout")
                return raw
        except ProviderError:
            raise
        except TimeoutError:
            raise ProviderError("runtime_timeout") from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise ProviderError("runtime_timeout") from None
            raise ProviderError("runtime_unavailable") from None
        except (OSError, ValueError):
            raise ProviderError("runtime_unavailable") from None

    def _verify_pin(self, route: str, deadline: float) -> None:
        try:
            data = json.loads(self._request(route, deadline))
            models = data["models"]
            if not isinstance(models, list) or not any(
                isinstance(item, dict)
                and (route == "/api/ps" or item.get("name") == self.model)
                and item.get("digest") == self.digest.removeprefix("sha256:")
                for item in models
            ):
                raise ProviderError("runtime_pin_mismatch")
        except (ValueError, UnicodeError, AttributeError, TypeError, KeyError):
            raise ProviderError("runtime_unavailable") from None

    def _generate(self, system: str, prompt: str, schema: dict) -> bytes:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        try:
            version = json.loads(self._request("/api/version", deadline))
            if version.get("version") != "0.40.15":
                raise ProviderError("runtime_pin_mismatch")
        except (ValueError, UnicodeError, AttributeError, TypeError):
            raise ProviderError("runtime_unavailable") from None
        self._verify_pin("/api/tags", deadline)
        raw = self._request(
            "/api/chat",
            deadline,
            {
                "model": self.digest.replace(":", "-", 1),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "format": schema,
                "options": {"temperature": 0, "seed": 42, "num_predict": 512},
            },
        )
        # Refuse output when the advertised or loaded model has changed.
        self._verify_pin("/api/tags", deadline)
        self._verify_pin("/api/ps", deadline)
        try:
            envelope = json.loads(raw)
            message = envelope.get("message")
            if (
                envelope.get("model") != self.digest.replace(":", "-", 1)
                or envelope.get("done") is not True
                or not isinstance(message, dict)
                or message.get("role") != "assistant"
                or not isinstance(message.get("content"), str)
                or message.get("tool_calls")
                or message.get("thinking")
            ):
                raise ValueError
            return message["content"].encode("utf-8")
        except (ValueError, UnicodeError, AttributeError):
            raise ProviderError("runtime_invalid_response") from None

    def generate(self, system: str, prompt: str, schema: dict) -> bytes:
        if not _LOCK.acquire(blocking=False):
            raise ProviderError("runtime_busy")
        process = None
        receive = send = None
        try:
            # A process boundary also bounds slow headers and slow-drip bodies;
            # socket timeouts alone are inactivity limits, not total deadlines.
            started = time.monotonic()
            ctx = multiprocessing.get_context("spawn")
            receive, send = ctx.Pipe(duplex=False)
            process = ctx.Process(
                target=_worker,
                args=(send, self.config, self.allowed_service, system, prompt, schema),
                daemon=True,
            )
            process.start()
            send.close()
            send = None
            # Reserve time for process termination and result assembly inside the
            # configured 30-second end-to-end envelope.
            budget = TIMEOUT_SECONDS - 1 if TIMEOUT_SECONDS > 1 else TIMEOUT_SECONDS
            remaining = max(0.0, budget - (time.monotonic() - started))
            if not receive.poll(remaining):
                raise ProviderError("runtime_timeout")
            try:
                state, value = receive.recv()
            except (EOFError, OSError):
                raise ProviderError("runtime_unavailable") from None
            if state != "ok":
                raise ProviderError(value)
            return value
        finally:
            try:
                if process is not None and process.pid is not None:
                    if process.is_alive():
                        process.terminate()
                    process.join(timeout=1)
                    if process.is_alive():
                        process.kill()
                        process.join()
                    process.close()
                if receive is not None:
                    receive.close()
                if send is not None:
                    send.close()
            finally:
                _LOCK.release()
