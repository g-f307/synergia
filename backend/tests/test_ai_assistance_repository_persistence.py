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
        elapsed_ms=0,
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

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: reserve(), range(10)))
    assert sum(value is not None for value in results) == 1
    assert sum(value is None for value in results) == 9


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
        elapsed_ms=0,
    )
    with psycopg.connect(database) as c:
        c.execute(
            "UPDATE synergia.ai_assistances SET "
            "result=jsonb_set(result,'{provenance,origin}',to_jsonb('model'::text)) "
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
            elapsed_ms=0,
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


def test_explicit_recovery_preserves_results_and_live_reservations(setup, database):
    from dataclasses import replace

    repo, key, _, actor, correlation = setup
    old = repo.reserve(key, actor, correlation)
    live_key = replace(key, prompt_sha256="c" * 64)
    live = repo.reserve(live_key, actor, correlation)
    finished_key = replace(key, prompt_sha256="d" * 64)
    finished = repo.reserve(finished_key, actor, correlation)
    repo.finish(
        finished_key,
        finished,
        actor,
        correlation,
        result(finished_key, finished),
        evidence_refs=frozenset(),
        response_sha256=None,
        rejection_code=None,
        elapsed_ms=0,
    )
    with psycopg.connect(database) as connection:
        connection.execute(
            "UPDATE synergia.ai_assistances "
            "SET reservation_until=clock_timestamp()-interval '1 second' WHERE id=%s",
            (old,),
        )
    assert repo.recover_reservations(actor, correlation)["count"] == 1
    assert (
        repo.recover_reservations(actor, correlation, batch_size=1, dry_run=False)[
            "count"
        ]
        == 1
    )
    assert repo.recover_reservations(actor, correlation, dry_run=False)["count"] == 0
    with psycopg.connect(database) as connection:
        assert {
            row[0]
            for row in connection.execute(
                "SELECT id FROM synergia.ai_assistances WHERE id=ANY(%s)",
                ([old, live, finished],),
            )
        } == {live, finished}
        assert (
            connection.execute(
                "SELECT count(*) FROM synergia.ai_assistance_events "
                "WHERE assistance_id=%s AND action='expired'",
                (old,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM synergia.graylog_deliveries "
                "WHERE source_snapshot->>'resource_id'=%s "
                "AND source_snapshot->>'action'='ai.assistance.expired'",
                (str(old),),
            ).fetchone()[0]
            == 1
        )
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
            elapsed_ms=0,
        )
    assert repo.reserve(key, actor, correlation) != old


def test_recovery_skips_locked_and_refuses_missing_actor(setup, database):
    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    with psycopg.connect(database) as connection:
        connection.execute(
            "UPDATE synergia.ai_assistances "
            "SET reservation_until=clock_timestamp()-interval '1 second' WHERE id=%s",
            (aid,),
        )
    with pytest.raises(AssistancePersistenceError, match="actor_not_found"):
        repo.recover_reservations(uuid4(), correlation, dry_run=False)
    with psycopg.connect(database) as connection:
        connection.execute(
            "SELECT id FROM synergia.ai_assistances WHERE id=%s FOR UPDATE", (aid,)
        )
        assert (
            repo.recover_reservations(actor, correlation, dry_run=False)["count"] == 0
        )
    assert repo.recover_reservations(actor, correlation, dry_run=False)["count"] == 1


def test_recovery_cli_defaults_to_preview(setup, database):
    import json
    import subprocess
    import sys

    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    with psycopg.connect(database) as connection:
        connection.execute(
            "UPDATE synergia.ai_assistances "
            "SET reservation_until=clock_timestamp()-interval '1 second' WHERE id=%s",
            (aid,),
        )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "backend"), "DATABASE_URL": database}
    command = [
        sys.executable,
        str(ROOT / "scripts/recover_ai_assistance.py"),
        "--actor-id",
        str(actor),
        "--batch-size",
        "1",
    ]
    preview = subprocess.run(
        command, env=env, capture_output=True, text=True, check=True
    )
    assert set(json.loads(preview.stdout)) == {"count", "oldest", "newest"}
    assert json.loads(preview.stdout)["count"] == 1
    assert str(aid) not in preview.stdout
    assert repo.recover_reservations(actor, correlation)["count"] == 1
    applied = subprocess.run(
        [*command, "--apply"], env=env, capture_output=True, text=True, check=True
    )
    assert json.loads(applied.stdout)["count"] == 1
    assert repo.recover_reservations(actor, correlation)["count"] == 0


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
            elapsed_ms=0,
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


