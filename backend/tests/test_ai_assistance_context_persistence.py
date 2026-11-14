from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.ai_assistance_context import (
    ExecutionContextBuilder,
    canonical_bytes,
    reference_id,
)
from app.ai_assistance_context_models import SECTIONS
from app.ai_assistance_context_reader import (
    COLLECTION_SQL,
    COUNTS_SQL,
    PostgresContextReader,
    PostgresContextSession,
)
from app.authorization import ActorContext
from app.errors import ApiError
from app.queries import PostgresQueryRepository

pytestmark = [pytest.mark.integration, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 14, tzinfo=UTC)


def actor(organization):
    return ActorContext(
        uuid4(),
        uuid4(),
        uuid4(),
        {"execution.read": frozenset({organization})},
        uuid4(),
    )


@pytest.fixture(scope="module")
def dataset():
    params = conninfo_to_dict(os.environ["DATABASE_URL"])
    params["dbname"] = "postgres"
    name = "synergia_context_" + uuid4().hex
    with psycopg.connect(make_conninfo(**params), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    params["dbname"] = name
    database = make_conninfo(**params)
    try:
        with psycopg.connect(database) as connection:
            for migration in sorted((ROOT / "database/migrations").glob("*.sql")):
                connection.execute(migration.read_text(), prepare=False)
            organizations = [uuid4(), uuid4()]
            executions = [uuid4(), uuid4()]
            for index, (organization, execution) in enumerate(
                zip(
                    organizations,
                    executions,
                    strict=True,
                )
            ):
                connection.execute(
                    """INSERT INTO synergia.iam_organizations
                    (id, organization_code, display_name) VALUES (%s,%s,'Synthetic')""",
                    (organization, f"context-{index}"),
                )
                connection.execute(
                    """INSERT INTO synergia.executions
                    (id,organization_id,status,source,started_at,finished_at)
                    VALUES (%s,%s,'completed_with_errors','OWM',%s,%s)""",
                    (str(execution), organization, NOW, NOW),
                )
                source = connection.execute(
                    """INSERT INTO synergia.source_files
                    (execution_id,file_name,content_hash,source,size_bytes)
                    VALUES (%s,'private-user@example.invalid.csv',%s,'OWM',10)
                    RETURNING id""",
                    (str(execution), f"{index + 1:064x}"),
                ).fetchone()[0]
                workorder = connection.execute(
                    """INSERT INTO synergia.workorders
                    (workorder_number,execution_id,source_file_id,processing_status)
                    VALUES ('synthetic',%s,%s,'consolidated') RETURNING id""",
                    (str(execution), source),
                ).fetchone()[0]
                connection.execute(
                    """INSERT INTO synergia.pipeline_issues
                    (execution_id,source_file_id,scope,severity,code,reason,created_at,details)
                    SELECT %s,%s,'record',
                    CASE WHEN n%%2=0 THEN 'error' ELSE 'warning' END,
                    'invalid_value','private@example.invalid /private token=secret',
                    %s,jsonb_build_object('original_values','private-secret')
                    FROM generate_series(1,1000) n""",
                    (str(execution), source, NOW),
                )
                connection.execute(
                    """INSERT INTO synergia.pending_items
                    (execution_id,source_file_id,workorder_id,category,reason,priority_score,
                     rule_id,created_at)
                    SELECT %s,%s,%s,'oqc_pending','private-secret', n%%100,
                    'oqc_pending',%s FROM generate_series(1,1000) n""",
                    (str(execution), source, workorder, NOW),
                )
                connection.execute(
                    """INSERT INTO synergia.classifications
                    (classification_id,execution_id,source_file_id,workorder_id,rule_id,
                    rule_catalog_version,state,entity_type,entity_id,justification,
                    data_quality,priority,priority_score,classified_at)
                    SELECT %s||'-'||lpad(n::text,4,'0'),%s,%s,%s,'oqc_pending',
                    '1.0.0','active','workorder','private-identifier','private-secret',
                    'partial','high',40,%s FROM generate_series(1,1000) n""",
                    (str(execution), str(execution), source, workorder, NOW),
                )
                connection.execute(
                    """INSERT INTO synergia.execution_state_transitions
                    (execution_id,from_state,to_state,actor_type,actor_identifier,reason,
                    state_version,occurred_at)
                    SELECT %s,'validating','completed_with_errors',
                    'technical','private-user@example.invalid','private-secret',n,%s
                    FROM generate_series(1,15) n""",
                    (str(execution), datetime.now(UTC)),
                )
        yield database, organizations, executions
    finally:
        params["dbname"] = "postgres"
        with psycopg.connect(make_conninfo(**params), autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid <> pg_backend_pid()",
                (name,),
            )
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


class RecordingConnection:
    def __init__(self, connection, statements):
        self.connection, self.statements = connection, statements

    def execute(self, query, parameters):
        self.statements.append((query, parameters))
        return self.connection.execute(query, parameters)


class RecordingReader(PostgresContextReader):
    def __init__(self, database):
        super().__init__(database)
        self.statements = []

    @contextmanager
    def snapshot(self):
        with super().snapshot() as session:
            yield PostgresContextSession(
                RecordingConnection(session.connection, self.statements)
            )


def test_large_fixture_uses_seven_bounded_selects_and_same_summary_counts(dataset):
    database, organizations, executions = dataset
    reader = RecordingReader(database)
    context = ExecutionContextBuilder(reader).build(
        actor(organizations[0]), executions[0]
    )
    assert len(reader.statements) == 7
    assert (
        context.counts.model_dump()
        == PostgresQueryRepository(database).get_execution(str(executions[0]))["counts"]
    )
    assert len(context.divergences) == 20
    assert all(item.severity == "error" for item in context.divergences)
    for query, parameters in reader.statements[1:]:
        assert "organization_id" in query and "execution_id" in query
        assert parameters == (str(executions[0]), organizations[0])
    serialized = canonical_bytes(context).decode()
    assert "private" not in serialized
    assert str(organizations[1]) not in serialized
    assert str(executions[1]) not in serialized


def test_database_orders_ties_and_bounds_each_collection(dataset):
    database, organizations, executions = dataset
    with PostgresContextReader(database).snapshot() as session:
        for section in SECTIONS:
            rows = session.items(section, str(executions[0]), organizations[0])
            assert len(rows) <= (11 if section == "state_history" else 21)
            if section == "divergences":
                assert all(row["severity"] == "error" for row in rows)
                assert [r["id"] for r in rows] == sorted(r["id"] for r in rows)
            if section == "pending_items":
                assert all(row["priority_score"] == 99 for row in rows[:10])
            if section == "state_history":
                assert rows[0]["state_version"] == 15


def test_cross_organization_queries_return_no_details(dataset):
    database, organizations, executions = dataset
    reader = RecordingReader(database)
    builder = ExecutionContextBuilder(reader)
    for execution in (executions[1], uuid4()):
        with pytest.raises(ApiError) as failure:
            builder.build(actor(organizations[0]), execution)
        assert failure.value.status_code == 404
    assert len(reader.statements) == 2
    with PostgresContextReader(database).snapshot() as session:
        assert session.counts(str(executions[1]), organizations[0]) is None
        for section in SECTIONS:
            assert session.items(section, str(executions[1]), organizations[0]) == []


@pytest.mark.parametrize(
    "status",
    ["validating", "reprocessing", "completed", "completed_with_errors", "failed"],
)
def test_database_eligibility_before_collection_queries(dataset, status):
    database, organizations, _ = dataset
    execution = uuid4()
    with psycopg.connect(database) as connection:
        connection.execute(
            """INSERT INTO synergia.executions (id,organization_id,status)
            VALUES (%s,%s,%s)""",
            (str(execution), organizations[0], status),
        )
    reader = RecordingReader(database)
    builder = ExecutionContextBuilder(reader)
    if status in {"validating", "reprocessing"}:
        with pytest.raises(ApiError) as failure:
            builder.build(actor(organizations[0]), execution)
        assert failure.value.status_code == 409
        assert len(reader.statements) == 1
    else:
        context = builder.build(actor(organizations[0]), execution)
        assert context.sufficiency == "insufficient"
        assert context.subject.source is None
        assert context.subject.finished_at is None
        assert len(reader.statements) == 7


def test_repeatable_read_snapshot_and_read_only_mode(dataset):
    database, organizations, executions = dataset
    reader = PostgresContextReader(database)
    with reader.snapshot() as session:
        assert (
            session.connection.execute("SHOW transaction_isolation").fetchone()[
                "transaction_isolation"
            ]
            == "repeatable read"
        )
        assert (
            session.connection.execute("SHOW transaction_read_only").fetchone()[
                "transaction_read_only"
            ]
            == "on"
        )
        session.subject(str(executions[0]), frozenset({organizations[0]}))
        with psycopg.connect(database) as concurrent:
            concurrent.execute(
                "UPDATE synergia.executions SET attempt=2 WHERE id=%s",
                (str(executions[0]),),
            )
        assert (
            session.subject(str(executions[0]), frozenset({organizations[0]}))[
                "attempt"
            ]
            == 1
        )
    with psycopg.connect(database) as connection:
        connection.execute(
            "UPDATE synergia.executions SET attempt=1 WHERE id=%s",
            (str(executions[0]),),
        )


def test_plans_for_largest_fixture_are_bounded_without_n_plus_one(dataset):
    database, organizations, executions = dataset
    with psycopg.connect(database) as connection:
        connection.execute("ANALYZE")
        plans = []
        for query in (COUNTS_SQL, *COLLECTION_SQL.values()):
            plan = connection.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query,
                (str(executions[0]), organizations[0]),
            ).fetchone()[0][0]
            plans.append(plan)
        assert len(plans) == 6
        assert all(plan["Plan"]["Actual Rows"] <= 21 for plan in plans)
        assert all(plan["Plan"]["Actual Loops"] == 1 for plan in plans)
        print(
            "CONTEXT_PLANS",
            [
                {
                    "section": section,
                    "rows": plan["Plan"]["Actual Rows"],
                    "execution_ms": plan["Execution Time"],
                }
                for section, plan in zip(("counts", *SECTIONS), plans, strict=True)
            ],
        )


def test_stable_hash_and_references_from_database(dataset):
    database, organizations, executions = dataset
    builder = ExecutionContextBuilder(PostgresContextReader(database))
    first = builder.build(actor(organizations[0]), executions[0], generated_at=NOW)
    second = builder.build(actor(organizations[0]), executions[0])
    assert canonical_bytes(first) == canonical_bytes(second)
    assert first.context_sha256 == second.context_sha256
    assert len(first.evidence_refs()) == sum(
        len(getattr(first, section)) for section in SECTIONS
    )
    with PostgresContextReader(database).snapshot() as session:
        native = session.items("divergences", str(executions[0]), organizations[0])[0][
            "id"
        ]
        assert first.divergences[0].ref_id == reference_id(
            "divergences", str(executions[0]), native
        )
