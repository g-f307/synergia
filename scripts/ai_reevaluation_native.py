"""Native Ollama tool experiment: model selects every query and finalization."""

from __future__ import annotations

import hashlib
import json
import time
import tracemalloc
import urllib.error
import urllib.request
from pathlib import Path

import ai_operational_summary as op
from ai_poc_foundation import (
    LocalRuntimeTimeout,
    OllamaRuntime,
    PoCFoundationError,
    _NoRedirectHandler,
)
from jsonschema import Draft202012Validator

FINAL = "final_answer"
COMPLETE = "finish_collection"
NATIVE_ARCHITECTURES = frozenset(
    {
        "operational_native_tools",
        "operational_native_structured",
        "operational_native_staged",
    }
)


def native_tools(
    *, include_final: bool = True, completion_tool: bool = False
) -> list[dict]:
    descriptions = {
        "get_execution": "Ler execução autorizada, seu status e contagens de coleções.",
        "list_pending": (
            "Ler pendências do único caso autorizado. "
            "Sem filtros para recuperar todas."
        ),
        "list_classifications": (
            "Ler classificações do único caso autorizado. "
            "Sem filtros para recuperar todas."
        ),
        "list_events": (
            "Ler eventos do único caso autorizado. "
            "Sem filtros para recuperar todos."
        ),
    }
    result = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": descriptions[name],
                "parameters": contract,
            },
        }
        for name, contract in op.tool_contracts().items()
    ]
    if completion_tool:
        result.append(
            {
                "type": "function",
                "function": {
                    "name": COMPLETE,
                    "description": (
                        "Indicar que não serão necessárias novas consultas "
                        "após o lote atual. A resposta consultiva será "
                        "solicitada em outra fase. Não lê nem altera dados."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                },
            }
        )
    if not include_final:
        return result
    result.append(
        {
            "type": "function",
            "function": {
                "name": FINAL,
                "description": (
                    "Finalizar com resposta consultiva, somente após recuperar "
                    "as evidências necessárias. Não grava nem altera dados."
                ),
                "parameters": json.loads(op.SCHEMA.read_text(encoding="utf-8")),
            },
        }
    )
    return result


class NativeToolsRuntime(OllamaRuntime):
    supports_structured_final = False

    def generate(self, prompt: str, *, model: str) -> tuple[str, int]:
        self.request_sha256 = None
        self.response_metrics = {}
        self.response_done_reason = None
        frame = json.loads(prompt)
        final_request = self.supports_structured_final and set(frame) == {
            "messages",
            "format",
        }
        if (
            set(frame) != {"messages", "tools"} and not final_request
        ) or not isinstance(frame.get("messages"), list):
            raise PoCFoundationError("invalid_native_request")
        body = json.dumps(
            {
                "model": model,
                **frame,
                "stream": False,
                "options": self.options,
                "think": self.think,
                "keep_alive": self.keep_alive,
            }
        ).encode()
        self.request_sha256 = hashlib.sha256(body).hexdigest()
        request = urllib.request.Request(
            self.config.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), _NoRedirectHandler()
            )
            with opener.open(request, timeout=self.config.timeout_seconds) as response:
                payload = json.load(response)
        except TimeoutError as exc:
            raise LocalRuntimeTimeout("native_runtime_timeout") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise LocalRuntimeTimeout("native_runtime_timeout") from exc
            raise PoCFoundationError("native_runtime_unavailable") from exc
        except json.JSONDecodeError as exc:
            raise PoCFoundationError("native_runtime_invalid_json") from exc
        self.response_model = payload.get("model")
        self.response_metrics = {
            k: payload[k]
            for k in (
                "load_duration",
                "total_duration",
                "prompt_eval_count",
                "prompt_eval_duration",
                "eval_count",
                "eval_duration",
            )
            if type(payload.get(k)) is int and payload[k] >= 0
        }
        reason = payload.get("done_reason")
        self.response_done_reason = reason if reason in {"stop", "length"} else None
        message = payload.get("message")
        if not isinstance(message, dict) or not isinstance(
            message.get("tool_calls", []), list
        ):
            raise PoCFoundationError("invalid_native_message")
        # No private thinking or unvalidated prose is persisted in reports.
        output = {"tool_calls": message.get("tool_calls", [])}
        if final_request:
            output["content"] = message.get("content")
        return json.dumps(output, ensure_ascii=False), payload.get("eval_count") or 0


class NativeStructuredRuntime(NativeToolsRuntime):
    supports_structured_final = True