def test_mismatched_duration_is_not_persisted_or_audited(setup, database):
    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    with pytest.raises(AssistancePersistenceError, match="integrity_error"):
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
        assert c.execute(
            "SELECT state,result,elapsed_ms FROM synergia.ai_assistances WHERE id=%s",
            (aid,),
        ).fetchone() == ("processing", None, None)
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.ai_assistance_events "
                "WHERE assistance_id=%s",
                (aid,),
            ).fetchone()[0]
            == 1
        )
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.graylog_deliveries "
                "WHERE origin='ai_assistance_events' "
                "AND source_snapshot->>'resource_id'=%s",
                (str(aid),),
            ).fetchone()[0]
            == 1
        )


def test_missing_actor_rolls_back_finish_and_reads(setup, database):
    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    missing = uuid4()
    value = result(key, aid)
    options = dict(
        evidence_refs=frozenset(),
        response_sha256=None,
        rejection_code=None,
        elapsed_ms=0,
    )
    with pytest.raises(AssistancePersistenceError, match="actor_not_found"):
        repo.finish(key, aid, missing, correlation, value, **options)
    with psycopg.connect(database) as c:
        assert c.execute(
            "SELECT state,result FROM synergia.ai_assistances WHERE id=%s", (aid,)
        ).fetchone() == ("processing", None)
    repo.finish(key, aid, actor, correlation, value, **options)
    operations = (
        lambda: repo.find(key, missing, correlation, evidence_refs=frozenset()),
        lambda: repo.get(
            key.organization_id,
            key.execution_id,
            aid,
            missing,
            correlation,
            evidence_refs=frozenset(),
        ),
        lambda: repo.latest(
            key.organization_id,
            key.execution_id,
            key.context_sha256,
            missing,
            correlation,
            evidence_refs=frozenset(),
        ),
    )
    for operation in operations:
        with pytest.raises(AssistancePersistenceError, match="actor_not_found"):
            operation()
    with psycopg.connect(database) as c:
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.ai_assistance_events "
                "WHERE assistance_id=%s",
                (aid,),
            ).fetchone()[0]
            == 2
        )
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.graylog_deliveries "
                "WHERE origin='ai_assistance_events' "
                "AND source_snapshot->>'resource_id'=%s",
                (str(aid),),
            ).fetchone()[0]
            == 2
        )


def test_read_detects_duration_changed_after_completion(setup, database):
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
        elapsed_ms=0,
    )
    with psycopg.connect(database) as c:
        c.execute("UPDATE synergia.ai_assistances SET elapsed_ms=1 WHERE id=%s", (aid,))
    with pytest.raises(AssistancePersistenceError, match="integrity_error"):
        repo.find(key, actor, correlation, evidence_refs=frozenset())
    with psycopg.connect(database) as c:
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.ai_assistance_events "
                "WHERE assistance_id=%s AND action='integrity_error'",
                (aid,),
            ).fetchone()[0]
            == 1
        )


