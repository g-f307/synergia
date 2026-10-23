from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from app.imports import PostgresImportRepository
from app.pipeline import read_source, run_pipeline_batch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_wo_status_fixture import build_workbook  # noqa: E402

pytestmark = pytest.mark.integration
TABLES = (
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
)


@pytest.fixture
def seeded(tmp_path):
    database_url = os.environ["DATABASE_URL"]
    execution_id = f"exec-wo-status-{uuid4().hex[:10]}"
    organization_id = uuid4()
    content, expected = build_workbook(edge=True)
    path = tmp_path / "wo-status.xlsx"
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO synergia.iam_organizations "
            "(id, organization_code, display_name) VALUES (%s, %s, 'WO Status')",
            (organization_id, f"wos-{execution_id[-10:]}"),
        )
        connection.execute(
            "INSERT INTO synergia.executions "
            "(id, status, source, organization_id, actor_type, actor_identifier) "
            "VALUES (%s, 'pending', 'WO Status', %s, 'technical', 'wo-status-test')",
            (execution_id, organization_id),
        )
        source_file_id = connection.execute(
            "INSERT INTO synergia.source_files "
            "(execution_id, source, file_name, extension, content_hash, size_bytes) "
            "VALUES (%s, 'WO Status', 'wo-status.xlsx', 'xlsx', %s, %s) RETURNING id",
            (execution_id, digest, len(content)),
        ).fetchone()[0]
    yield database_url, execution_id, source_file_id, path, expected
    with psycopg.connect(database_url) as connection:
        for table in TABLES:
            connection.execute(
                f"DELETE FROM synergia.{table} WHERE execution_id = %s",
                (execution_id,),
            )
        connection.execute(
            "DELETE FROM synergia.executions WHERE id = %s", (execution_id,)
        )
        connection.execute(
            "UPDATE synergia.iam_organizations "
            "SET is_active = false, deactivated_at = now() WHERE id = %s",
            (organization_id,),
        )


def _run(seeded):
    database_url, execution_id, source_file_id, path, _ = seeded
    repository = PostgresImportRepository(database_url)
    tables, issues = read_source(path, ".xlsx", "WO Status")
    return repository, run_pipeline_batch(
        execution_id=execution_id,
        inputs=[
            {
                "file_name": "wo-status.xlsx",
                "source": "WO Status",
                "source_file_id": source_file_id,
                "tables": tables,
                "read_issues": issues,
            }
        ],
        repository=repository,
        classified_at="2026-08-28T12:00:00+00:00",
    )


def _counts(database_url: str, execution_id: str) -> dict[str, int]:
    with psycopg.connect(database_url) as connection:
        return {
            table: connection.execute(
                f"SELECT count(*) FROM synergia.{table} WHERE execution_id = %s",
                (execution_id,),
            ).fetchone()[0]
            for table in ("normalized_records", "imported_records", "workorders")
        }


def test_composite_workbook_persists_per_sheet_records_with_the_file_identity(
    seeded,
) -> None:
    database_url, execution_id, source_file_id, _, expected = seeded

    repository, result = _run(seeded)

    assert result["status"] == "completed_with_errors"
    assert repository.get(execution_id)["status"] == "completed_with_errors"
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            "SELECT sheet_name, count(*), count(DISTINCT source_file_id), "
            "min(source_file_id) FROM synergia.normalized_records "
            "WHERE execution_id = %s GROUP BY sheet_name ORDER BY sheet_name",
            (execution_id,),
        ).fetchall()
        provenance = connection.execute(
            "SELECT transformations -> 0 ->> 'adapter', "
            "transformations -> 0 ->> 'source_column' "
            "FROM synergia.normalized_records WHERE execution_id = %s "
            "AND sheet_name = 'NFP' ORDER BY row_number LIMIT 1",
            (execution_id,),
        ).fetchone()
    assert [row[0] for row in rows] == ["CTNR STATUS", "NFP", "OWM SN"]
    assert {row[2] for row in rows} == {1} and {row[3] for row in rows} == {
        source_file_id
    }
    by_sheet = {row[0]: row[1] for row in rows}
    assert by_sheet["NFP"] == (
        expected["NFP"]["emitted"] - expected["NFP"]["rejected_adapter"]
    )
    assert provenance == ("wo_status@1.0.0", "U:Plant")


def test_committing_the_same_result_twice_is_refused_without_duplicates(
    seeded,
) -> None:
    database_url, execution_id, _, _, _ = seeded
    repository, result = _run(seeded)
    first = _counts(database_url, execution_id)

    with pytest.raises(RuntimeError, match="não está apta"):
        repository.commit_pipeline(execution_id, result)

    assert _counts(database_url, execution_id) == first


def test_reconciliation_report_matches_the_persisted_execution(seeded) -> None:
    from scripts.validate_wo_status import _persisted_counts

    from app.wo_status_report import build_report, compare_persisted

    database_url, execution_id, _, path, _ = seeded
    _run(seeded)
    report = build_report(path)

    persisted = _persisted_counts(database_url, execution_id)

    assert compare_persisted(report, persisted) == {"matches": True, "differences": []}
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "DELETE FROM synergia.normalized_records WHERE execution_id = %s "
            "AND sheet_name = 'NFP' AND row_number = 4",
            (execution_id,),
        )
    comparison = compare_persisted(
        report, _persisted_counts(database_url, execution_id)
    )
    assert comparison["matches"] is False
    assert comparison["differences"][0]["sheet"] == "NFP"
    assert comparison["differences"][0]["kind"] == "normalized"
