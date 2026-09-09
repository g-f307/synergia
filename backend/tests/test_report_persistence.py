from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from app.authorization import ActorContext
from app.errors import ApiError
from app.reports import CreateReportRequest, PostgresReportRepository

pytestmark = pytest.mark.integration


def _actor(user_id, session_id, organization_id) -> ActorContext:
    return ActorContext(
        user_id=user_id,
        session_id=session_id,
        token_id=uuid4(),
        permissions={
            "report.generate": frozenset({organization_id}),
            "report.read": frozenset({organization_id}),
            "report.cancel": frozenset({organization_id}),
        },
        correlation_id=uuid4(),
    )


def _request(
    execution_id,
    organization_id,
    report_type="workorder_consolidated",
    *,
    reference_at="2026-09-08T12:00:00Z",
    filters=None,
):
    return CreateReportRequest.model_validate(
        {
            "report_type": report_type,
            "execution_id": execution_id,
            "organization_id": organization_id,
            "reference_at": reference_at,
            "filters": filters or {},
        }
    )


def test_reports_persist_snapshots_versions_scope_and_failures() -> None:
    database_url = os.environ["DATABASE_URL"]
    suffix = uuid4().hex
    user_id, session_id, organization_id = uuid4(), uuid4(), uuid4()
    other_organization_id = uuid4()
    complete_id = f"report-complete-{suffix[:10]}"
    partial_id = f"report-partial-{suffix[:10]}"
    active_id = f"report-active-{suffix[:10]}"

    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO synergia.identity_users (id, status, display_name)
            VALUES (%s, 'active', %s)
            """,
            (user_id, f"Report test {suffix[:10]}"),
        )
        connection.execute(
            """
            INSERT INTO synergia.identity_sessions (
                id, user_id, status, authenticated_at, last_seen_at,
                idle_expires_at, absolute_expires_at, authentication_method
            ) VALUES (%s, %s, 'active', now(), now(), now() + interval '1 hour',
                      now() + interval '2 hours', 'synthetic')
            """,
            (session_id, user_id),
        )
        connection.execute(
            """
            INSERT INTO synergia.iam_organizations (id, organization_code, display_name)
            VALUES (%s, %s, 'Report organization'),
                   (%s, %s, 'Hidden organization')
            """,
            (
                organization_id,
                f"report-{suffix[:10]}",
                other_organization_id,
                f"hidden-{suffix[:10]}",
            ),
        )
        connection.execute(
            """
            INSERT INTO synergia.executions (
                id, status, organization_id, source, actor_type, actor_identifier
            ) VALUES
                (%s, 'completed', %s, 'OWM', 'technical', 'report-test'),
                (%s, 'completed_with_errors', %s, 'OWM', 'technical', 'report-test'),
                (%s, 'validating', %s, 'OWM', 'technical', 'report-test')
            """,
            (
                complete_id,
                organization_id,
                partial_id,
                organization_id,
                active_id,
                organization_id,
            ),
        )
        for index, execution_id in enumerate((complete_id, partial_id)):
            source_id = connection.execute(
                """
                INSERT INTO synergia.source_files (
                    execution_id, file_name, content_hash
                )
                VALUES (%s, %s, %s) RETURNING id
                """,
                (execution_id, f"{execution_id}.json", str(index + 1) * 64),
            ).fetchone()[0]
            quantities = (
                (None, None, "consolidated", "2026-08-31T10:00:00Z"),
                (0, 0, "consolidated", "2026-09-02T10:00:00Z"),
                (12, 8, "failed", "2026-09-03T10:00:00Z"),
            )
            workorder_ids = []
            for quantity_index, (
                planned,
                produced,
                processing_status,
                updated_at,
            ) in enumerate(quantities):
                workorder_ids.append(
                    connection.execute(
                        """
                        INSERT INTO synergia.workorders (
                            workorder_number, execution_id, source_file_id,
                            processing_status, planned_quantity, produced_quantity,
                            updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                        """,
                        (
                            f"WO-{index}-{quantity_index}-{suffix[:8]}",
                            execution_id,
                            source_id,
                            processing_status,
                            planned,
                            produced,
                            updated_at,
                        ),
                    ).fetchone()[0]
                )
            lot_id = connection.execute(
                """
                INSERT INTO synergia.lots (
                    lot_number, workorder_id, execution_id, source_file_id
                ) VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (
                    f"LOT-{index}-{suffix[:8]}",
                    workorder_ids[2],
                    execution_id,
                    source_id,
                ),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO synergia.oqc_decisions (
                    workorder_id, lot_id, execution_id, source_file_id,
                    decision_state, reason, updated_at
                ) VALUES (%s, %s, %s, %s, 'pending', 'Synthetic reason',
                          '2026-09-03T10:00:00Z')
                """,
                (workorder_ids[2], lot_id, execution_id, source_id),
            )
            connection.execute(
                """
                INSERT INTO synergia.pending_items (
                    workorder_id, lot_id, execution_id, source_file_id,
                    category, reason, priority, priority_score, responsible_area
                ) VALUES (%s, %s, %s, %s, 'oqc_pending', 'Awaiting OQC',
                          'high', 80, 'Quality')
                """,
                (workorder_ids[2], lot_id, execution_id, source_id),
            )

    repository = PostgresReportRepository(database_url)
    actor = _actor(user_id, session_id, organization_id)
    complete = repository.generate(_request(complete_id, organization_id), actor)
    assert complete["completeness"] == "complete"
    assert [
        (row["planned_quantity"], row["produced_quantity"])
        for row in complete["data"]["workorders"]
    ] == [(None, None), (0, 0), (12, 8)]

    filtered = repository.generate(
        _request(
            complete_id,
            organization_id,
            reference_at="2026-09-02T12:00:00Z",
            filters={
                "date_from": "2026-09-01",
                "date_to": "2026-09-02",
                "state": "consolidated",
            },
        ),
        actor,
    )
    assert [
        (row["planned_quantity"], row["produced_quantity"])
        for row in filtered["data"]["workorders"]
    ] == [(0, 0)]

    second = repository.generate(
        _request(complete_id, organization_id), actor, complete["report_id"]
    )
    assert second["version"] == 2
    versions, total = repository.list_versions(
        complete["report_id"], frozenset({organization_id}), 1, 25
    )
    assert total == 2
    assert [row["version"] for row in versions] == [2, 1]
    assert (
        repository.get_version(
            complete["report_id"], 1, frozenset({other_organization_id})
        )
        is None
    )

    partial = repository.generate(_request(partial_id, organization_id), actor)
    assert partial["completeness"] == "partial"
    oqc = repository.generate(
        _request(
            partial_id,
            organization_id,
            "oqc_summary",
            filters={
                "date_from": "2026-09-01",
                "date_to": "2026-09-04",
                "state": "pending",
                "lot_number": f"LOT-1-{suffix[:8]}",
                "priority": "high",
            },
        ),
        actor,
    )
    assert oqc["data"]["items"][0]["priority"] == "high"
    assert oqc["data"]["items"][0]["organization_code"] is None

    with pytest.raises(ApiError) as active_error:
        repository.generate(_request(active_id, organization_id), actor)
    assert active_error.value.status_code == 409
    assert active_error.value.code == "execution_not_reportable"

    with pytest.raises(ApiError) as missing_error:
        repository.generate(_request(f"missing-{suffix[:10]}", organization_id), actor)
    assert missing_error.value.status_code == 404
    assert missing_error.value.code == "resource_not_found"

    catalog, catalog_total = repository.list_reports(
        frozenset({organization_id}),
        "workorder_consolidated",
        "succeeded",
        complete_id,
        1,
        2,
    )
    assert catalog_total >= 2
    assert len(catalog) == 2
    hidden_catalog, hidden_total = repository.list_reports(
        frozenset({other_organization_id}), None, None, None, 1, 25
    )
    assert hidden_catalog == []
    assert hidden_total == 0

    with psycopg.connect(database_url) as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                UPDATE synergia.report_versions
                SET filters = '{"changed": true}' WHERE id = %s
                """,
                (complete["version_id"],),
            )
        connection.rollback()

    failing = PostgresReportRepository(database_url)
    failing._workorder_data = lambda cursor, payload: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("synthetic failure")
    )
    with pytest.raises(ApiError) as failure:
        failing.generate(_request(complete_id, organization_id), actor)
    failed_report_id = failure.value.details["report_id"]
    with psycopg.connect(database_url, row_factory=psycopg.rows.dict_row) as connection:
        failed = connection.execute(
            """
            SELECT rv.state, rv.failure_code,
                   array_agg(re.event_type ORDER BY re.occurred_at, re.id) AS events
            FROM synergia.report_versions rv
            JOIN synergia.report_events re ON re.report_version_id = rv.id
            WHERE rv.report_id = %s GROUP BY rv.id
            """,
            (failed_report_id,),
        ).fetchone()
        assert failed["state"] == "failed"
        assert failed["failure_code"] == "generation_failed"
        assert failed["events"] == [
            "report.generation_started",
            "report.generation_failed",
        ]

        success_events = connection.execute(
            """
            SELECT array_agg(event_type ORDER BY occurred_at, id) AS events
            FROM synergia.report_events WHERE report_version_id = %s
            """,
            (complete["version_id"],),
        ).fetchone()["events"]
        assert success_events == [
            "report.generation_started",
            "report.generation_succeeded",
        ]

    pending_generation = repository._create_generation(  # noqa: SLF001
        _request(complete_id, organization_id), actor, None
    )
    cancelled = repository.cancel(
        pending_generation["report_id"],
        pending_generation["version"],
        actor,
        "Solicitação substituída por novo corte",
    )
    assert cancelled is not None
    assert cancelled["state"] == "cancelled"
    assert cancelled["cancellation_reason"] == "Solicitação substituída por novo corte"
    with pytest.raises(ApiError) as cancellation_conflict:
        repository.cancel(
            pending_generation["report_id"],
            pending_generation["version"],
            actor,
            "Segunda tentativa",
        )
    assert cancellation_conflict.value.status_code == 409

    consulted = repository.get_version(
        complete["report_id"], 1, frozenset({organization_id}), actor
    )
    assert consulted is not None
    with psycopg.connect(database_url) as connection:
        assert (
            connection.execute(
                """
            SELECT count(*) FROM synergia.report_events
            WHERE report_version_id = %s AND event_type = 'report.consulted'
            """,
                (complete["version_id"],),
            ).fetchone()[0]
            == 1
        )
