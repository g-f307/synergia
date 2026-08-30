from __future__ import annotations

# SQL fixtures stay aligned with the persisted contracts they exercise.
# ruff: noqa: E501
import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.execution import ExecutionState
from app.main import app
from app.queries import PostgresQueryRepository

pytestmark = pytest.mark.integration
EXECUTION_ID = "exec-monitoring-integration"
STATE_PREFIX = "exec-monitoring-state-"


@pytest.fixture(autouse=True)
def cleanup_monitoring_rows():
    yield
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for table in (
            "pending_items",
            "classifications",
            "pipeline_issues",
            "pipeline_summaries",
            "normalized_records",
            "workorders",
            "source_files",
            "file_inspections",
            "audit_events",
            "execution_state_transitions",
        ):
            connection.execute(
                f"DELETE FROM synergia.{table} WHERE execution_id=%s OR execution_id LIKE %s",
                (EXECUTION_ID, f"{STATE_PREFIX}%"),
            )
        connection.execute(
            "DELETE FROM synergia.executions WHERE id=%s OR id LIKE %s",
            (EXECUTION_ID, f"{STATE_PREFIX}%"),
        )


def _seed_monitoring(storage_root: Path) -> tuple[int, int]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            """INSERT INTO synergia.executions
               (id,status,source,actor_type,actor_identifier,finished_at)
               VALUES (%s,'completed_with_errors','OWM','technical','integration',now())""",
            (EXECUTION_ID,),
        )
        rejected_ids = []
        for index in range(3):
            rejected_ids.append(
                connection.execute(
                    """INSERT INTO synergia.file_inspections
                       (execution_id,source,original_file_name,internal_name,extension,
                        declared_media_type,detected_media_type,size_bytes,content_hash,
                        decision,reason_code,analyzed_at,retained_until)
                       VALUES (%s,'OWM','rejected.csv',%s,'csv','text/csv','text/csv',10,%s,
                               'rejected','active_content',now(),now()+interval '1 day')
                       RETURNING id""",
                    (EXECUTION_ID, f"{index + 1:048x}.csv", f"{index + 1:064x}"),
                ).fetchone()[0]
            )
        accepted_id = connection.execute(
            """INSERT INTO synergia.file_inspections
               (execution_id,source,original_file_name,internal_name,extension,
                declared_media_type,detected_media_type,size_bytes,content_hash,
                decision,reason_code,analyzed_at)
               VALUES (%s,'OWM','accepted.csv',%s,'csv','text/csv','text/csv',18,%s,
                       'accepted','accepted',now()) RETURNING id""",
            (EXECUTION_ID, "a" * 48 + ".csv", "a" * 64),
        ).fetchone()[0]
        storage_key = f"accepted/OWM/{EXECUTION_ID}/accepted.csv"
        source_id = connection.execute(
            """INSERT INTO synergia.source_files
               (execution_id,file_name,content_hash,media_type,size_bytes,extension,
                storage_key,source,inspection_id,detected_media_type)
               VALUES (%s,'accepted.csv',%s,'text/csv',18,'csv',%s,'OWM',%s,'text/csv')
               RETURNING id""",
            (EXECUTION_ID, "a" * 64, storage_key, accepted_id),
        ).fetchone()[0]
        workorder_id = connection.execute(
            """INSERT INTO synergia.workorders
               (workorder_number,execution_id,source_file_id,processing_status)
               VALUES ('WO-MON-1',%s,%s,'consolidated') RETURNING id""",
            (EXECUTION_ID, source_id),
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO synergia.pipeline_summaries
               (execution_id,source_file_id,rows_read,valid_records,rejected_records,
                normalized_records,error_count,warning_count)
               VALUES (%s,%s,3,2,1,2,1,1)""",
            (EXECUTION_ID, source_id),
        )
        for row_number in (2, 3):
            connection.execute(
                """INSERT INTO synergia.normalized_records
                   (execution_id,source_file_id,sheet_name,row_number,
                    normalized_values,original_values)
                   VALUES (%s,%s,'Data',%s,%s,%s)""",
                (
                    EXECUTION_ID,
                    source_id,
                    row_number,
                    Jsonb({"workorder_number": "WO-MON-1"}),
                    Jsonb({}),
                ),
            )
        for severity, code in (
            ("error", "invalid_value"),
            ("warning", "quantity_mismatch"),
        ):
            connection.execute(
                """INSERT INTO synergia.pipeline_issues
                   (execution_id,source_file_id,scope,severity,code,reason,details)
                   VALUES (%s,%s,'record',%s,%s,'synthetic',%s)""",
                (
                    EXECUTION_ID,
                    source_id,
                    severity,
                    code,
                    Jsonb({"workorder_number": "WO-MON-1"}),
                ),
            )
        for index in range(2):
            classification_id = f"class-monitoring-{index}"
            connection.execute(
                """INSERT INTO synergia.classifications
                   (classification_id,execution_id,workorder_id,source_file_id,rule_id,
                    rule_catalog_version,state,entity_type,entity_id,justification,
                    data_quality,priority,priority_score,classified_at,evidence)
                   VALUES (%s,%s,%s,%s,'oqc_pending','1.0.0','active','workorder',
                           'WO-MON-1','synthetic','complete','high',80,now()+%s*interval '1 second','{}')""",
                (classification_id, EXECUTION_ID, workorder_id, source_id, index),
            )
            connection.execute(
                """INSERT INTO synergia.pending_items
                   (workorder_id,execution_id,source_file_id,category,reason,classification_id,
                    rule_id,rule_catalog_version,priority,priority_score,responsible_area,evidence,
                    created_at,updated_at)
                   VALUES (%s,%s,%s,'oqc_pending','synthetic',%s,'oqc_pending','1.0.0',
                           'high',80,'Qualidade','{}',now()+%s*interval '1 second',now())""",
                (workorder_id, EXECUTION_ID, source_id, classification_id, index),
            )
    target = storage_root / storage_key
    target.parent.mkdir(parents=True)
    target.write_text("workorder_number\n", encoding="utf-8")
    assert accepted_id != source_id
    return source_id, accepted_id


def test_postgres_monitoring_counts_states_pagination_and_safe_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_id, inspection_id = _seed_monitoring(tmp_path)
    monkeypatch.setenv("IMPORT_STORAGE_DIR", str(tmp_path))
    repository = PostgresQueryRepository(os.environ["DATABASE_URL"])
    detail = repository.get_execution(EXECUTION_ID)
    assert detail["lifecycle"] == "partial"
    assert detail["counts"] == {
        "files": 1,
        "rows_read": 3,
        "valid_records": 2,
        "rejected_records": 1,
        "normalized_records": 2,
        "workorders": 1,
        "lots": 0,
        "serials": 0,
        "classifications": 2,
        "pending_items": 2,
        "errors": 1,
        "warnings": 1,
    }
    with TestClient(app) as client:
        for resource in ("classifications", "pending-items", "evidences"):
            page = client.get(
                f"/executions/{EXECUTION_ID}/{resource}?page=1&page_size=1&sort=newest"
            ).json()
            assert page["pagination"]["page_size"] == 1
            assert page["pagination"]["total"] >= 1
            assert len(page["items"]) == 1
        allowed = client.get(
            f"/executions/{EXECUTION_ID}/evidences/{source_id}/download"
        )
        assert allowed.status_code == 200
        assert allowed.content == b"workorder_number\n"
        internal_alias = client.get(
            f"/executions/{EXECUTION_ID}/evidences/{inspection_id}/download"
        )
        assert internal_alias.status_code == 404
        assert internal_alias.json()["error"]["code"] == "evidence_not_found"
        assert str(tmp_path) not in internal_alias.text


def test_all_official_states_have_a_coherent_public_lifecycle() -> None:
    expected = {
        "completed": {"completed", "duplicate"},
        "partial": {"completed_with_errors"},
        "failed": {"validation_failed", "failed", "cancelled"},
        "active": {
            "pending",
            "validating",
            "normalizing",
            "consolidating",
            "applying_rules",
            "reprocessing",
        },
    }
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        for state in ExecutionState:
            connection.execute(
                "INSERT INTO synergia.executions (id,status) VALUES (%s,%s)",
                (f"{STATE_PREFIX}{state.value}", state.value),
            )
    repository = PostgresQueryRepository(os.environ["DATABASE_URL"])
    observed = {key: set() for key in expected}
    for state in ExecutionState:
        detail = repository.get_execution(f"{STATE_PREFIX}{state.value}")
        observed[detail["lifecycle"]].add(state.value)
    assert observed == expected