def final_schema() -> dict:
    """Encode the existing abstention/question invariant, not a case label."""
    branches = []
    for status in ("completed", "insufficient_evidence"):
        branch = json.loads(op.SCHEMA.read_text(encoding="utf-8"))
        for key in ("$schema", "$id"):
            branch.pop(key, None)
        branch["properties"]["status"] = {"const": status}
        if status == "insufficient_evidence":
            branch["properties"]["open_questions"]["minItems"] = 1
        branches.append(branch)
    return {"type": "object", "oneOf": branches}


def accept_final(case, registry, output, report):
    report["schema_valid"] = Draft202012Validator(
        json.loads(op.SCHEMA.read_text())
    ).is_valid(output)
    if report["schema_valid"]:
        report["diagnostic_projection"] = {
            "status": output["status"],
            "open_questions_count": len(output["open_questions"]),
            "finding_count": len(output["findings"]),
            "case_id_matches": output["case_id"] == case["case_id"],
        }
    op.validate_output(case, output)
    retrieved = {e for call in registry.calls for e in call.get("evidence_ids", [])}
    if "execution" not in retrieved or any(
        e not in retrieved
        for finding in output["findings"]
        for e in finding["evidence_ids"]
    ):
        report["failure"] = "unretrieved_evidence"
    else:
        report["output"] = output


def structured_finish(
    case, registry, runtime, model, messages, report, *, context_guard=False
):
    schema = final_schema()
    report["context_contract_guidance_applied"] = False
    execution_reads = [
        call
        for call in registry.calls
        if call["name"] == "get_execution"
        and call["outcome"] == "succeeded"
        and "execution" in call.get("evidence_ids", [])
    ]
    # Narrow only the existing validator invariant, using metadata already read
    # by the model. Never fetch a missing collection or consult a gold label.
    if context_guard and execution_reads:
        execution = case["execution"]
        if execution["lifecycle"] == "partial" and all(
            execution["counts"][name] == 0
            for name in ("pending_items", "classifications", "events")
        ):
            schema = schema["oneOf"][1]
            report["context_contract_guidance_applied"] = True
            report["guidance_source_result_sha256"] = execution_reads[-1][
                "result_sha256"
            ]
    request = messages + [
        {
            "role": "user",
            "content": (
                "Agora retorne somente o JSON do schema, "
                "usando apenas as evidências recuperadas. "
                "status descreve o diagnóstico, não o estado da execução. "
                "A falta de causa-raiz "
                "não impede descrever como completed uma falha documentada. "
                "partial sem evidência adicional exige "
                "insufficient_evidence e uma pergunta. "
                "Não invente fatos, causas ou referências, "
                "nem selecione classificações conflitantes. "
                "Schema: " + json.dumps(schema, ensure_ascii=False)
            ),
        }
    ]
    report["finalization_count"] += 1
    raw, tokens = runtime.generate(
        json.dumps({"messages": request, "format": schema}, ensure_ascii=False),
        model=model,
    )
    report["generated_tokens"] += tokens
    report["steps"].append(
        {
            "step": len(report["steps"]) + 1,
            "phase": "structured_final",
            "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "generated_tokens": tokens,
        }
    )
    frame = json.loads(raw)
    if frame.get("tool_calls"):
        for call in frame["tool_calls"]:
            function = call.get("function", {}) if isinstance(call, dict) else {}
            name = function.get("name")
            registry.calls.append(
                {
                    "name": name
                    if isinstance(name, str) and name in op.TOOL_SPECS
                    else "unknown",
                    "arguments": None,
                    "outcome": "denied",
                }
            )
        raise PoCFoundationError("unexpected_tools_in_finalization")
    content = frame.get("content")
    if not isinstance(content, str):
        raise PoCFoundationError("missing_structured_content")
    accept_final(case, registry, json.loads(content), report)