def test_cleanup_worker_rejects_missing_actor_without_deletion(
    setup, database, monkeypatch
):
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "expire_ai_assistance", ROOT / "scripts/expire_ai_assistance.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    main = module.main

    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    with psycopg.connect(database) as c:
        c.execute(
            "UPDATE synergia.ai_assistances SET "
            "created_at=clock_timestamp()-interval '2 days', "
            "expires_at=clock_timestamp()-interval '1 day' WHERE id=%s",
            (aid,),
        )
    monkeypatch.setenv("DATABASE_URL", database)
    monkeypatch.setattr(
        sys, "argv", ["expire_ai_assistance.py", "--actor-id", str(uuid4())]
    )
    with pytest.raises(AssistancePersistenceError, match="actor_not_found"):
        main()
    with psycopg.connect(database) as c:
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.ai_assistances WHERE id=%s", (aid,)
            ).fetchone()[0]
            == 1
        )
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
        c.execute(
            (
                ROOT
                / "database/rollbacks"
                / "0039_create_ai_assistance_rate_attempts.down.sql"
            ).read_text(),
            prepare=False,
        )
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
        c.execute(
            (
                ROOT / "database/migrations/0039_create_ai_assistance_rate_attempts.sql"
            ).read_text(),
            prepare=False,
        )
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
        elapsed_ms=0,
    )
    with psycopg.connect(database) as c:
        c.execute(
            "UPDATE synergia.ai_assistances SET result=jsonb_set(result, '{state}', "
            "to_jsonb('ready'::text)) WHERE id=%s",
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
    import json

    _, key, _, actor, _ = setup
    with psycopg.connect(database) as c:
        c.execute(
            """INSERT INTO synergia.ai_assistances
            (id,organization_id,execution_id,requested_by,state,origin,contract_version,
             model_name,model_digest,context_sha256,prompt_sha256,response_sha256,
             rejection_code,result,elapsed_ms,created_at,completed_at,expires_at,reservation_until)
            SELECT gen_random_uuid(),%s,%s,%s,
              CASE n%%4 WHEN 0 THEN 'processing' WHEN 1 THEN 'ready'
                  WHEN 2 THEN 'insufficient_evidence' ELSE 'rejected' END,
              CASE n%%4 WHEN 0 THEN NULL WHEN 1 THEN 'model' ELSE 'deterministic' END,
              '1.0.0', CASE WHEN n%%4=1 THEN 'model:local' ELSE NULL END,
              CASE WHEN n%%4=1 THEN 'sha256:' || repeat('d',64) ELSE NULL END,
              %s,lpad(to_hex(n),64,'0'),
              CASE WHEN n%%4=1 THEN repeat('f',64) ELSE NULL END,
              CASE WHEN n%%4=3 THEN 'invalid_json' ELSE NULL END,
              CASE WHEN n%%4=0 THEN NULL ELSE %s::jsonb END,
              CASE WHEN n%%4=0 THEN NULL ELSE 1 END,
              clock_timestamp()-interval '60 days' + n * interval '1 second',
              CASE WHEN n%%4=0 THEN NULL ELSE clock_timestamp()-interval '1 day' END,
              CASE WHEN n%%5=0 THEN clock_timestamp()-interval '1 hour'
                   ELSE clock_timestamp()+interval '30 days' END,
              CASE WHEN n%%4=0 THEN clock_timestamp()-interval '1 hour' ELSE NULL END
            FROM generate_series(1,3000) n""",
            (
                key.organization_id,
                str(key.execution_id),
                actor,
                key.context_sha256,
                json.dumps(contract_examples()["insufficient_evidence"]),
            ),
        )
        c.execute("ANALYZE synergia.ai_assistances")

        def explain(query, params):
            return "\n".join(row[0] for row in c.execute("EXPLAIN " + query, params))

        org, execution = key.organization_id, str(key.execution_id)
        latest = explain(
            """SELECT a.* FROM synergia.ai_assistances a
            JOIN synergia.executions e ON e.id=a.execution_id
            WHERE a.organization_id=%s AND a.execution_id=%s AND e.organization_id=%s
              AND a.context_sha256=%s AND a.state <> 'processing'
              AND a.expires_at > clock_timestamp()
            ORDER BY a.created_at DESC, a.id DESC LIMIT 1""",
            (org, execution, org, key.context_sha256),
        )
        equivalent = explain(
            """SELECT a.* FROM synergia.ai_assistances a
            JOIN synergia.executions e ON e.id=a.execution_id
            WHERE a.organization_id=%s AND a.execution_id=%s AND e.organization_id=%s
              AND a.context_sha256=%s AND a.prompt_sha256=%s
              AND a.model_digest IS NOT DISTINCT FROM %s AND a.contract_version=%s
              AND a.state <> 'processing' AND a.expires_at > clock_timestamp()""",
            (org, execution, org, key.context_sha256, f"{42:064x}", None, "1.0.0"),
        )
        get_plan = explain(
            """SELECT a.* FROM synergia.ai_assistances a
            JOIN synergia.executions e ON e.id=a.execution_id
            WHERE a.id=%s AND a.organization_id=%s AND a.execution_id=%s
              AND e.organization_id=%s AND a.state <> 'processing'
              AND a.expires_at > clock_timestamp()""",
            (uuid4(), org, execution, org),
        )
        expire_plan = explain(
            """DELETE FROM synergia.ai_assistances WHERE id IN
            (SELECT id FROM synergia.ai_assistances
             WHERE expires_at <= clock_timestamp()
             ORDER BY expires_at,id LIMIT %s FOR UPDATE SKIP LOCKED) RETURNING *""",
            (100,),
        )
        reserve_plan = explain(
            """DELETE FROM synergia.ai_assistances a
            USING synergia.executions e
            WHERE a.organization_id=%s AND a.execution_id=%s
              AND e.id=a.execution_id AND e.organization_id=a.organization_id
              AND a.context_sha256=%s AND a.prompt_sha256=%s
              AND a.model_digest IS NOT DISTINCT FROM %s AND a.contract_version=%s
              AND ((a.state='processing' AND a.reservation_until <= clock_timestamp())
                   OR a.expires_at <= clock_timestamp()) RETURNING a.*""",
            (org, execution, key.context_sha256, f"{42:064x}", None, "1.0.0"),
        )
        reservation_scan = explain(
            """SELECT id FROM synergia.ai_assistances
            WHERE state='processing' AND reservation_until <= clock_timestamp()
            ORDER BY reservation_until LIMIT 20""",
            (),
        )
        assert "ai_assistance_idempotency" in equivalent
        assert "ai_assistances_pkey" in get_plan
        assert "ai_assistance_expiry" in expire_plan
        assert "ai_assistance_idempotency" in reserve_plan
        assert "ai_assistance_latest" in latest or "ai_assistance_idempotency" in latest
        for label, plan in (
            ("latest", latest),
            ("find", equivalent),
            ("get", get_plan),
            ("expire", expire_plan),
            ("reserve", reserve_plan),
            ("reservation_monitor", reservation_scan),
        ):
            print(f"\n{label} plan:\n{plan}")
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
        elapsed_ms=0,
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
        elapsed_ms=0,
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
        elapsed_ms=0,
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


def test_read_revalidates_authorized_references(setup):
    import json
    from dataclasses import replace

    repo, base, _, actor, correlation = setup
    key = replace(base, model_name="model:local", model_digest="sha256:" + "d" * 64)
    aid = repo.reserve(key, actor, correlation)
    ref = "DIV-" + "1" * 32
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
    example["findings"] = [
        {
            "title": "Divergência registrada",
            "explanation": "Há um registro disponível para conferência.",
            "evidence_refs": [ref],
        }
    ]
    value = AiAssistanceResponse.model_validate_json(
        json.dumps(example), context={"evidence_refs": {ref}}
    )
    repo.complete(
        key,
        aid,
        actor,
        correlation,
        value,
        evidence_refs=frozenset({ref}),
        response_sha256="f" * 64,
        rejection_code=None,
        elapsed_ms=0,
    )
    with pytest.raises(AssistancePersistenceError, match="integrity_error"):
        repo.get(
            key.organization_id,
            key.execution_id,
            aid,
            actor,
            correlation,
            evidence_refs=frozenset({"DIV-" + "2" * 32}),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE synergia.ai_assistances SET context_sha256='bad' WHERE id=%s",
        "UPDATE synergia.ai_assistances SET state='ready' WHERE id=%s",
        "UPDATE synergia.ai_assistances SET elapsed_ms=-1 WHERE id=%s",
        "UPDATE synergia.ai_assistances SET rejection_code='free_text' WHERE id=%s",
    ],
)
def test_database_constraints_reject_invalid_metadata(setup, database, mutation):
    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    with psycopg.connect(database) as c:
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(mutation, (aid,))
        c.rollback()


