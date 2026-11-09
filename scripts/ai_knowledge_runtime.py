"""Bounded localhost requests and durable PoC budgets; no retry or fallback."""

from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

from ai_knowledge import KnowledgeError, digest, read, write_new


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise KnowledgeError("runtime_redirect_refused")


class Runtime:
    def __init__(self, endpoint="http://127.0.0.1:11434"):
        if endpoint != "http://127.0.0.1:11434":
            raise KnowledgeError("only_pinned_local_endpoint_allowed")
        self.endpoint = endpoint
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        )

    def request(self, route, payload=None, timeout=10):
        allowed = {"version", "tags", "ps", "show", "embed", "chat", "generate"}
        if route not in allowed:
            raise KnowledgeError("unknown_runtime_route")
        request = urllib.request.Request(
            f"{self.endpoint}/api/{route}",
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise KnowledgeError("runtime_response_too_large")
                return json.loads(raw)
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError("runtime_timeout") from exc
            raise KnowledgeError("runtime_transport_failure") from exc

    def inventory(self, protocol):
        version = self.request("version")
        if version.get("version") != protocol["runtime"]["version"]:
            raise KnowledgeError("runtime_version_changed")
        tags = self.request("tags")["models"]
        selected = {}
        for name, expected in protocol["models"].items():
            tag = next((t for t in tags if t["name"] == name), None)
            if tag is None or tag["digest"] != expected:
                raise KnowledgeError("model_pin_mismatch")
            selected[name] = self.clean_tag(tag)
        embed_name = protocol["retrieval"]["embedding_model"]
        embed_tag = next((t for t in tags if t["name"] == embed_name), None)
        if embed_tag is None:
            raise KnowledgeError("embedding_model_not_installed")
        if embed_tag["digest"] != protocol["retrieval"]["embedding_digest"]:
            raise KnowledgeError("embedding_pin_mismatch")
        selected[embed_name] = self.clean_tag(embed_tag)
        configurations = {}
        for name in selected:
            shown = self.request("show", {"model": name})
            configurations[name] = {
                "parameters": shown.get("parameters"),
                "template_sha256": digest(shown.get("template")),
                "system_sha256": digest(shown.get("system")),
            }
        return {
            "runtime": version,
            "models": selected,
            "configuration": configurations,
            "loaded": self.request("ps"),
        }

    @staticmethod
    def clean_tag(tag):
        result = {key: tag[key] for key in ("name", "digest", "size", "details")}
        result["details"] = {
            k: v for k, v in tag["details"].items() if k != "parent_model"
        }
        return result

    def unload(self, model):
        # No prompt: this is a model-management request, not a generation attempt.
        self.request("generate", {"model": model, "keep_alive": 0, "stream": False})


class Budget:
    """One shared ledger across run directories; reserve before sending anything.

    Crash/transport uncertainty keeps the full reserved time. An unresolved call
    blocks further inference until explicit reconciliation; it is never retried.
    """

    def __init__(self, root: Path, protocol: dict, phase: str = "probes"):
        self.root = root
        self.spec = protocol["budget"]
        if phase not in self.spec["generative_calls"]:
            raise KnowledgeError("unknown_budget_phase")
        self.phase = phase
        self.path = root / "budget.json"
        self.lock = root / "inference.lock"
        self.owned = False

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise KnowledgeError("inference_lock_requires_reconciliation") from exc
        os.close(fd)
        self.owned = True
        if not self.path.exists():
            write_new(
                self.path,
                {
                    "budget_sha256": digest(self.spec),
                    "generative_calls": 0,
                    "embedding_texts": 0,
                    "active_seconds": 0.0,
                    "receipts": [],
                },
            )
        self.state = read(self.path)
        if self.state.get("budget_sha256") != digest(self.spec):
            self.__exit__(None, None, None)
            raise KnowledgeError("budget_configuration_changed")
        if any(r["state"] != "completed" for r in self.state["receipts"]):
            self.__exit__(None, None, None)
            raise KnowledgeError("unresolved_inference_requires_reconciliation")
        return self

    def __exit__(self, *args):
        if self.owned:
            self.lock.unlink()
            self.owned = False

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2) + "\n"
        )
        temporary.replace(self.path)

    def call(self, runtime, route, payload, result_path: Path, timeout, count=1):
        if not result_path.resolve().is_relative_to(self.root.resolve()):
            raise KnowledgeError("escaping_result_path")
        if result_path.exists():
            raise KnowledgeError("attempt_already_exists")
        if route not in {"chat", "embed"}:
            raise KnowledgeError("unbudgeted_inference_route")
        if type(count) is not int or count <= 0 or timeout <= 0:
            raise KnowledgeError("invalid_charge")
        expected_count = len(payload.get("input", [])) if route == "embed" else 1
        if count != expected_count:
            raise KnowledgeError("charge_payload_mismatch")
        if shutil.disk_usage(self.root).free < self.spec["minimum_disk_free_bytes"]:
            raise KnowledgeError("insufficient_disk_margin")
        kind = "embedding_texts" if route == "embed" else "generative_calls"
        limit = (
            self.spec["embedding_texts"]
            if route == "embed"
            else self.spec["hard_call_limit"]
        )
        if self.state[kind] + count > limit:
            raise KnowledgeError("inference_count_budget_exhausted")
        if (
            self.state["active_seconds"] + timeout
            > self.spec["active_inference_seconds"]
        ):
            raise KnowledgeError("inference_time_budget_exhausted")
        phase_used = sum(
            r["count"]
            for r in self.state["receipts"]
            if r["route"] == "chat" and r.get("phase", "probes") == self.phase
        )
        if (
            route == "chat"
            and phase_used + count > self.spec["generative_calls"][self.phase]
        ):
            code = (
                "block2_probe_quota_exhausted"
                if self.phase == "probes"
                else "phase_quota_exhausted"
            )
            raise KnowledgeError(code)
        attempt = {
            "route": route,
            "phase": self.phase,
            "count": count,
            "result": str(result_path.relative_to(self.root)),
            "state": "started",
            "reserved_seconds": timeout,
        }
        if any(r["result"] == attempt["result"] for r in self.state["receipts"]):
            raise KnowledgeError("attempt_id_already_charged")
        self.state[kind] += count
        self.state["active_seconds"] += timeout
        self.state["receipts"].append(attempt)
        self.save()
        started = time.monotonic()
        record = {"request": payload, "response": None, "error": None}
        try:
            record["response"] = runtime.request(route, payload, timeout)
        except Exception as exc:
            record["error"] = type(exc).__name__
            record["elapsed_seconds"] = time.monotonic() - started
            write_new(result_path, record)
            # No following inference/unload; HTTP cancellation is not proof of stop.
            attempt["state"] = "transport_uncertain"
            self.save()
            raise
        elapsed = time.monotonic() - started
        record["elapsed_seconds"] = elapsed
        write_new(result_path, record)
        self.state["active_seconds"] += elapsed - timeout
        attempt.update(state="completed", elapsed_seconds=elapsed)
        self.save()
        return record
