from __future__ import annotations

import os

import psycopg
import pytest

from app.queries import PostgresQueryRepository

pytestmark = pytest.mark.integration


def test_queries_and_reprocessing_use_the_operational_model() -> None:
    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        execution_id = "exec-api-query"
        connection.execute(
            """
            INSERT INTO synergia.executions (
                id, status, source, actor_type, actor_identifier, finished_at
            ) VALUES (
                %s, 'completed', 'OWM', 'technical', 'synthetic-api', now()
            )
            """,
            (execution_id,),
        )
        source_file_id = connection.execute(
            """
            INSERT INTO synergia.source_files (
                execution_id, file_name, content_hash
            ) VALUES (%s, 'api-query.json', %s)
            RETURNING id
            """,
            (execution_id, "c" * 64),
        ).fetchone()[0]
        workorder_id = connection.execute(
            """
            INSERT INTO synergia.workorders (
                workorder_number, execution_id, source_file_id,
                processing_status, planned_quantity, produced_quantity,
                received_quantity, released_quantity, pending_quantity,
                retained_quantity, partially_released
            ) VALUES (
                'WO-API-001', %s, %s, 'consolidated', 10, 8, 8, 6, 2, 1, true
            ) RETURNING id
            """,
            (execution_id, source_file_id),
        ).fetchone()[0]
        lot_id = connection.execute(
            """
            INSERT INTO synergia.lots (
                lot_number, workorder_id, execution_id, source_file_id
            ) VALUES ('LOT-API-001', %s, %s, %s)
            RETURNING id
            """,
            (workorder_id, execution_id, source_file_id),
        ).fetchone()[0]
        serial_id = connection.execute(
            """
            INSERT INTO synergia.serials (
                serial_number, container_number, workorder_id, lot_id,
                execution_id, source_file_id
            ) VALUES ('SER-API-001', 'CONT-API-001', %s, %s, %s, %s)
            RETURNING id
            """,
            (workorder_id, lot_id, execution_id, source_file_id),
        ).fetchone()[0]
        pending_id = connection.execute(
            """
            INSERT INTO synergia.pending_items (
                workorder_id, lot_id, serial_id, execution_id, source_file_id,
                category, reason
            ) VALUES (%s, %s, %s, %s, %s, 'long_term_hold', 'Synthetic API')
            RETURNING id
            """,
            (workorder_id, lot_id, serial_id, execution_id, source_file_id),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO synergia.audit_events (
                execution_id, entity_type, entity_id, event_type, payload
            ) VALUES (%s, 'workorder', 'WO-API-001', 'consolidated', '{}')
            """,
            (execution_id,),
        )

    repository = PostgresQueryRepository(database_url)

    assert repository.get_execution(execution_id)["status"] == "completed"
    assert repository.get_workorder("WO-API-001")["lots"] == ["LOT-API-001"]
    assert repository.get_lot("LOT-API-001")["serials"] == ["SER-API-001"]
    assert repository.get_serial("SER-API-001")["container_number"] == ("CONT-API-001")
    pending, total = repository.list_pending(
        status_filter="open",
        category="long_term_hold",
        workorder_number="WO-API-001",
        execution_id=execution_id,
        page=1,
        page_size=10,
        sort="oldest",
    )
    assert total == 1
    assert pending[0]["id"] == pending_id
    assert pending[0]["priority"] == "critical"
    history, total = repository.list_history(
        execution_id=execution_id,
        entity_type="workorder",
        entity_id="WO-API-001",
        event_type="consolidated",
        page=1,
        page_size=10,
        sort="newest",
    )
    assert total == 1
    assert history[0]["payload"] == {}
    assert repository.get_consolidated("WO-API-001")["pending_items"] == pending
    assert repository.indicators()["workorders"]["partially_released"] == 1

    new_execution_id = "exec-api-query-reprocessed"
    reprocessed = repository.request_reprocessing(
        execution_id,
        new_execution_id,
        "integration-test",
        "request-1",
        "1.0.0",
        "1.0.0",
    )

    assert reprocessed["attempt"] == 2
    assert reprocessed["previous_execution_id"] == execution_id
    assert repository.get_execution(execution_id)["status"] == "completed"
    new_execution = repository.get_execution(new_execution_id)
    assert new_execution["status"] == "reprocessing"
    assert new_execution["reprocessed_from_execution_id"] == execution_id
    events, total = repository.list_history(
        execution_id=new_execution_id,
        entity_type="execution",
        entity_id=new_execution_id,
        event_type="reprocessing_requested",
        page=1,
        page_size=10,
        sort="newest",
    )
    assert total == 1
    assert events[0]["payload"]["previous_execution_id"] == execution_id