def test_expire_multiple_batches_preserves_unexpired(setup, database):
    from dataclasses import replace

    repo, key, _, actor, correlation = setup
    while repo.expire(actor, correlation, batch_size=100)["count"]:
        pass
    ids = [
        repo.reserve(replace(key, context_sha256=f"{n:064x}"), actor, correlation)
        for n in range(1, 5)
    ]
    with psycopg.connect(database) as c:
        for index, aid in enumerate(ids[:3]):
            c.execute(
                "UPDATE synergia.ai_assistances SET "
                "created_at=clock_timestamp()-interval '5 days', "
                "expires_at=clock_timestamp()-(%s * interval '1 day') WHERE id=%s",
                (3 - index, aid),
            )
    assert repo.expire(actor, correlation, batch_size=2, dry_run=True)["count"] == 2
    assert repo.expire(actor, correlation, batch_size=2)["count"] == 2
    with psycopg.connect(database) as c:
        remaining = {
            row[0]
            for row in c.execute(
                "SELECT id FROM synergia.ai_assistances WHERE id=ANY(%s)", (ids,)
            )
        }
        assert remaining == {ids[2], ids[3]}
    assert repo.expire(actor, correlation, batch_size=2)["count"] == 1
    assert repo.expire(actor, correlation, batch_size=2)["count"] == 0
    with psycopg.connect(database) as c:
        assert c.execute(
            "SELECT id FROM synergia.ai_assistances WHERE id=ANY(%s)", (ids,)
        ).fetchall() == [(ids[3],)]
        assert (
            c.execute(
                "SELECT count(*) FROM synergia.ai_assistance_events "
                "WHERE action='expired' AND assistance_id=ANY(%s)",
                (ids,),
            ).fetchone()[0]
            == 3
        )


