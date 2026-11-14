from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.ai_assistance_contract import AiAssistanceResponse, contract_examples
from app.ai_assistance_repository import (
    AssistanceKey,
    AssistancePersistenceError,
    PostgresAiAssistanceRepository,
)

pytestmark = [pytest.mark.integration, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def database():
    params = conninfo_to_dict(os.environ["DATABASE_URL"])
    params["dbname"] = "postgres"
    name = "synergia_ai188_" + uuid4().hex
    with psycopg.connect(make_conninfo(**params), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    params["dbname"] = name
    url = make_conninfo(**params)
    try:
        with psycopg.connect(url) as connection:
            for migration in sorted((ROOT / "database/migrations").glob("*.sql")):
                connection.execute(migration.read_text(), prepare=False)
        yield url
    finally:
        params["dbname"] = "postgres"
        with psycopg.connect(make_conninfo(**params), autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture
def setup(database):
    org, other, execution, actor, correlation = (uuid4() for _ in range(5))
    with psycopg.connect(database) as connection:
        for identifier in (org, other):
            connection.execute(
                "INSERT INTO synergia.iam_organizations "
                "(id,organization_code,display_name) VALUES (%s,%s,'Synthetic')",
                (identifier, str(identifier)),
            )
        connection.execute(
            "INSERT INTO synergia.identity_users "
            "(id,display_name) VALUES (%s,'Synthetic')",
            (actor,),
        )
        connection.execute(
            "INSERT INTO synergia.executions "
            "(id,organization_id,status) VALUES (%s,%s,'completed')",
            (str(execution), org),
        )
    key = AssistanceKey(org, execution, "a" * 64, "b" * 64, None, None)
    return PostgresAiAssistanceRepository(database), key, other, actor, correlation


def result(key, assistance_id):
    example = contract_examples()["insufficient_evidence"]
    example.update(assistance_id=str(assistance_id), execution_id=str(key.execution_id))
    example["provenance"].update(
        context_hash=key.context_sha256, prompt_hash=key.prompt_sha256
    )
    example["created_at"] = datetime.now(UTC).isoformat()
    return AiAssistanceResponse.model_validate_json(__import__("json").dumps(example))


def test_reserve_finish_read_and_tenant_isolation(setup, database):
    repo, key, other, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    value = result(key, aid)
    repo.finish(
        key,
        aid,
        actor,
        correlation,
        value,
        evidence_refs=frozenset(),
        response_sha256=None,
        rejection_code=None,
        elapsed_ms=1,
    )
    assert repo.find(key, actor, correlation, evidence_refs=frozenset()) == value
    assert (
        repo.get(
            other, key.execution_id, aid, actor, correlation, evidence_refs=frozenset()
        )
        is None
    )
    assert (
        repo.get(
            key.organization_id,
            key.execution_id,
            aid,
            actor,
            correlation,
            evidence_refs=frozenset(),
        )
        == value
    )
    with psycopg.connect(database) as c:
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.ai_assistance_events "
                "WHERE assistance_id=%s",
                (aid,),
            ).fetchone()[0]
            == 4
        )
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.graylog_deliveries "
                "WHERE origin='ai_assistance_events' "
                "AND source_snapshot->>'resource_id'=%s",
                (str(aid),),
            ).fetchone()[0]
            == 4
        )


def test_concurrent_reservations_have_single_winner(setup):
    repo, key, _, actor, correlation = setup

    def reserve():
        try:
            return repo.reserve(key, actor, correlation)
        except AssistancePersistenceError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve(), range(2)))
    assert sum(value is not None for value in results) == 1


def test_integrity_error_and_expiration(setup, database):
    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    value = result(key, aid)
    repo.finish(
        key,
        aid,
        actor,
        correlation,
        value,
        evidence_refs=frozenset(),
        response_sha256=None,
        rejection_code=None,
        elapsed_ms=1,
    )
    with psycopg.connect(database) as c:
        c.execute(
            "UPDATE synergia.ai_assistances SET "
            "result=jsonb_set(result,'{summary}',to_jsonb('bad <html>'::text)) "
            "WHERE id=%s",
            (aid,),
        )
    with pytest.raises(AssistancePersistenceError, match="integrity_error"):
        repo.get(
            key.organization_id,
            key.execution_id,
            aid,
            actor,
            correlation,
            evidence_refs=frozenset(),
        )
    with psycopg.connect(database) as c:
        c.execute(
            "UPDATE synergia.ai_assistances "
            "SET created_at=clock_timestamp()-interval '2 days', "
            "expires_at=clock_timestamp()-interval '1 day' WHERE id=%s",
            (aid,),
        )
    assert repo.expire(actor, correlation, batch_size=1, dry_run=True)["count"] == 1
    assert repo.expire(actor, correlation, batch_size=1)["count"] == 1
    assert repo.expire(actor, correlation, batch_size=1)["count"] == 0


