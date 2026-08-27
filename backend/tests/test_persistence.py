import os

import psycopg
import pytest

pytestmark = pytest.mark.integration


def test_creates_all_operational_entities() -> None:
    expected_tables = {
        "audit_events",
        "executions",
        "holds",
        "lots",
        "oqc_decisions",
        "organizations",
        "pending_items",
        "serials",
        "source_files",
        "workorders",
    }
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'synergia';
                """
            )
            assert {row[0] for row in cursor.fetchall()} == expected_tables


def test_persists_traceable_partial_release_and_reprocessing() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO synergia.executions (id, status)
                VALUES ('exec-001', 'completed'), ('exec-002', 'running');
                """
            )
            cursor.execute(
                """
                UPDATE synergia.executions
                SET reprocessed_from_id = 'exec-001', attempt = 2
                WHERE id = 'exec-002';
                """
            )
            cursor.execute(
                """
                INSERT INTO synergia.source_files
                    (execution_id, file_name, content_hash)
                VALUES ('exec-002', 'WO Status.xlsx', %s)
                RETURNING id;
                """,
                ("a" * 64,),
            )
            source_file_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO synergia.workorders (
                    workorder_number, execution_id, source_file_id,
                    planned_quantity, received_quantity, released_quantity,
                    pending_quantity, retained_quantity, partially_released
                ) VALUES ('00001234', 'exec-002', %s, 10, 10, 6, 3, 1, true)
                RETURNING id;
                """,
                (source_file_id,),
            )
            workorder_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO synergia.lots
                    (lot_number, workorder_id, execution_id, source_file_id)
                VALUES ('LOT-0001', %s, 'exec-002', %s)
                RETURNING id;
                """,
                (workorder_id, source_file_id),
            )
            lot_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO synergia.serials (
                    serial_number, container_number, workorder_id, lot_id,
                    execution_id, source_file_id
                ) VALUES ('SER-0001', '0000456', %s, %s, 'exec-002', %s)
                RETURNING id;
                """,
                (workorder_id, lot_id, source_file_id),
            )
            serial_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO synergia.pending_items (
                    workorder_id, serial_id, execution_id, source_file_id,
                    category, reason
                ) VALUES (%s, %s, 'exec-002', %s, 'release', NULL);
                """,
                (workorder_id, serial_id, source_file_id),
            )
            cursor.execute(
                """
                INSERT INTO synergia.holds (
                    workorder_id, serial_id, execution_id, source_file_id,
                    reason
                ) VALUES (%s, %s, 'exec-002', %s, NULL);
                """,
                (workorder_id, serial_id, source_file_id),
            )
            cursor.execute(
                """
                SELECT w.workorder_number, l.lot_number, s.serial_number,
                       s.container_number, w.partially_released,
                       e.reprocessed_from_id
                FROM synergia.serials s
                JOIN synergia.workorders w ON w.id = s.workorder_id
                JOIN synergia.lots l ON l.id = s.lot_id
                JOIN synergia.executions e ON e.id = s.execution_id
                WHERE s.id = %s;
                """,
                (serial_id,),
            )
            assert cursor.fetchone() == (
                "00001234",
                "LOT-0001",
                "SER-0001",
                "0000456",
                True,
                "exec-001",
            )
        connection.rollback()