def test_raw_content_rejected_by_application_and_database(setup, database):
    import json

    repo, key, _, actor, correlation = setup
    aid = repo.reserve(key, actor, correlation)
    safe = result(key, aid)
    forged = safe.model_copy(update={"summary": "token=synthetic_secret_188"})
    with pytest.raises(AssistancePersistenceError, match="integrity_error"):
        repo.finish(
            key,
            aid,
            actor,
            correlation,
            forged,
            evidence_refs=frozenset(),
            response_sha256=None,
            rejection_code=None,
            elapsed_ms=0,
        )
    repo.finish(
        key,
        aid,
        actor,
        correlation,
        safe,
        evidence_refs=frozenset(),
        response_sha256=None,
        rejection_code=None,
        elapsed_ms=0,
    )
    attacks = [
        "result || jsonb_build_object('prompt', 'synthetic raw prompt')",
        "jsonb_set(result, '{provenance,raw_response}', to_jsonb('raw'::text))",
        "jsonb_set(result, '{provenance,model}', "
        "jsonb_build_object('prompt', 'synthetic raw prompt'))",
        "jsonb_set(result, '{created_at}', to_jsonb('synthetic raw prompt'::text))",
        "jsonb_set(result, '{summary}', to_jsonb('token=synthetic_secret_188'::text))",
    ]
    with psycopg.connect(database) as c:
        for attack in attacks:
            with pytest.raises(psycopg.errors.CheckViolation):
                with c.transaction():
                    c.execute(
                        "UPDATE synergia.ai_assistances SET result="
                        + attack
                        + " WHERE id=%s",
                        (aid,),
                    )
        rows = c.execute(
            "SELECT row_to_json(a) FROM synergia.ai_assistances a WHERE id=%s", (aid,)
        ).fetchone()[0]
        serialized = json.dumps(rows)
        assert "synthetic_secret_188" not in serialized
        assert "synthetic raw prompt" not in serialized
        columns = {
            row[0]
            for row in c.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='synergia' AND table_name='ai_assistances'"
            )
        }
        assert not {"prompt", "context", "raw_response", "provider_payload"} & columns


def test_rejects_mismatched_finding_type_before_writing(setup, database):
    import json
    from dataclasses import replace

    repo, base, _, actor, correlation = setup
    key = replace(base, model_name="model:local", model_digest="sha256:" + "d" * 64)
    aid = repo.reserve(key, actor, correlation)
    ref = "EVI-" + "1" * 32
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
    example["findings"] = [
        {
            "title": "Divergência registrada",
            "explanation": "Há um registro disponível para conferência.",
            "evidence_refs": [ref],
        }
    ]
    value = AiAssistanceResponse.model_validate_json(
        json.dumps(example), context={"evidence_refs": {ref}}
    )
    with pytest.raises(AssistancePersistenceError, match="integrity_error"):
        repo.complete(
            key,
            aid,
            actor,
            correlation,
            value,
            evidence_refs=frozenset({ref}),
            response_sha256="f" * 64,
            rejection_code=None,
            elapsed_ms=0,
        )
    with psycopg.connect(database) as c:
        assert (
            c.execute(
                "SELECT state FROM synergia.ai_assistances WHERE id=%s", (aid,)
            ).fetchone()[0]
            == "processing"
        )


