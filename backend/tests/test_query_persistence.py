from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import psycopg
import pytest

from app.queries import PostgresQueryRepository

pytestmark = pytest.mark.integration


def test_operational_search_paginates_sorts_and_isolates_organizations() -> None:
    database_url = os.environ["DATABASE_URL"]
    suffix = uuid4().hex[:10]
    organization_a, organization_b = uuid4(), uuid4()
    executions = [f"exec-search-{letter}-{suffix}" for letter in "abc"]
    identifier = f"DUP-{suffix}"
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO synergia.iam_organizations (
                id, organization_code, display_name
            ) VALUES (%s, %s, 'Search A'), (%s, %s, 'Search B')
            """,
            (
                organization_a,
                f"search-a-{suffix}",
                organization_b,
                f"search-b-{suffix}",
            ),
        )
        for index, execution_id in enumerate(executions):
            organization_id = organization_a if index < 2 else organization_b
            connection.execute(
                """
                INSERT INTO synergia.executions (
                    id, status, source, actor_type, actor_identifier,
                    organization_id, updated_at
                ) VALUES (%s, 'completed', 'OWM', 'technical',
                          'search-test', %s, '2026-09-04T12:00:00Z')
                """,
                (execution_id, organization_id),
            )
            source_id = connection.execute(
                """
                INSERT INTO synergia.source_files (
                    execution_id, file_name, content_hash
                ) VALUES (%s, %s, %s) RETURNING id
                """,
                (execution_id, f"{execution_id}.json", f"{index + 1:x}" * 64),
            ).fetchone()[0]
            workorder_id = connection.execute(
                """
                INSERT INTO synergia.workorders (
                    workorder_number, execution_id, source_file_id,
                    processing_status, updated_at
                ) VALUES (%s, %s, %s, 'consolidated',
                          '2026-09-04T12:00:00Z') RETURNING id
                """,
                (identifier, execution_id, source_id),
            ).fetchone()[0]
            lot_id = connection.execute(
                """
                INSERT INTO synergia.lots (
                    lot_number, workorder_id, execution_id, source_file_id,
                    updated_at
                ) VALUES (%s, %s, %s, %s,
                          '2026-09-04T12:00:00Z') RETURNING id
                """,
                (identifier, workorder_id, execution_id, source_id),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO synergia.serials (
                    serial_number, workorder_id, lot_id, execution_id,
                    source_file_id, updated_at
                ) VALUES (%s, %s, %s, %s, %s,
                          '2026-09-04T12:00:00Z')
                """,
                (identifier, workorder_id, lot_id, execution_id, source_id),
            )

    repository = PostgresQueryRepository(database_url)
    try:
        for entity_type in ("workorder", "lot", "serial"):
            first_page, total = repository.search_operational(
                entity_type=entity_type,
                query=identifier,
                page=1,
                page_size=1,
                sort="updated_desc",
                organization_ids=frozenset({organization_a}),
            )
            second_page, _ = repository.search_operational(
                entity_type=entity_type,
                query=identifier,
                page=2,
                page_size=1,
                sort="updated_desc",
                organization_ids=frozenset({organization_a}),
            )
            ascending, _ = repository.search_operational(
                entity_type=entity_type,
                query=identifier,
                page=1,
                page_size=3,
                sort="identifier_asc",
                organization_ids=frozenset({organization_a}),
            )
            hidden, hidden_total = repository.search_operational(
                entity_type=entity_type,
                query=identifier,
                page=1,
                page_size=3,
                sort="updated_desc",
                organization_ids=frozenset({uuid4()}),
            )

            assert total == 2
            assert [first_page[0]["execution_id"], second_page[0]["execution_id"]] == [
                executions[1],
                executions[0],
            ]
            assert [row["execution_id"] for row in ascending] == executions[:2]
            assert hidden == []
            assert hidden_total == 0

        assert (
            repository.get_workorder(
                identifier, organization_ids=frozenset({organization_b})
            )["execution_id"]
            == executions[2]
        )
        assert (
            repository.get_lot(
                identifier, organization_ids=frozenset({organization_b})
            )["execution_id"]
            == executions[2]
        )
        assert (
            repository.get_serial(
                identifier, organization_ids=frozenset({organization_b})
            )["execution_id"]
            == executions[2]
        )
        assert (
            repository.get_workorder(identifier, organization_ids=frozenset({uuid4()}))
            is None
        )
        assert (
            repository.get_serial(identifier, organization_ids=frozenset({uuid4()}))
            is None
        )
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM synergia.audit_events WHERE execution_id = ANY(%s)",
                (executions,),
            )
            connection.execute(
                "DELETE FROM synergia.execution_state_transitions "
                "WHERE execution_id = ANY(%s)",
                (executions,),
            )
            connection.execute(
                "DELETE FROM synergia.serials WHERE execution_id = ANY(%s)",
                (executions,),
            )
            connection.execute(
                "DELETE FROM synergia.lots WHERE execution_id = ANY(%s)",
                (executions,),
            )
            connection.execute(
                "DELETE FROM synergia.workorders WHERE execution_id = ANY(%s)",
                (executions,),
            )
            connection.execute(
                "DELETE FROM synergia.source_files WHERE execution_id = ANY(%s)",
                (executions,),
            )
            connection.execute(
                "DELETE FROM synergia.executions WHERE id = ANY(%s)",
                (executions,),
            )
            connection.execute(
                """
                UPDATE synergia.iam_organizations
                SET is_active = false,
                    deactivated_at = now(),
                    updated_at = now()
                WHERE id = ANY(%s)
                """,
                ([organization_a, organization_b],),
            )


