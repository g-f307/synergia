"""Reproduce the issue 187 local model check using only synthetic fixtures."""

import hashlib
import json
import os
from pathlib import Path

from app.ai_assistance_config import AiAssistanceConfig
from app.ai_assistance_context import canonical_bytes
from app.ai_assistance_context_models import ExecutionAssistanceContext
from app.ai_assistance_generator import AiAssistanceGenerator
from app.ai_assistance_provider import LocalAiModelProvider


def main():
    fixture = Path("backend/tests/fixtures/ai_context_1_0_0_complete.json")
    context = ExecutionAssistanceContext.model_validate_json(fixture.read_bytes())
    context = context.model_copy(
        update={
            "pending_items": [],
            "classifications": [],
            "evidences": [],
            "state_history": [],
        }
    )
    context = context.model_copy(
        update={"context_sha256": hashlib.sha256(canonical_bytes(context)).hexdigest()}
    )
    config = AiAssistanceConfig.from_environment(os.environ)
    result = AiAssistanceGenerator(LocalAiModelProvider(config)).generate(context)
    evidence = {
        "context": context.model_dump(mode="json"),
        "result": {
            key: getattr(result, key)
            for key in (
                "state",
                "origin",
                "summary",
                "findings",
                "human_checks",
                "limitations",
                "rejection_code",
                "context_sha256",
                "prompt_sha256",
                "response_sha256",
                "schema_sha256",
                "model",
                "digest",
                "elapsed_ms",
            )
        },
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if result.state == "ready" and result.origin == "model" else 1


if __name__ == "__main__":
    raise SystemExit(main())