@pytest.mark.parametrize("wo_number", ["WO-226-CTRL", "WO-TOKEN-01", "WO-SECRET-01"])
def test_triage_generation_persistence_and_readback(setup, wo_number):
    import json
    from dataclasses import replace

    from app.ai_assistance_context import ExecutionContextBuilder
    from app.ai_assistance_fallback import (
        deterministic_triage_findings,
        required_limitations,
    )
    from app.ai_assistance_generator import AiAssistanceGenerator
    from app.authorization import ActorContext
    from tests.test_ai_assistance_context import Reader

    repo, base, _, actor, correlation = setup
    reader = Reader(1)
    reader.row["execution_id"] = str(base.execution_id)
    reader.row["organization_id"] = base.organization_id
    reader.collections["divergences"][0]["workorder_number"] = wo_number
    reader.collections["pending_items"][0].update(
        rule_id="oqc_hold",
        status="open",
        priority_score=80,
        workorder_number=wo_number,
        responsible_area="Qualidade",
        priority="high",
        age_days=14,
        has_container=True,
    )
    ctx_actor = ActorContext(
        actor,
        uuid4(),
        uuid4(),
        {"execution.read": frozenset({base.organization_id})},
        correlation,
    )
    ctx = ExecutionContextBuilder(reader).build(ctx_actor, base.execution_id)
    findings = deterministic_triage_findings(ctx)

    class TriageProvider:
        model = "model:triage"
        digest = "sha256:" + "e" * 64

        def generate(self, system, prompt, schema):
            return json.dumps(
                {
                    "summary": (
                        f"A execução registra {ctx.counts.errors} erros, "
                        f"{ctx.counts.warnings} avisos e "
                        f"{ctx.counts.pending_items} pendências."
                    ),
                    "findings": findings,
                    "human_checks": [
                        "Conferência humana das referências disponíveis."
                    ],
                    "limitations": required_limitations(ctx),
                },
                ensure_ascii=False,
            ).encode("utf-8")

    generated = AiAssistanceGenerator(TriageProvider()).generate(ctx)
    assert generated.state == "ready"
    if wo_number == "WO-226-CTRL":
        assert any(wo_number in f["explanation"] for f in generated.findings)
    else:
        assert all(wo_number not in f["explanation"] for f in generated.findings)

    key = replace(
        base,
        context_sha256=ctx.context_sha256,
        prompt_sha256=generated.prompt_sha256,
        model_name=generated.model,
        model_digest=generated.digest,
    )
    aid = repo.reserve(key, actor, correlation)
    refs = ctx.evidence_refs()
    response = AiAssistanceResponse.model_validate_json(
        json.dumps(
            {
                "assistance_id": str(aid),
                "execution_id": str(key.execution_id),
                "state": generated.state,
                "summary": generated.summary,
                "findings": generated.findings,
                "human_checks": generated.human_checks,
                "limitations": generated.limitations,
                "provenance": {
                    "contract_version": key.contract_version,
                    "model": key.model_name,
                    "digest": key.model_digest,
                    "context_hash": key.context_sha256,
                    "prompt_hash": key.prompt_sha256,
                    "origin": generated.origin,
                    "timings": {
                        "context_ms": 0,
                        "generation_ms": generated.elapsed_ms,
                        "total_ms": generated.elapsed_ms,
                    },
                },
                "created_at": datetime.now(UTC).isoformat(),
            }
        ),
        context={"evidence_refs": refs},
    )
    saved = repo.finish(
        key,
        aid,
        actor,
        correlation,
        response,
        evidence_refs=refs,
        response_sha256=generated.response_sha256,
        rejection_code=None,
        elapsed_ms=generated.elapsed_ms,
    )
    loaded = repo.latest(
        key.organization_id,
        key.execution_id,
        ctx.context_sha256,
        actor,
        correlation,
        evidence_refs=refs,
    )
    assert loaded is not None
    assert loaded.assistance_id == saved.assistance_id
    assert [f.model_dump() for f in loaded.findings] == generated.findings