def test_abandoned_reservation_recovered_and_old_token_cannot_finish(setup, database):
    repo, key, _, actor, correlation = setup
    old = repo.reserve(key, actor, correlation)
    with psycopg.connect(database) as c:
        c.execute(
            "UPDATE synergia.ai_assistances "
            "SET reservation_until=clock_timestamp()-interval '1 second' WHERE id=%s",
            (old,),
        )
    new = repo.reserve(key, actor, correlation)
    assert old != new
    with pytest.raises(AssistancePersistenceError, match="reservation_missing"):
        repo.finish(
            key,
            old,
            actor,
            correlation,
            result(key, old),
            evidence_refs=frozenset(),
            response_sha256=None,
            rejection_code=None,
            elapsed_ms=1,
        )
    with psycopg.connect(database) as c:
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.ai_assistance_events "
                "WHERE assistance_id=%s AND action='expired'",
                (old,),
            ).fetchone()[0]
            == 1
        )


def test_failed_finish_rolls_back_result_and_event(setup, database):
    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    wrong = result(key, uuid4())
    with pytest.raises(AssistancePersistenceError, match="integrity_error"):
        repo.finish(
            key,
            aid,
            actor,
            correlation,
            wrong,
            evidence_refs=frozenset(),
            response_sha256=None,
            rejection_code=None,
            elapsed_ms=1,
        )
    with psycopg.connect(database) as c:
        assert c.execute(
            "SELECT state,result FROM synergia.ai_assistances WHERE id=%s", (aid,)
        ).fetchone() == ("processing", None)
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.ai_assistance_events "
                "WHERE assistance_id=%s",
                (aid,),
            ).fetchone()[0]
            == 1
        )


def test_rollback_migration_is_reversible(database):
    rollback = (
        ROOT / "database/rollbacks/0038_create_ai_assistance_persistence.down.sql"
    )
    with psycopg.connect(database) as c:
        c.execute(rollback.read_text(), prepare=False)
        assert (
            c.execute("SELECT to_regclass('synergia.ai_assistances')").fetchone()[0]
            is None
        )
        assert (
            c.execute("SELECT to_regclass('synergia.audit_event_catalog')").fetchone()[
                0
            ]
            is not None
        )
        forward = ROOT / "database/migrations/0038_create_ai_assistance_persistence.sql"
        c.execute(forward.read_text(), prepare=False)
        assert (
            c.execute(
                "SELECT to_regclass('synergia.ai_assistance_idempotency')"
            ).fetchone()[0]
            is not None
        )
        c.rollback()


def test_audit_projection_is_sanitized_and_exportable(setup, database):
    from psycopg.rows import dict_row

    from app.graylog import GraylogConfig, to_gelf

    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    config = GraylogConfig(
        endpoint="https://graylog.example.invalid/gelf",
        environment="test",
        application_version="1.0.0",
        enabled=True,
        authorization_confirmed=True,
        organization_ids=(key.organization_id,),
        headers={"Authorization": "synthetic"},
        include_actor_id=True,
        include_resource_id=True,
    )
    with psycopg.connect(database, row_factory=dict_row) as c:
        row = c.execute(
            "SELECT * FROM synergia.audit_event_catalog "
            "WHERE id LIKE 'ai_assistance:%%' AND resource_id=%s",
            (str(aid),),
        ).fetchone()
        snapshot = c.execute(
            "SELECT source_snapshot FROM synergia.graylog_deliveries "
            "WHERE event_key=%s",
            (row["id"],),
        ).fetchone()["source_snapshot"]
        assert snapshot["metadata"] == row["metadata"]
        assert snapshot["correlation_id"] == str(row["correlation_id"])
        gelf = to_gelf(row, config)
        assert gelf["_meta_context_sha256"] == key.context_sha256
        assert gelf["_meta_prompt_sha256"] == key.prompt_sha256
        assert gelf["_meta_execution_id"] == str(key.execution_id)
        assert gelf["_correlation_id"] == str(correlation)
        payload = __import__("json").dumps(gelf)
        assert "summary" not in payload and "response" not in payload


