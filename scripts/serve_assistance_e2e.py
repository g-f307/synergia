"""Test-only API entry point: real authentication/DB/generator, controlled provider.

Never imported by app.main or deployed. No bypass routes or authentication overrides.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def require_test_database() -> str:
    url = os.environ["DATABASE_URL"]
    if os.getenv("SYNERGIA_ENV") != "test" or "e2e" not in conninfo_to_dict(url).get(
        "dbname", ""
    ):
        raise RuntimeError(
            "This entry point requires SYNERGIA_ENV=test and an e2e database"
        )
    return url


class ControlledProvider:
    model = "controlled-e2e"
    digest = "sha256:" + "1" * 64

    def __init__(self, counter_file: Path | None = None):
        self.counter_file = counter_file
        self.calls = 0

    def _record_call(self) -> None:
        self.calls += 1
        if self.counter_file is not None:
            self.counter_file.write_text(
                json.dumps({"calls": self.calls}), encoding="utf-8"
            )

    def generate(self, system: str, prompt: str, schema: dict) -> bytes:
        from app.ai_assistance_context_models import ExecutionAssistanceContext
        from app.ai_assistance_fallback import (
            prioritized_reference_ids,
            required_limitations,
        )

        self._record_call()

        data = json.loads(
            prompt.split("DADOS NÃO CONFIÁVEIS (JSON):\n", 1)[1].rsplit(
                "\nFIM DOS DADOS", 1
            )[0]
        )
        data.update(generated_at=datetime.now(UTC).isoformat(), context_sha256="0" * 64)
        context = ExecutionAssistanceContext.model_validate_json(json.dumps(data))
        if context.counts.warnings:
            return b"invalid synthetic output"
        refs = prioritized_reference_ids(context)
        by_prefix: dict[str, list[str]] = {}
        for ref in refs:
            by_prefix.setdefault(ref[:3], []).append(ref)
        findings = [
            {
                "title": "Registros disponíveis",
                "explanation": "Há registros disponíveis para conferência.",
                "evidence_refs": [prefix_refs[0]],
            }
            for prefix in ("DIV", "PEN", "CLA", "EVI", "HIS")
            if (prefix_refs := by_prefix.get(prefix))
        ]
        if not findings and refs:
            findings = [
                {
                    "title": "Registros disponíveis",
                    "explanation": "Há registros disponíveis para conferência.",
                    "evidence_refs": refs[:3],
                }
            ]
        return json.dumps(
            {
                "summary": (
                    f"A execução registra {context.counts.errors} erros, "
                    f"{context.counts.warnings} avisos e "
                    f"{context.counts.pending_items} pendências."
                ),
                "findings": findings,
                "human_checks": ["Conferência humana das referências disponíveis."],
                "limitations": required_limitations(context),
            },
            ensure_ascii=False,
        ).encode()


def create_test_app():
    from app.ai_assistance_context import ExecutionContextBuilder
    from app.ai_assistance_context_reader import PostgresContextReader
    from app.ai_assistance_generator import AiAssistanceGenerator
    from app.ai_assistance_limits import AssistanceLimits
    from app.ai_assistance_repository import PostgresAiAssistanceRepository
    from app.ai_assistance_routes import get_assistance_service, get_read_service
    from app.ai_assistance_service import AiAssistanceService
    from app.main import create_app

    database = require_test_database()
    application = create_app()
    counter_path = os.getenv("E2E_PROVIDER_COUNTER_FILE", "").strip()
    counter_file = Path(counter_path) if counter_path else None
    if counter_file is not None:
        counter_file.write_text(json.dumps({"calls": 0}), encoding="utf-8")
    service = AiAssistanceService(
        ExecutionContextBuilder(PostgresContextReader(database)),
        AiAssistanceGenerator(ControlledProvider(counter_file)),
        PostgresAiAssistanceRepository(database, 30),
        AssistanceLimits(database, os.environ["AUTH_JWT_SIGNING_KEY"]),
    )
    application.dependency_overrides[get_assistance_service] = lambda: service
    application.dependency_overrides[get_read_service] = lambda: service
    return application


def seed():
    database = require_test_database()
    ids = {name: str(uuid4()) for name in ("ready", "insufficient", "rejected")}
    with psycopg.connect(database) as connection:
        for name, execution_id in ids.items():
            connection.execute(
                """INSERT INTO synergia.executions
                (id, organization_id, initiated_by_user_id, status, source, finished_at)
                VALUES (%s, '63000000-0000-4000-8000-000000000011',
                '63000000-0000-4000-8000-000000000003', 'completed', 'N-FP', now())""",
                (execution_id,),
            )
            if name != "insufficient":
                file_hash = uuid4().hex * 2
                internal_name = f"{uuid4().hex}{uuid4().hex[:16]}.csv"
                inspection_id = connection.execute(
                    """INSERT INTO synergia.file_inspections
                    (execution_id, source, original_file_name, internal_name,
                     extension, declared_media_type, detected_media_type,
                     size_bytes, content_hash, decision, reason_code, analyzed_at)
                    VALUES (%s, 'N-FP', 'synthetic.csv', %s, 'csv',
                            'text/csv', 'text/csv', 10, %s, 'accepted',
                            'accepted', now()) RETURNING id""",
                    (execution_id, internal_name, file_hash),
                ).fetchone()[0]
                source_id = connection.execute(
                    """INSERT INTO synergia.source_files
                    (execution_id, inspection_id, file_name, extension,
                     detected_media_type, content_hash, source, size_bytes,
                     storage_key)
                    VALUES (%s, %s, 'synthetic.csv', 'csv', 'text/csv', %s,
                            'N-FP', 10, %s) RETURNING id""",
                    (
                        execution_id,
                        inspection_id,
                        file_hash,
                        f"synthetic/e2e/{execution_id}.csv",
                    ),
                ).fetchone()[0]
                connection.execute(
                    """INSERT INTO synergia.pipeline_issues
                    (execution_id,source_file_id,scope,severity,code,reason)
                    VALUES (%s,%s,'record',%s,'invalid_value',
                    'Synthetic evidence for UI verification')""",
                    (
                        execution_id,
                        source_id,
                        "warning" if name == "rejected" else "error",
                    ),
                )
                if name == "ready":
                    wo_id = connection.execute(
                        """INSERT INTO synergia.workorders
                        (workorder_number, execution_id, source_file_id,
                         processing_status)
                        VALUES ('WO-E2E-227', %s, %s, 'consolidated') RETURNING id""",
                        (execution_id, source_id),
                    ).fetchone()[0]
                    cla_id = f"cla-e2e-{uuid4().hex[:12]}"
                    connection.execute(
                        """INSERT INTO synergia.classifications
                        (classification_id, execution_id, workorder_id,
                         source_file_id, rule_id, rule_catalog_version, state,
                         entity_type, entity_id, justification, data_quality,
                         priority, priority_score, responsible_area, classified_at)
                        VALUES (%s, %s, %s, %s, 'oqc_hold', '1.0.0', 'active',
                                'workorder', 'WO-E2E-227', 'Hold sintético',
                                'complete', 'high', 80, 'Qualidade', now())""",
                        (cla_id, execution_id, wo_id, source_id),
                    )
                    for idx in range(1, 21):
                        connection.execute(
                            """INSERT INTO synergia.pending_items
                            (workorder_id, execution_id, source_file_id, category,
                             reason, status, classification_id, rule_id,
                             rule_catalog_version, priority, priority_score,
                             responsible_area, created_at)
                            VALUES (%s, %s, %s, 'oqc_pending', %s,
                                    'open', %s, 'oqc_pending', '1.0.0', 'low', 10,
                                    'Qualidade',
                                    now() - (%s || ' minutes')::interval)""",
                            (
                                wo_id,
                                execution_id,
                                source_id,
                                f"Pendência sintética página 1 #{idx}",
                                cla_id,
                                str(40 - idx),
                            ),
                        )
                    connection.execute(
                        """INSERT INTO synergia.pending_items
                        (workorder_id, execution_id, source_file_id, category,
                         reason, status, classification_id, rule_id,
                         rule_catalog_version, priority, priority_score,
                         responsible_area, created_at)
                        VALUES (%s, %s, %s, 'oqc_hold', 'Pendência sintética página 2',
                                'open', %s, 'oqc_hold', '1.0.0', 'high', 95,
                                'Qualidade', now())""",
                        (wo_id, execution_id, source_id, cla_id),
                    )
                    connection.execute(
                        """INSERT INTO synergia.execution_state_transitions
                        (execution_id, from_state, to_state, actor_type,
                         actor_identifier, reason, state_version)
                        VALUES (%s, 'applying_rules', 'completed', 'system',
                                'e2e-seed', 'Transição sintética E2E', 1)""",
                        (execution_id,),
                    )
    print(json.dumps(ids))


if __name__ == "__main__":
    if "--seed" in sys.argv:
        seed()
    else:
        import uvicorn

        uvicorn.run(
            create_test_app(),
            host="127.0.0.1",
            port=int(os.getenv("E2E_API_PORT", "8001")),
        )