def collect_native_attempt(
    case: dict,
    runtime,
    model: str,
    *,
    prompt_path: Path,
    structured_final: bool = False,
    completion_tool: bool = False,
    context_guard: bool = False,
) -> dict:
    if completion_tool and not structured_final:
        raise PoCFoundationError("completion_requires_structured_final")
    if context_guard and not (completion_tool and structured_final):
        raise PoCFoundationError("context_guard_requires_staged_native_flow")
    registry = op.ToolRegistry(case)
    messages = [
        {"role": "system", "content": prompt_path.read_text(encoding="utf-8")},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "case_id": case["case_id"],
                    "execution_id": case["execution"]["execution_id"],
                }
            ),
        },
    ]
    report = {
        "output": None,
        "failure": None,
        "schema_valid": False,
        "generated_tokens": 0,
        "tool_calls": registry.calls,
        "steps": [],
        "tool_call_limit": op.MAX_TOOL_CALLS,
        "architecture": "operational_native_staged"
        if completion_tool
        else "operational_native_structured"
        if structured_final
        else "operational_native_tools",
        "maximum_model_steps": op.MAX_MODEL_STEPS + int(structured_final),
        "finalization_count": 0,
        "collection_completion_count": 0,
        "context_contract_guard_enabled": context_guard,
    }
    started = time.perf_counter()
    tracemalloc.start()
    try:
        for step in range(op.MAX_MODEL_STEPS):
            if time.perf_counter() - started >= op.MAX_ATTEMPT_SECONDS:
                report["failure"] = "attempt_time_limit"
                break
            raw, tokens = runtime.generate(
                json.dumps(
                    {
                        "messages": messages,
                        "tools": native_tools(
                            include_final=not structured_final,
                            completion_tool=completion_tool,
                        ),
                    },
                    ensure_ascii=False,
                ),
                model=model,
            )
            report["generated_tokens"] += tokens
            report["steps"].append(
                {
                    "step": step + 1,
                    "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                    "generated_tokens": tokens,
                }
            )
            frame = json.loads(raw)
            calls = frame.get("tool_calls")
            if (
                isinstance(calls, list)
                and not calls
                and structured_final
                and not completion_tool
            ):
                structured_finish(
                    case,
                    registry,
                    runtime,
                    model,
                    messages,
                    report,
                    context_guard=context_guard,
                )
                break
            if not isinstance(calls, list) or not calls:
                report["failure"] = (
                    "missing_native_completion"
                    if completion_tool
                    else "missing_native_tool_call"
                )
                break
            if any(
                not isinstance(call, dict) or not isinstance(call.get("function"), dict)
                for call in calls
            ):
                report["failure"] = "invalid_native_tool_call"
                break
            finals = [c for c in calls if c["function"].get("name") == FINAL]
            if finals and not structured_final:
                report["finalization_count"] += len(finals)
                if len(calls) != 1:
                    for call in calls:
                        name = call["function"].get("name")
                        if name != FINAL:
                            registry.calls.append(
                                {
                                    "name": name
                                    if isinstance(name, str) and name in op.TOOL_SPECS
                                    else "unknown",
                                    "arguments": None,
                                    "outcome": "denied",
                                }
                            )
                    report["failure"] = "mixed_finalization_and_tools"
                    break
                output = finals[0]["function"].get("arguments")
                accept_final(case, registry, output, report)
                break
            accepted_calls = []
            results = []
            denied = 0
            completion_requested = False
            for call in calls:
                function = call["function"]
                name, args = function.get("name"), function.get("arguments")
                if completion_tool and name == COMPLETE:
                    if args != {} or completion_requested:
                        report["failure"] = "invalid_collection_completion"
                        break
                    completion_requested = True
                    continue
                if len(registry.calls) >= op.MAX_TOOL_CALLS:
                    registry.calls.append(
                        {
                            "name": name
                            if isinstance(name, str) and name in op.TOOL_SPECS
                            else "unknown",
                            "arguments": None,
                            "outcome": "limit_exceeded",
                        }
                    )
                    report["failure"] = "tool_call_limit"
                    break
                try:
                    result = registry.call(name, args)
                except PoCFoundationError:
                    denied += 1
                    continue
                # Only successful allowlisted calls/arguments re-enter the conversation.
                safe = {
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                }
                accepted_calls.append(safe)
                results.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            if accepted_calls:
                messages.append(
                    {"role": "assistant", "content": "", "tool_calls": accepted_calls}
                )
                messages.extend(results)
            if denied:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"{denied} solicitações negadas; "
                            "nenhum dado dessas solicitações foi retornado."
                        ),
                    }
                )
            if report["failure"]:
                break
            if completion_requested:
                report["collection_completion_count"] += 1
                structured_finish(
                    case,
                    registry,
                    runtime,
                    model,
                    messages,
                    report,
                    context_guard=context_guard,
                )
                break
        else:
            report["failure"] = "iteration_limit"
    except json.JSONDecodeError:
        report["failure"] = "invalid_json"
    except (TimeoutError, LocalRuntimeTimeout):
        report["failure"] = "runtime_timeout"
    except PoCFoundationError:
        report["failure"] = "contract_or_runtime_failure"
    finally:
        report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        report["python_peak_memory_bytes"] = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    return report