def test_integrity_failure_emits_audit(setup, database):
    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    repo.finish(
        key,
        aid,
        actor,
        correlation,
        result(key, aid),
        evidence_refs=frozenset(),
        response_sha256=None,
        rejection_code=None,
        elapsed_ms=1,
    )
    with psycopg.connect(database) as c:
        c.execute(
            "UPDATE synergia.ai_assistances SET result=jsonb_set(result, '{summary}', "
            "to_jsonb('A causa foi a falha'::text)) WHERE id=%s",
            (aid,),
        )
    with pytest.raises(AssistancePersistenceError, match="integrity_error"):
        repo.get(
            key.organization_id,
            key.execution_id,
            aid,
            actor,
            correlation,
            evidence_refs=frozenset(),
        )
    with psycopg.connect(database) as c:
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.ai_assistance_events "
                "WHERE assistance_id=%s AND action='integrity_error'",
                (aid,),
            ).fetchone()[0]
            == 1
        )


def test_index_plans_with_representative_fixture(setup, database):
    repo, key, _, actor, _ = setup
    with psycopg.connect(database) as c:
        c.execute(
            """INSERT INTO synergia.ai_assistances
            (id,organization_id,execution_id,requested_by,state,contract_version,
             context_sha256,prompt_sha256,expires_at,reservation_until)
            SELECT gen_random_uuid(),%s,%s,%s,'processing','1.0.0',
                   lpad(to_hex(n),64,'0'),%s,clock_timestamp()+interval '30 days',
                   clock_timestamp()+interval '2 minutes'
            FROM generate_series(1,3000) n""",
            (key.organization_id, str(key.execution_id), actor, key.prompt_sha256),
        )
        c.execute("ANALYZE synergia.ai_assistances")
        latest = "\n".join(
            row[0]
            for row in c.execute(
                """EXPLAIN SELECT a.* FROM synergia.ai_assistances a
                JOIN synergia.executions e ON e.id=a.execution_id
                WHERE a.organization_id=%s AND a.execution_id=%s
                  AND e.organization_id=%s AND a.context_sha256=%s
                  AND a.state <> 'processing' AND a.expires_at > clock_timestamp()
                ORDER BY a.created_at DESC, a.id DESC LIMIT 1""",
                (
                    key.organization_id,
                    str(key.execution_id),
                    key.organization_id,
                    f"{42:064x}",
                ),
            )
        )
        equivalent = "\n".join(
            row[0]
            for row in c.execute(
                """EXPLAIN SELECT a.* FROM synergia.ai_assistances a
                JOIN synergia.executions e ON e.id=a.execution_id
                WHERE a.organization_id=%s AND a.execution_id=%s
                AND e.organization_id=%s
                AND a.context_sha256=%s AND a.prompt_sha256=%s
                AND a.model_digest IS NOT DISTINCT FROM %s AND a.contract_version=%s
                AND a.state <> 'processing' AND a.expires_at > clock_timestamp()""",
                (
                    key.organization_id,
                    str(key.execution_id),
                    key.organization_id,
                    f"{42:064x}",
                    key.prompt_sha256,
                    key.model_digest,
                    key.contract_version,
                ),
            )
        )
        assert "ai_assistance_idempotency" in latest or "ai_assistance_latest" in latest
        assert "ai_assistance_idempotency" in equivalent
        print("\nlatest plan:\n" + latest + "\nidempotency plan:\n" + equivalent)
        c.rollback()


def test_latest_is_tenant_and_context_bound(setup):
    repo, key, other, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    value = result(key, aid)
    repo.finish(
        key,
        aid,
        actor,
        correlation,
        value,
        evidence_refs=frozenset(),
        response_sha256=None,
        rejection_code=None,
        elapsed_ms=1,
    )
    assert (
        repo.latest(
            key.organization_id,
            key.execution_id,
            key.context_sha256,
            actor,
            correlation,
            evidence_refs=frozenset(),
        )
        == value
    )
    assert (
        repo.latest(
            other,
            key.execution_id,
            key.context_sha256,
            actor,
            correlation,
            evidence_refs=frozenset(),
        )
        is None
    )
    assert (
        repo.latest(
            key.organization_id,
            key.execution_id,
            "c" * 64,
            actor,
            correlation,
            evidence_refs=frozenset(),
        )
        is None
    )


