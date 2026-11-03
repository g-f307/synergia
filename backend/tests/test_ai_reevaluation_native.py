"""Offline regressions for actual native choices, grounding and read-only scope."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import ai_operational_summary as op  # noqa: E402
import ai_reevaluation as runner  # noqa: E402
from ai_poc_foundation import PoCFoundationError  # noqa: E402
from ai_reevaluation_native import collect_native_attempt  # noqa: E402
from evaluate_ai_operational import score_tool_calls  # noqa: E402

CASE = op.load_case(ROOT / "data/synthetic/ai-operational-v3/OP3-D02-input.json")
GOLD = json.loads(
    (ROOT / "data/synthetic/ai-operational-v3/OP3-D02-gold.json").read_text()
)
PROMPT = ROOT / "scripts/ai_poc_prompts/operational-native-v1.txt"


def call(name, args):
    return {"type": "function", "function": {"name": name, "arguments": args}}


class Runtime:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.requests = []

    def generate(self, prompt, *, model):
        self.requests.append(json.loads(prompt))
        return json.dumps({"tool_calls": next(self.frames)}), 20


def execute(frames):
    runtime = Runtime(frames)
    return collect_native_attempt(CASE, runtime, "fake", prompt_path=PROMPT), runtime


def test_native_agent_selects_every_query_and_finalization():
    report, runtime = execute(
        [
            [
                call(
                    "get_execution", {"execution_id": CASE["execution"]["execution_id"]}
                )
            ],
            [
                call("list_pending", {}),
                call("list_events", {}),
                call("list_classifications", {}),
            ],
            [call("final_answer", GOLD)],
        ]
    )
    assert report["failure"] is None
    assert report["output"] == GOLD
    assert report["finalization_count"] == 1
    assert report["generated_tokens"] == 60
    assert (
        score_tool_calls(
            CASE,
            ["get_execution", "list_pending", "list_events", "list_classifications"],
            report["tool_calls"],
        )["accuracy"]
        == 1
    )
    assert len(runtime.requests[0]["messages"]) == 2
    assert "pending_items" not in runtime.requests[0]["messages"][1]["content"]
    history = runtime.requests[-1]["messages"]
    assert len(history[-4]["tool_calls"]) == 3
    assert [m["role"] for m in history[-4:]] == ["assistant", "tool", "tool", "tool"]


def test_premature_native_finalization_cannot_claim_unretrieved_facts():
    report, _ = execute([[call("final_answer", GOLD)]])
    assert report["schema_valid"]
    assert report["failure"] == "unretrieved_evidence"
    assert report["output"] is None
    assert report["tool_calls"] == []


def test_native_agent_cannot_call_mutating_tools_and_denied_args_are_not_echoed():
    report, runtime = execute(
        [
            [call("delete_execution", {"execution_id": "outside-case"})],
            [call("final_answer", GOLD)],
        ]
    )
    assert report["failure"] == "unretrieved_evidence"
    assert report["tool_calls"] == [
        {"name": "unknown", "arguments": None, "outcome": "denied"}
    ]
    assert "outside-case" not in json.dumps(runtime.requests[-1])
    assert "delete_execution" not in json.dumps(runtime.requests[-1])


def test_native_loop_limit_preserves_extra_incorrect_call():
    frame = [call("get_execution", {"execution_id": CASE["execution"]["execution_id"]})]
    report, _ = execute([frame] * 7)
    assert report["failure"] == "tool_call_limit"
    assert len(report["tool_calls"]) == 7
    assert report["tool_calls"][-1]["outcome"] == "limit_exceeded"
    assert report["output"] is None


def test_native_finalization_is_not_batched_with_unseen_evidence():
    report, _ = execute(
        [
            [
                call(
                    "get_execution", {"execution_id": CASE["execution"]["execution_id"]}
                ),
                call("final_answer", GOLD),
            ]
        ]
    )
    assert report["failure"] == "mixed_finalization_and_tools"
    assert report["tool_calls"][0]["outcome"] == "denied"
    assert report["output"] is None


@pytest.mark.parametrize("calls", [[], [{"function": "invalid"}]])
def test_bad_native_frames_fail_closed(calls):
    report, _ = execute([calls])
    assert report["failure"] in {"missing_native_tool_call", "invalid_native_tool_call"}
    assert report["output"] is None


def test_native_finalization_rejects_wrong_case():
    wrong = copy.deepcopy(GOLD)
    wrong["case_id"] = "other"
    report, _ = execute([[call("final_answer", wrong)]])
    assert report["failure"] == "contract_or_runtime_failure"
    assert report["output"] is None


def test_native_chat_transport_does_not_persist_reasoning_or_prose(monkeypatch):
    c = runner.configuration(
        ROOT
        / "scripts/ai_reevaluation_configs/operational-instruct-native-development.json"
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return json.dumps(
                {
                    "model": c["model"],
                    "eval_count": 23,
                    "done_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "thinking": "private reasoning",
                        "content": "unvalidated prose",
                        "tool_calls": [
                            call("get_execution", {"execution_id": "synthetic"})
                        ],
                    },
                }
            ).encode()

    class Opener:
        def open(self, request, timeout):
            body = json.loads(request.data)
            assert request.full_url.endswith("/api/chat")
            assert "messages" in body and "tools" in body and "format" not in body
            assert body["think"] is False
            return Response()

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    runtime = runner.make_runtime(c)
    raw, count = runtime.generate(
        json.dumps({"messages": [], "tools": []}), model=c["model"]
    )
    assert count == 23
    assert runtime.response_metrics["eval_count"] == 23
    assert len(runtime.request_sha256) == 64
    assert "private reasoning" not in raw + str(runtime.__dict__)
    assert "unvalidated prose" not in raw


@pytest.mark.parametrize(
    "kind,endpoint",
    [
        ("quality", "http://127.0.0.1:11434/api/chat"),
        ("operational", "http://127.0.0.1:11434/api/generate"),
    ],
)
def test_native_configuration_requires_correct_poc_and_route(kind, endpoint):
    c = runner.configuration(
        ROOT
        / "scripts/ai_reevaluation_configs/operational-instruct-native-development.json"
    )
    c.update(kind=kind, endpoint=endpoint)
    with pytest.raises(PoCFoundationError, match="operational_chat_agent"):
        runner.validate_configuration(c)


def test_native_configuration_requires_model_tool_capability():
    c = runner.configuration(
        ROOT
        / "scripts/ai_reevaluation_configs/operational-instruct-native-development.json"
    )
    with pytest.raises(PoCFoundationError, match="native_tools_not_supported"):
        runner.freeze(
            c, metadata=lambda _: {"capabilities": ["completion"]}, identity=lambda: {}
        )


def test_structured_final_keeps_queries_model_selected_and_uses_no_final_tool():
    class StructuredRuntime(Runtime):
        def generate(self, prompt, *, model):
            request = json.loads(prompt)
            self.requests.append(request)
            if "format" in request:
                assert "tools" not in request
                return json.dumps({"content": json.dumps(GOLD), "tool_calls": []}), 30
            assert all(
                t["function"]["name"] != "final_answer" for t in request["tools"]
            )
            return json.dumps({"tool_calls": next(self.frames)}), 20

    runtime = StructuredRuntime(
        [
            [
                call(
                    "get_execution", {"execution_id": CASE["execution"]["execution_id"]}
                )
            ],
            [
                call("list_pending", {}),
                call("list_events", {}),
                call("list_classifications", {}),
            ],
            [],
        ]
    )
    report = collect_native_attempt(
        CASE, runtime, "fake", prompt_path=PROMPT, structured_final=True
    )
    assert report["failure"] is None
    assert report["output"] == GOLD
    assert report["generated_tokens"] == 90
    assert report["maximum_model_steps"] == 8
    assert report["steps"][-1]["phase"] == "structured_final"
    assert len(report["tool_calls"]) == 4
    assert len(runtime.requests) == 4


@pytest.mark.parametrize("content", ["not JSON", json.dumps({})])
def test_invalid_structured_final_is_not_repaired_or_retried(content):
    class StructuredRuntime(Runtime):
        def generate(self, prompt, *, model):
            request = json.loads(prompt)
            self.requests.append(request)
            if "format" in request:
                return json.dumps({"content": content, "tool_calls": []}), 10
            return json.dumps({"tool_calls": []}), 10

    runtime = StructuredRuntime([])
    report = collect_native_attempt(
        CASE, runtime, "fake", prompt_path=PROMPT, structured_final=True
    )
    assert report["failure"] in {"invalid_json", "contract_or_runtime_failure"}
    assert report["output"] is None
    assert len(runtime.requests) == 2
    assert report["tool_calls"] == []


def test_structured_output_cannot_compensate_for_missing_queries():
    class StructuredRuntime(Runtime):
        def generate(self, prompt, *, model):
            request = json.loads(prompt)
            self.requests.append(request)
            if "format" in request:
                return json.dumps({"content": json.dumps(GOLD), "tool_calls": []}), 10
            return json.dumps({"tool_calls": []}), 10

    report = collect_native_attempt(
        CASE, StructuredRuntime([]), "fake", prompt_path=PROMPT, structured_final=True
    )
    assert report["failure"] == "unretrieved_evidence"
    assert report["output"] is None
    assert report["tool_calls"] == []


def test_final_schema_encodes_question_invariant_without_forcing_status():
    from ai_reevaluation_native import final_schema
    from jsonschema import Draft202012Validator

    output = copy.deepcopy(GOLD)
    validator = Draft202012Validator(final_schema())
    assert validator.is_valid(output)
    output["status"] = "insufficient_evidence"
    output["open_questions"] = []
    assert not validator.is_valid(output)
    output["open_questions"] = ["Qual evidência falta?"]
    assert validator.is_valid(output)


def test_structured_phase_never_executes_an_unsolicited_tool():
    class StructuredRuntime(Runtime):
        def generate(self, prompt, *, model):
            if "format" in json.loads(prompt):
                return json.dumps(
                    {
                        "content": json.dumps(GOLD),
                        "tool_calls": [call("list_pending", {})],
                    }
                ), 10
            return json.dumps({"tool_calls": []}), 10

    report = collect_native_attempt(
        CASE, StructuredRuntime([]), "fake", prompt_path=PROMPT, structured_final=True
    )
    assert report["failure"] == "contract_or_runtime_failure"
    assert report["output"] is None
    assert report["tool_calls"] == [
        {"name": "list_pending", "arguments": None, "outcome": "denied"}
    ]


def test_model_can_select_final_read_batch_and_completion_without_prefilled_queries():
    class StagedRuntime(Runtime):
        def generate(self, prompt, *, model):
            request = json.loads(prompt)
            self.requests.append(request)
            if "format" in request:
                return json.dumps({"content": json.dumps(GOLD), "tool_calls": []}), 30
            names = {t["function"]["name"] for t in request["tools"]}
            assert "finish_collection" in names and "final_answer" not in names
            return json.dumps({"tool_calls": next(self.frames)}), 20

    runtime = StagedRuntime(
        [
            [
                call(
                    "get_execution", {"execution_id": CASE["execution"]["execution_id"]}
                )
            ],
            [
                call("list_pending", {}),
                call("list_events", {}),
                call("list_classifications", {}),
                call("finish_collection", {}),
            ],
        ]
    )
    report = collect_native_attempt(
        CASE,
        runtime,
        "fake",
        prompt_path=PROMPT,
        structured_final=True,
        completion_tool=True,
    )
    assert report["failure"] is None
    assert report["output"] == GOLD
    assert report["collection_completion_count"] == report["finalization_count"] == 1
    assert len(report["tool_calls"]) == 4
    assert len(runtime.requests) == 3
    assert (
        score_tool_calls(
            CASE,
            ["get_execution", "list_pending", "list_events", "list_classifications"],
            report["tool_calls"],
        )["accuracy"]
        == 1
    )


@pytest.mark.parametrize(
    "frames,expected",
    [
        (
            [[call("finish_collection", {"force": True})]],
            "invalid_collection_completion",
        ),
        (
            [[call("finish_collection", {}), call("finish_collection", {})]],
            "invalid_collection_completion",
        ),
        ([[]], "missing_native_completion"),
    ],
)
def test_staged_agent_must_provide_a_valid_completion_signal(frames, expected):
    report = collect_native_attempt(
        CASE,
        Runtime(frames),
        "fake",
        prompt_path=PROMPT,
        structured_final=True,
        completion_tool=True,
    )
    assert report["failure"] == expected
    assert report["output"] is None
    assert report["collection_completion_count"] == 0


def test_completion_signal_does_not_fetch_missing_data_or_bypass_grounding():
    class StagedRuntime(Runtime):
        def generate(self, prompt, *, model):
            request = json.loads(prompt)
            self.requests.append(request)
            if "format" in request:
                return json.dumps({"content": json.dumps(GOLD), "tool_calls": []}), 20
            return json.dumps({"tool_calls": [call("finish_collection", {})]}), 20

    runtime = StagedRuntime([])
    report = collect_native_attempt(
        CASE,
        runtime,
        "fake",
        prompt_path=PROMPT,
        structured_final=True,
        completion_tool=True,
    )
    assert report["failure"] == "unretrieved_evidence"
    assert report["output"] is None
    assert report["tool_calls"] == []
    assert len(runtime.requests) == 2


@pytest.mark.parametrize(
    "variant,role",
    [
        ("native", "instruct"),
        ("native-structured", "instruct"),
        ("native-staged", "instruct"),
        ("native-staged-guarded", "qwen3-8b"),
    ],
)
def test_configuration_runtime_and_executor_route_are_integrated(
    variant, role, tmp_path, monkeypatch
):
    c = runner.configuration(
        ROOT
        / "scripts/ai_reevaluation_configs"
        / f"operational-{role}-{variant}-development.json"
    )
    frames = [
        {
            "tool_calls": [
                call(
                    "get_execution", {"execution_id": CASE["execution"]["execution_id"]}
                )
            ]
        }
    ]
    reads = [
        call("list_pending", {}),
        call("list_events", {}),
        call("list_classifications", {}),
    ]
    if variant == "native":
        frames.extend(
            [{"tool_calls": reads}, {"tool_calls": [call("final_answer", GOLD)]}]
        )
    elif variant == "native-structured":
        frames.extend(
            [{"tool_calls": reads}, {"tool_calls": []}, {"content": json.dumps(GOLD)}]
        )
    else:
        frames.extend(
            [
                {"tool_calls": reads + [call("finish_collection", {})]},
                {"content": json.dumps(GOLD)},
            ]
        )
    seen = []

    class Response:
        def __init__(self, message):
            self.message = message

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return json.dumps(
                {
                    "model": c["model"],
                    "done_reason": "stop",
                    "eval_count": 20,
                    "message": self.message,
                }
            ).encode()

    class Opener:
        def open(self, request, timeout):
            assert request.full_url.endswith("/api/chat")
            seen.append(json.loads(request.data))
            return Response(frames.pop(0))

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    cases, _ = runner.corpus("operational")
    item = next(item for item in cases if item["case_id"] == CASE["case_id"])
    result = runner.execute_case(c, item, tmp_path, runner.make_runtime(c))
    assert result["report"]["failure"] is None
    assert result["report"]["output"] == GOLD
    assert result["tool_score"]["accuracy"] == 1
    assert result["report"]["architecture"] == c["architecture"]
    assert result["report"]["context_contract_guard_enabled"] == c.get(
        "context_contract_guard", False
    )
    assert not frames
    assert all(request["model"] == c["model"] for request in seen)


def test_context_guard_uses_only_execution_metadata_already_retrieved():
    from ai_reevaluation_native import structured_finish

    case = op.load_case(ROOT / "data/synthetic/ai-operational-v3/OP3-D04-input.json")
    gold = json.loads(
        (ROOT / "data/synthetic/ai-operational-v3/OP3-D04-gold.json").read_text()
    )
    registry = op.ToolRegistry(case)
    registry.call("get_execution", {"execution_id": case["execution"]["execution_id"]})

    class Runtime:
        def generate(self, prompt, *, model):
            schema = json.loads(prompt)["format"]
            assert schema["properties"]["status"] == {"const": "insufficient_evidence"}
            assert schema["properties"]["open_questions"]["minItems"] == 1
            return json.dumps({"content": json.dumps(gold), "tool_calls": []}), 10

    report = {
        "steps": [],
        "generated_tokens": 0,
        "finalization_count": 0,
        "failure": None,
    }
    structured_finish(case, registry, Runtime(), "fake", [], report, context_guard=True)
    assert report["output"] == gold
    assert report["context_contract_guidance_applied"]
    assert report["guidance_source_result_sha256"] == registry.calls[0]["result_sha256"]
    assert len(registry.calls) == 1


def test_context_guard_cannot_inspect_unretrieved_execution_or_fill_a_query():
    from ai_reevaluation_native import structured_finish

    case = op.load_case(ROOT / "data/synthetic/ai-operational-v3/OP3-D04-input.json")
    gold = json.loads(
        (ROOT / "data/synthetic/ai-operational-v3/OP3-D04-gold.json").read_text()
    )
    registry = op.ToolRegistry(case)

    class Runtime:
        def generate(self, prompt, *, model):
            assert "oneOf" in json.loads(prompt)["format"]
            return json.dumps({"content": json.dumps(gold), "tool_calls": []}), 10

    report = {
        "steps": [],
        "generated_tokens": 0,
        "finalization_count": 0,
        "failure": None,
    }
    structured_finish(case, registry, Runtime(), "fake", [], report, context_guard=True)
    assert report["failure"] == "unretrieved_evidence"
    assert not report["context_contract_guidance_applied"]
    assert registry.calls == []


def test_context_guard_does_not_force_status_for_cases_with_additional_data():
    from ai_reevaluation_native import structured_finish

    registry = op.ToolRegistry(CASE)
    registry.call("get_execution", {"execution_id": CASE["execution"]["execution_id"]})

    class Runtime:
        def generate(self, prompt, *, model):
            assert "oneOf" in json.loads(prompt)["format"]
            return json.dumps({"content": json.dumps(GOLD), "tool_calls": []}), 10

    report = {
        "steps": [],
        "generated_tokens": 0,
        "finalization_count": 0,
        "failure": None,
    }
    structured_finish(CASE, registry, Runtime(), "fake", [], report, context_guard=True)
    assert not report["context_contract_guidance_applied"]
    assert report["failure"] == "unretrieved_evidence"
