"""Frozen requests, one-shot validation and batch resume with a fake runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_ai_knowledge_development as runner  # noqa: E402
from ai_knowledge import KnowledgeError, digest, inputs, read  # noqa: E402


def test_prepare_is_gold_free_and_requests_are_frozen(tmp_path, monkeypatch):
    real_read = runner.read

    def without_gold(path):
        assert "gold" not in str(path)
        return real_read(path)

    monkeypatch.setattr(runner, "read", without_gold)
    output = tmp_path / "calibration"
    runner.prepare("calibration", output)
    plan = read(output / "plan.json")
    assert len(plan["requests"]) == 64
    assert digest(plan["requests"]) == plan["requests_sha256"]
    assert not plan["reserved_allowed"]
    with pytest.raises(FileExistsError):
        runner.prepare("calibration", output)


def test_validation_campaign_cannot_be_reprepared_after_selection(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "source_hashes", lambda: {})
    selection = {
        "development_confirmed": True,
        "models": {
            m: {"profile": "historical", "variant": "checklist"}
            for m in read(runner.BASE)["models"]
        },
        "rankings": {c["case_id"]: ["K03"] for c in inputs("validation")},
    }
    root = tmp_path / ".test-tmp" / "campaign"
    runner.prepare("validation", root / "first", selection)
    with pytest.raises(FileExistsError):
        runner.prepare("validation", root / "second", selection)
    assert read(root / "validation-lock.json")["selection_sha256"] == digest(selection)


def test_completed_calls_are_not_repeated_on_batch_resume(tmp_path, monkeypatch):
    output = tmp_path / "run"
    runner.prepare("calibration", output)
    plan = read(output / "plan.json")
    plan["requests"] = plan["requests"][:2]
    plan["requests_sha256"] = digest(plan["requests"])
    plan["protocol"]["budget"]["minimum_disk_free_bytes"] = 0
    (output / "plan.json").write_text(json.dumps(plan))
    calls = []

    class FakeRuntime:
        def inventory(self, protocol):
            return {"loaded": {"models": []}}

        def request(self, route, payload=None, timeout=None):
            if route == "chat":
                calls.append(payload)
                return {"message": {"content": "{}"}, "done_reason": "stop"}
            return {"models": []}

        def unload(self, model):
            pass

    class FakeSampler:
        failure = None

        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def report(self):
            return {}

    monkeypatch.setattr(runner, "Runtime", FakeRuntime)
    monkeypatch.setattr(runner, "Sampler", FakeSampler)
    monkeypatch.setattr(runner, "hardware", lambda: {})
    runner.execute(tmp_path, output, 1)
    assert len(calls) == 1
    assert not (output / "complete.json").exists()
    runner.execute(tmp_path, output, 1)
    assert len(calls) == 2
    assert read(output / "complete.json")["calls"] == 2
    runner.execute(tmp_path, output, 1)
    assert len(calls) == 2
    # A mutated completed request must not be silently replayed.
    plan["requests"][0]["body"]["options"]["seed"] = 999
    plan["requests_sha256"] = digest(plan["requests"])
    (output / "plan.json").write_text(json.dumps(plan))
    with pytest.raises(KnowledgeError, match="attempt_requires_reconciliation"):
        runner.execute(tmp_path, output, 1)
    assert len(calls) == 2