def test_model_result_and_rejection_are_persisted_without_raw_content(setup, database):
    import json
    from dataclasses import replace

    repo, base, _, actor, correlation = setup
    key = replace(base, model_name="model:local", model_digest="sha256:" + "d" * 64)
    aid = repo.reserve(key, actor, correlation)
    example = contract_examples()["ready"]
    example.update(assistance_id=str(aid), execution_id=str(key.execution_id))
    example["created_at"] = datetime.now(UTC).isoformat()
    example["provenance"].update(
        model=key.model_name,
        digest=key.model_digest,
        origin="model",
        context_hash=key.context_sha256,
        prompt_hash=key.prompt_sha256,
    )
    value = AiAssistanceResponse.model_validate_json(json.dumps(example))
    repo.complete(
        key,
        aid,
        actor,
        correlation,
        value,
        evidence_refs=frozenset(),
        response_sha256="f" * 64,
        rejection_code=None,
        elapsed_ms=1,
    )
    assert repo.find(key, actor, correlation, evidence_refs=frozenset()) == value
    with psycopg.connect(database) as c:
        row = c.execute(
            "SELECT to_jsonb(a) FROM synergia.ai_assistances a WHERE id=%s", (aid,)
        ).fetchone()[0]
        assert not {"prompt", "context", "raw_response"}.intersection(row)
        assert row["response_sha256"] == "f" * 64


def test_rejected_result_records_reason_and_audit(setup, database):
    import json

    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    example = contract_examples()["rejected"]
    example.update(assistance_id=str(aid), execution_id=str(key.execution_id))
    example["created_at"] = datetime.now(UTC).isoformat()
    example["provenance"].update(
        context_hash=key.context_sha256, prompt_hash=key.prompt_sha256
    )
    value = AiAssistanceResponse.model_validate_json(json.dumps(example))
    repo.reject(
        key,
        aid,
        actor,
        correlation,
        value,
        evidence_refs=frozenset(),
        response_sha256="f" * 64,
        rejection_code="invalid_json",
        elapsed_ms=1,
    )
    with psycopg.connect(database) as c:
        assert c.execute(
            "SELECT action,rejection_code FROM synergia.ai_assistance_events "
            "WHERE assistance_id=%s AND action='rejected'",
            (aid,),
        ).fetchone() == ("rejected", "invalid_json")


def test_cross_tenant_reservation_never_writes(setup, database):
    from dataclasses import replace

    repo, key, other, actor, correlation = setup
    with pytest.raises(AssistancePersistenceError, match="conflict_or_not_found"):
        repo.reserve(replace(key, organization_id=other), actor, correlation)
    with psycopg.connect(database) as c:
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.ai_assistances WHERE execution_id=%s",
                (str(key.execution_id),),
            ).fetchone()[0]
            == 0
        )


def test_changed_context_allows_new_reservation(setup):
    from dataclasses import replace

    repo, key, _, actor, correlation = setup
    first = repo.reserve(key, actor, correlation)
    second = repo.reserve(replace(key, context_sha256="c" * 64), actor, correlation)
    assert first != second


def test_cleanup_command_dry_run_reports_only_count_and_range(setup, database):
    import json
    import subprocess
    import sys

    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    with psycopg.connect(database) as c:
        c.execute(
            "UPDATE synergia.ai_assistances SET "
            "created_at=clock_timestamp()-interval '2 days', "
            "expires_at=clock_timestamp()-interval '1 day' WHERE id=%s",
            (aid,),
        )
    env = dict(os.environ, DATABASE_URL=database, PYTHONPATH=str(ROOT / "backend"))
    run = subprocess.run(
        [
            sys.executable,
            "scripts/expire_ai_assistance.py",
            "--actor-id",
            str(actor),
            "--batch-size",
            "1",
            "--dry-run",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    output = json.loads(run.stdout)
    assert set(output) == {"count", "oldest", "newest"}
    assert output["count"] == 1
    assert str(aid) not in run.stdout
    with psycopg.connect(database) as c:
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.ai_assistances WHERE id=%s", (aid,)
            ).fetchone()[0]
            == 1
        )