def test_indicator_filters_and_related_records_use_postgresql() -> None:
    database_url = os.environ["DATABASE_URL"]
    suffix = uuid4().hex[:10]
    organization_a, organization_b = uuid4(), uuid4()
    execution_a = f"exec-dashboard-a-{suffix}"
    execution_b = f"exec-dashboard-b-{suffix}"
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO synergia.iam_organizations (
                id, organization_code, display_name
            ) VALUES (%s, %s, %s), (%s, %s, %s)
            """,
            (
                organization_a,
                f"dashboard-a-{suffix}",
                "Dashboard A",
                organization_b,
                f"dashboard-b-{suffix}",
                "Dashboard B",
            ),
        )
        connection.execute(
            """
            INSERT INTO synergia.executions (
                id, status, source, actor_type, actor_identifier,
                organization_id, started_at, finished_at
            ) VALUES
                (%s, 'completed', 'OWM', 'technical', 'synthetic-dashboard',
                 %s, '2026-08-10T12:00:00Z', now()),
                (%s, 'completed', 'OWM', 'technical', 'synthetic-dashboard',
                 %s, '2026-07-10T12:00:00Z', now())
            """,
            (execution_a, organization_a, execution_b, organization_b),
        )
        source_file = connection.execute(
            """
            INSERT INTO synergia.source_files (
                execution_id, file_name, content_hash
            ) VALUES (%s, %s, %s) RETURNING id
            """,
            (execution_a, f"dashboard-{suffix}.json", "d" * 64),
        ).fetchone()[0]
        workorder = connection.execute(
            """
            INSERT INTO synergia.workorders (
                workorder_number, execution_id, source_file_id,
                processing_status, planned_quantity, produced_quantity,
                received_quantity, released_quantity, pending_quantity,
                retained_quantity, partially_released
            ) VALUES (
                %s, %s, %s, 'consolidated', 10, 8, 8, 6, 2, 1, true
            ) RETURNING id
            """,
            (f"WO-DASH-{suffix}", execution_a, source_file),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO synergia.pending_items (
                workorder_id, execution_id, source_file_id, category, reason
            ) VALUES (
                %s, %s, %s, 'long_term_hold', 'Synthetic dashboard'
            )
            """,
            (workorder, execution_a, source_file),
        )

    repository = PostgresQueryRepository(database_url)
    try:
        indicators = repository.indicators(
            frozenset({organization_a}), date(2026, 8, 1), date(2026, 8, 31)
        )
        assert indicators["executions"] == {"completed": 1}
        assert indicators["workorders"]["total"] == 1
        for entity in ("executions", "workorders", "pending-items"):
            rows, total = repository.indicator_related(
                entity,
                frozenset({organization_a}),
                date(2026, 8, 1),
                date(2026, 8, 31),
                1,
                1,
            )
            assert total == 1
            assert len(rows) == 1
        rows, total = repository.indicator_related(
            "executions",
            frozenset({organization_b}),
            date(2026, 8, 1),
            date(2026, 8, 31),
            1,
            25,
        )
        assert rows == []
        assert total == 0
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM synergia.audit_events WHERE execution_id IN (%s, %s)",
                (execution_a, execution_b),
            )
            connection.execute(
                "DELETE FROM synergia.execution_state_transitions "
                "WHERE execution_id IN (%s, %s)",
                (execution_a, execution_b),
            )
            connection.execute(
                "DELETE FROM synergia.pending_items WHERE execution_id = %s",
                (execution_a,),
            )
            connection.execute(
                "DELETE FROM synergia.workorders WHERE execution_id = %s",
                (execution_a,),
            )
            connection.execute(
                "DELETE FROM synergia.source_files WHERE execution_id = %s",
                (execution_a,),
            )
            connection.execute(
                "DELETE FROM synergia.executions WHERE id IN (%s, %s)",
                (execution_a, execution_b),
            )


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
                category, reason, rule_id, rule_catalog_version, priority,
                priority_score, responsible_area, evidence
            ) VALUES (
                %s, %s, %s, %s, %s, 'long_term_hold', 'Synthetic API',
                'long_term_hold', '1.0.0', 'critical', 90, 'Quality',
                '{"source":"synthetic"}'
            )
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
    for entity_type, identifier in (
        ("workorder", "WO-API-001"),
        ("lot", "LOT-API-001"),
        ("serial", "SER-API-001"),
    ):
        rows, total = repository.search_operational(
            entity_type=entity_type,
            query=identifier,
            page=1,
            page_size=1,
            sort="updated_desc",
        )
        assert total == 1
        assert rows[0]["identifier"] == identifier
        assert rows[0]["execution_id"] == execution_id
    pending, total = repository.list_pending(
        status_filter="open",
        category="long_term_hold",
        workorder_number="WO-API-001",
        execution_id=execution_id,
        lot_number="LOT-API-001",
        serial_number="SER-API-001",
        priority="critical",
        responsible_area="Quality",
        page=1,
        page_size=10,
        sort="oldest",
    )
    assert total == 1
    assert pending[0]["id"] == pending_id
    assert pending[0]["priority"] == "critical"
    detail = repository.get_pending(pending_id)
    assert detail["rule_catalog_version"] == "1.0.0"
    assert detail["evidence"] == {"source": "synthetic"}
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
