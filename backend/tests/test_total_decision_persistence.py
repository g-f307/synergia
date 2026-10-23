from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.business_rules import RULE_CATALOG
from app.execution import PIPELINE_VERSION
from app.imports import PostgresImportRepository
from app.pipeline import read_source, run_pipeline_batch
from app.queries import PostgresQueryRepository
from app.total_decision_report import build_report, compare_persisted

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.generate_total_decision_fixture import (  # noqa: E402
    SENSITIVE_SENTINEL,
    build_workbook,
)
from scripts.validate_total_decision import persisted_counts  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture
def execution(tmp_path):
    database = os.environ["DATABASE_URL"]
    execution_id = "td-" + uuid4().hex
    organization = uuid4()
    content = build_workbook(edge=True)
    path = tmp_path / "synthetic.xlsx"
    path.write_bytes(content)
    with psycopg.connect(database) as conn:
        conn.execute(
            "INSERT INTO synergia.iam_organizations "
            "(id, organization_code, display_name) VALUES (%s, %s, 'Synthetic')",
            (organization, execution_id),
        )
        conn.execute(
            "INSERT INTO synergia.executions "
            "(id, status, source, organization_id, actor_type, actor_identifier) "
            "VALUES (%s, 'pending', 'Total Decision', %s, 'technical', 'test')",
            (execution_id, organization),
        )
        file_id = conn.execute(
            "INSERT INTO synergia.source_files "
            "(execution_id, source, file_name, extension, content_hash, size_bytes) "
            "VALUES (%s, 'Total Decision', 'synthetic.xlsx', 'xlsx', %s, %s) "
            "RETURNING id",
            (execution_id, hashlib.sha256(content).hexdigest(), len(content)),
        ).fetchone()[0]
    yield database, execution_id, file_id, path
    with psycopg.connect(database) as conn:
        for table in (
            "pending_items",
            "holds",
            "oqc_decisions",
            "classifications",
            "rule_evaluations",
            "consolidated_field_provenance",
            "audit_events",
            "pipeline_issues",
            "pipeline_summaries",
            "normalized_records",
            "imported_records",
            "serials",
            "lots",
            "workorders",
            "organizations",
            "execution_idempotency",
            "source_files",
            "execution_state_transitions",
        ):
            conn.execute(
                f"DELETE FROM synergia.{table} WHERE execution_id = %s", (execution_id,)
            )
        conn.execute("DELETE FROM synergia.executions WHERE id = %s", (execution_id,))
        conn.execute(
            "UPDATE synergia.iam_organizations SET is_active = false, "
            "deactivated_at = now() WHERE id = %s",
            (organization,),
        )


def test_persistence_reconciles_and_preserves_logical_source_and_minimization(
    execution,
):
    database, execution_id, file_id, path = execution
    repository = PostgresImportRepository(database)
    tables, issues = read_source(path, ".xlsx", "Total Decision")
    result = run_pipeline_batch(
        execution_id=execution_id,
        inputs=[
            {
                "source": "Total Decision",
                "file_name": "synthetic.xlsx",
                "source_file_id": file_id,
                "tables": tables,
                "read_issues": issues,
            }
        ],
        repository=repository,
        classified_at="2026-01-10T00:00:00+00:00",
    )
    assert result["status"] == "completed_with_errors"
    report = build_report(path)
    counts = persisted_counts(database, execution_id, path)
    assert compare_persisted(report, counts)["matches"] is True
    assert counts["Sheet1"] == {"imported": 4, "normalized": 1}
    with psycopg.connect(database) as conn:
        records = conn.execute(
            "SELECT row_number, source_file_id, normalized_values, "
            "original_values, transformations FROM synergia.normalized_records "
            "WHERE execution_id = %s",
            (execution_id,),
        ).fetchall()
        assert records[0][:2] == (4, file_id)
        assert {record["source"] for record in result["normalized_records"]} == {
            "GMES/OQC"
        }
        assert SENSITIVE_SENTINEL not in json.dumps(records, default=str)
        imported = conn.execute(
            "SELECT original_values FROM synergia.imported_records "
            "WHERE execution_id = %s",
            (execution_id,),
        ).fetchall()
        assert SENSITIVE_SENTINEL not in json.dumps(imported, default=str)
        assert records[0][4][0]["adapter"] == "total_decision@1.0.0"
    with pytest.raises(RuntimeError, match="não está apta"):
        repository.commit_pipeline(execution_id, result)
    assert persisted_counts(database, execution_id, path) == counts
    queries = PostgresQueryRepository(database)
    retry_id = execution_id + "-retry"
    try:
        first = queries.request_reprocessing(
            execution_id,
            retry_id,
            "synthetic",
            "same-request",
            PIPELINE_VERSION,
            RULE_CATALOG["version"],
        )
        replay = queries.request_reprocessing(
            execution_id,
            retry_id + "-other",
            "synthetic",
            "same-request",
            PIPELINE_VERSION,
            RULE_CATALOG["version"],
        )
        assert first["execution_id"] == replay["execution_id"] == retry_id
        assert first["idempotent_replay"] is False
        assert replay["idempotent_replay"] is True
        assert persisted_counts(database, execution_id, path) == counts
        with psycopg.connect(database) as conn:
            assert conn.execute(
                "SELECT source, reprocessed_from_id FROM synergia.executions "
                "WHERE id = %s",
                (retry_id,),
            ).fetchone() == ("Total Decision", execution_id)
    finally:
        with psycopg.connect(database) as conn:
            for table in (
                "audit_events",
                "execution_idempotency",
                "execution_state_transitions",
                "executions",
            ):
                key = "id" if table == "executions" else "execution_id"
                conn.execute(
                    f"DELETE FROM synergia.{table} WHERE {key} = %s", (retry_id,)
                )
    with pytest.raises(ValueError, match="incompatível"):
        persisted_counts(database, "wrong-execution", path)
    path.write_bytes(build_workbook(rows=2))
    with pytest.raises(ValueError, match="incompatível"):
        persisted_counts(database, execution_id, path)
