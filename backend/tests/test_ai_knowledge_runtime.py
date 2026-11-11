"""Durability and budgets with a fake runtime; no credentials or localhost."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from ai_knowledge import KnowledgeError, read  # noqa: E402
from ai_knowledge_runtime import Budget, Runtime  # noqa: E402
from run_ai_knowledge_infrastructure import main  # noqa: E402


class FakeRuntime:
    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    def request(self, route, payload, timeout):
        self.calls += 1
        if self.error:
            raise self.error
        return {"done": True}


def protocol():
    result = copy.deepcopy(read(ROOT / "docs/ai-knowledge-poc-protocol.json"))
    result["budget"]["minimum_disk_free_bytes"] = 0
    return result


def test_only_the_pinned_local_endpoint_is_accepted():
    for endpoint in [
        "https://example.invalid",
        "http://127.0.0.1:11434/x",
        "http://user:password@127.0.0.1:11434",
    ]:
        with pytest.raises(KnowledgeError, match="only_pinned_local_endpoint"):
            Runtime(endpoint)


def test_failed_call_is_charged_retained_and_blocks_implicit_resume(tmp_path):
    p = protocol()
    fake = FakeRuntime(TimeoutError("synthetic timeout"))
    with Budget(tmp_path, p) as budget:
        with pytest.raises(TimeoutError):
            budget.call(fake, "chat", {}, tmp_path / "attempt.json", timeout=45)
    ledger = read(tmp_path / "budget.json")
    assert ledger["generative_calls"] == 1
    assert ledger["active_seconds"] == 45
    assert ledger["receipts"][0]["state"] == "transport_uncertain"
    assert read(tmp_path / "attempt.json")["error"] == "TimeoutError"
    with pytest.raises(KnowledgeError, match="unresolved_inference"):
        with Budget(tmp_path, p):
            pass
    assert fake.calls == 1


def test_completed_attempt_cannot_be_overwritten_or_charged_again(tmp_path):
    fake = FakeRuntime()
    with Budget(tmp_path, protocol()) as budget:
        budget.call(fake, "chat", {}, tmp_path / "one.json", 45)
        with pytest.raises(KnowledgeError, match="attempt_already_exists"):
            budget.call(fake, "chat", {}, tmp_path / "one.json", 45)
    assert fake.calls == 1
    assert read(tmp_path / "budget.json")["generative_calls"] == 1


def test_embedding_texts_not_requests_are_charged(tmp_path):
    with Budget(tmp_path, protocol()) as budget:
        budget.call(
            FakeRuntime(),
            "embed",
            {"input": ["a", "b", "c"]},
            tmp_path / "embed.json",
            45,
            count=3,
        )
    ledger = read(tmp_path / "budget.json")
    assert ledger["embedding_texts"] == 3
    assert ledger["generative_calls"] == 0


def test_count_mismatch_and_time_budget_fail_before_runtime(tmp_path):
    p = protocol()
    p["budget"]["active_inference_seconds"] = 1
    fake = FakeRuntime()
    with Budget(tmp_path, p) as budget:
        with pytest.raises(KnowledgeError, match="charge_payload_mismatch"):
            budget.call(fake, "embed", {"input": ["a", "b"]}, tmp_path / "bad.json", 1)
        with pytest.raises(KnowledgeError, match="inference_time_budget_exhausted"):
            budget.call(fake, "chat", {}, tmp_path / "over.json", 2)
    assert fake.calls == 0


def test_probe_limit_cannot_be_bypassed_with_a_new_directory(tmp_path):
    p = protocol()
    p["budget"]["generative_calls"]["probes"] = 1
    fake = FakeRuntime()
    with Budget(tmp_path, p) as budget:
        budget.call(fake, "chat", {}, tmp_path / "first.json", 1)
    with Budget(tmp_path, p) as budget:
        with pytest.raises(KnowledgeError, match="block2_probe_quota_exhausted"):
            budget.call(fake, "chat", {}, tmp_path / "second.json", 1)
    assert fake.calls == 1


def test_budget_mutation_requires_explicit_reconciliation(tmp_path):
    p = protocol()
    with Budget(tmp_path, p):
        pass
    p["budget"]["active_inference_seconds"] += 1
    with pytest.raises(KnowledgeError, match="budget_configuration_changed"):
        with Budget(tmp_path, p):
            pass


def test_concurrent_runner_and_path_escape_are_refused(tmp_path):
    with Budget(tmp_path, protocol()) as budget:
        with pytest.raises(KnowledgeError, match="inference_lock"):
            with Budget(tmp_path, protocol()):
                pass
        with pytest.raises(KnowledgeError, match="escaping_result_path"):
            budget.call(FakeRuntime(), "chat", {}, tmp_path.parent / "escape.json", 1)


def test_cli_has_no_reserved_split_and_requires_explicit_inference_flag():
    with pytest.raises(SystemExit) as exc:
        main(["retrieval", "--budget-root", "/tmp/x", "--output-dir", "/tmp/x/run"])
    assert exc.value.code == 2


def test_phase_quotas_share_global_budget_and_keep_legacy_probe_receipts(tmp_path):
    p = protocol()
    p["budget"]["generative_calls"]["probes"] = 1
    p["budget"]["generative_calls"]["calibration"] = 1
    fake = FakeRuntime()
    with Budget(tmp_path, p) as budget:
        budget.call(fake, "chat", {}, tmp_path / "probe.json", 1)
        # Simulate an existing block-2 receipt, which predates phase labels.
        del budget.state["receipts"][0]["phase"]
        budget.save()
    with Budget(tmp_path, p, "calibration") as budget:
        budget.call(fake, "chat", {}, tmp_path / "calibration.json", 1)
        with pytest.raises(KnowledgeError, match="phase_quota"):
            budget.call(fake, "chat", {}, tmp_path / "over.json", 1)
    with Budget(tmp_path, p) as budget:
        with pytest.raises(KnowledgeError, match="probe_quota"):
            budget.call(fake, "chat", {}, tmp_path / "over-probe.json", 1)
    assert read(tmp_path / "budget.json")["generative_calls"] == fake.calls == 2