@pytest.mark.parametrize(
    "title,explanation,refs",
    [
        (
            "Divergência (error): invalid_value",
            (
                "Divergência de severidade error no escopo record "
                "com código invalid_value disponível para conferência."
            ),
            ["PEN-" + "1" * 32],
        ),
        (
            "Pendência aberta: oqc_hold",
            (
                "3 registros de pendência open na regra oqc_hold "
                "disponíveis para conferência."
            ),
            ["PEN-" + "1" * 32],
        ),
        (
            "Pendência aberta: oqc_hold",
            (
                "Registro de pendência cancelled na regra oqc_hold "
                "disponível para conferência."
            ),
            ["PEN-" + "1" * 32],
        ),
        (
            "Divergência (error): invalid_value",
            (
                "Divergência de severidade warning no escopo record "
                "com código invalid_value disponível para conferência."
            ),
            ["DIV-" + "1" * 32],
        ),
        (
            "Classificação ativa: oqc_hold",
            (
                "Classificação closed na regra oqc_pass com qualidade de dados "
                "complete disponível para conferência."
            ),
            ["CLA-" + "1" * 32],
        ),
    ],
)
def test_persistence_rejects_incoherent_triage_findings_on_write_and_read(
    setup, database, title, explanation, refs
):
    import json
    from dataclasses import replace

    repo, base, _, actor, correlation = setup
    key = replace(base, model_name="model:local", model_digest="sha256:" + "a" * 64)
    aid = repo.reserve(key, actor, correlation)
    bad = contract_examples()["ready"]
    bad.update(assistance_id=str(aid), execution_id=str(key.execution_id))
    bad["created_at"] = datetime.now(UTC).isoformat()
    bad["provenance"].update(
        model=key.model_name,
        digest=key.model_digest,
        origin="model",
        context_hash=key.context_sha256,
        prompt_hash=key.prompt_sha256,
    )
    bad["findings"] = [
        {"title": title, "explanation": explanation, "evidence_refs": refs}
    ]
    value = AiAssistanceResponse.model_validate_json(
        json.dumps(bad), context={"evidence_refs": set(refs)}
    )
    with pytest.raises(AssistancePersistenceError, match="integrity_error"):
        repo.complete(
            key,
            aid,
            actor,
            correlation,
            value,
            evidence_refs=frozenset(refs),
            response_sha256="b" * 64,
            rejection_code=None,
            elapsed_ms=0,
        )

    # Simulate an incoherent persisted document and verify readback rejects it.
    with psycopg.connect(database) as connection:
        connection.execute(
            """UPDATE synergia.ai_assistances
            SET state='ready', origin='model', result=%s::jsonb,
                completed_at=clock_timestamp(), reservation_until=NULL,
                elapsed_ms=0, response_sha256=%s
            WHERE id=%s""",
            (json.dumps(bad), "b" * 64, aid),
        )
    with pytest.raises(AssistancePersistenceError, match="integrity_error"):
        repo.get(
            key.organization_id,
            key.execution_id,
            aid,
            actor,
            correlation,
            evidence_refs=frozenset(refs),
        )


@pytest.mark.parametrize("ref_count", [1, 2, 3])
def test_persistence_accepts_coherent_triage_findings_for_one_to_three_refs(
    setup, ref_count
):
    import json
    from dataclasses import replace

    repo, base, _, actor, correlation = setup
    key = replace(base, model_name="model:local", model_digest="sha256:" + "c" * 64)
    aid = repo.reserve(key, actor, correlation)
    refs = [f"PEN-{i:032x}" for i in range(1, ref_count + 1)]
    explanation = (
        "Registro de pendência open na regra oqc_hold sob responsabilidade "
        "de Qualidade com aging de 10 dias disponível para conferência."
        if ref_count == 1
        else f"{ref_count} registros de pendência open na regra oqc_hold "
        "sob responsabilidade de Qualidade com aging máximo de 10 dias "
        "disponíveis para conferência."
    )
    doc = contract_examples()["ready"]
    doc.update(assistance_id=str(aid), execution_id=str(key.execution_id))
    doc["created_at"] = datetime.now(UTC).isoformat()
    doc["provenance"].update(
        model=key.model_name,
        digest=key.model_digest,
        origin="model",
        context_hash=key.context_sha256,
        prompt_hash=key.prompt_sha256,
    )
    doc["findings"] = [
        {
            "title": "Pendência aberta em Qualidade: oqc_hold",
            "explanation": explanation,
            "evidence_refs": refs,
        }
    ]
    value = AiAssistanceResponse.model_validate_json(
        json.dumps(doc), context={"evidence_refs": set(refs)}
    )
    saved = repo.finish(
        key,
        aid,
        actor,
        correlation,
        value,
        evidence_refs=frozenset(refs),
        response_sha256="d" * 64,
        rejection_code=None,
        elapsed_ms=0,
    )
    loaded = repo.get(
        key.organization_id,
        key.execution_id,
        aid,
        actor,
        correlation,
        evidence_refs=frozenset(refs),
    )
    assert loaded.assistance_id == saved.assistance_id
    assert loaded.findings[0].evidence_refs == refs
