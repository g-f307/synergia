import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event
from uuid import uuid4

import psycopg
import pytest
from test_ai_assistance_generator import Fake, context, valid
from test_ai_assistance_service import Contexts

from app.ai_assistance_context import ExecutionContextBuilder, canonical_bytes
from app.ai_assistance_context_reader import PostgresContextReader
from app.ai_assistance_generator import AiAssistanceGenerator
from app.ai_assistance_limits import AssistanceLimits
from app.ai_assistance_provider import ProviderError
from app.ai_assistance_repository import AssistanceKey
from app.ai_assistance_service import AiAssistanceService
from app.authorization import ActorContext
from app.errors import ApiError

pytest_plugins = ("test_ai_assistance_repository_persistence",)
pytestmark = [pytest.mark.integration, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[2]


def fixture_service(setup, database, provider, name="insufficient"):
    repo, key, _, actor_id, correlation = setup
    ctx = context(name)
    subject = ctx.subject.model_copy(
        update={
            "execution_id": key.execution_id,
            "organization_id": key.organization_id,
        }
    )
    ctx = ctx.model_copy(update={"subject": subject})
    ctx = ctx.model_copy(
        update={"context_sha256": sha256(canonical_bytes(ctx)).hexdigest()}
    )
    actor = ActorContext(
        actor_id,
        uuid4(),
        uuid4(),
        {
            name: frozenset({key.organization_id})
            for name in (
                "execution.read",
                "ai.assistance.read",
                "ai.assistance.generate",
            )
        },
        correlation,
    )
    service = AiAssistanceService(
        Contexts(ctx),
        AiAssistanceGenerator(provider),
        repo,
        AssistanceLimits(database, "s" * 32),
    )
    return service, actor, ctx


def test_real_persistence_reuse_audit_and_tenant(setup, database):
    provider = Fake(b"never")
    service, actor, ctx = fixture_service(setup, database, provider)
    result = service.generate(actor, ctx.subject.execution_id)
    assert service.generate(actor, ctx.subject.execution_id) == result
    assert service.latest(actor, ctx.subject.execution_id) == result
    foreign = replace(
        actor, permissions={key: frozenset({uuid4()}) for key in actor.permissions}
    )
    with pytest.raises(ApiError) as exc:
        service.latest(foreign, ctx.subject.execution_id)
    assert exc.value.status_code == 404
    assert provider.calls == 0
    with psycopg.connect(database) as connection:
        actions = connection.execute(
            "SELECT action, correlation_id FROM synergia.ai_assistance_events "
            "WHERE assistance_id=%s ORDER BY occurred_at",
            (result.assistance_id,),
        ).fetchall()
    assert [row[0] for row in actions] == ["requested", "completed", "reused", "read"]
    assert all(row[1] == actor.correlation_id for row in actions)


def test_real_context_through_http(setup, database):
    from fastapi.testclient import TestClient

    from app.ai_assistance_config import AiAssistanceConfig
    from app.ai_assistance_routes import (
        enabled_config,
        get_assistance_service,
        get_read_service,
    )
    from app.authorization import get_actor_context, get_authorization_repository
    from app.main import create_app

    service, actor, ctx = fixture_service(setup, database, Fake(b"never"))
    service.contexts = ExecutionContextBuilder(PostgresContextReader(database))
    app = create_app()
    app.dependency_overrides[enabled_config] = lambda: AiAssistanceConfig(enabled=True)
    app.dependency_overrides[get_actor_context] = lambda: actor
    app.dependency_overrides[get_assistance_service] = lambda: service
    app.dependency_overrides[get_read_service] = lambda: service
    app.dependency_overrides[get_authorization_repository] = lambda: type(
        "Audit", (), {"audit_denial": lambda *args: None}
    )()
    path = f"/executions/{ctx.subject.execution_id}/ai-assistance"
    with TestClient(app) as http:
        generated = http.post(path, json={})
        assert generated.status_code == 200, generated.text
        assert generated.json()["state"] == "insufficient_evidence"
        assert http.get(path + "/latest").json() == generated.json()
        other_id = uuid4()
        with psycopg.connect(database) as connection:
            connection.execute(
                "INSERT INTO synergia.executions (id, organization_id, status) "
                "VALUES (%s, %s, 'completed')",
                (str(other_id), ctx.subject.organization_id),
            )
            before = connection.execute(
                "SELECT count(*) FROM synergia.ai_assistance_rate_attempts"
            ).fetchone()[0]
        other_key = AssistanceKey(
            ctx.subject.organization_id, other_id, "a" * 64, "b" * 64, None, None
        )
        reservation = service.repository.reserve(
            other_key, actor.user_id, actor.correlation_id
        )
        assert http.post(path).json() == generated.json()
        with psycopg.connect(database) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM synergia.ai_assistance_rate_attempts"
                ).fetchone()[0]
                == before
            )
        service.repository.abandon(
            other_key,
            reservation,
            actor.user_id,
            actor.correlation_id,
            "runtime_unavailable",
        )
        with psycopg.connect(database) as connection:
            connection.execute(
                "UPDATE synergia.executions SET attempt=attempt+1 WHERE id=%s",
                (str(ctx.subject.execution_id),),
            )
        assert http.get(path + "/latest").status_code == 404
        active_id = uuid4()
        with psycopg.connect(database) as connection:
            connection.execute(
                "INSERT INTO synergia.executions (id, organization_id, status) "
                "VALUES (%s, %s, 'validating')",
                (str(active_id), ctx.subject.organization_id),
            )
        active = http.post(f"/executions/{active_id}/ai-assistance", json={})
        assert active.status_code == 409
        assert active.json()["error"]["code"] == "ai_assistance_execution_not_terminal"
        with psycopg.connect(database) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM synergia.ai_assistance_rate_attempts"
                ).fetchone()[0]
                == before
            )


def test_suspended_http_reads_real_persistence_without_provider(
    setup, database, monkeypatch
):
    from fastapi.testclient import TestClient

    import app.ai_assistance_routes as routes
    from app.authorization import get_actor_context, get_authorization_repository
    from app.main import create_app

    provider = Fake(b"never")
    service, actor, ctx = fixture_service(setup, database, provider)
    service.contexts = ExecutionContextBuilder(PostgresContextReader(database))
    saved = service.generate(actor, ctx.subject.execution_id)
    monkeypatch.setenv("DATABASE_URL", database)
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENABLED", "true")
    monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_GENERATION_ENABLED", "false")
    for name in ("ENDPOINT", "MODEL", "DIGEST"):
        monkeypatch.delenv("SYNERGIA_AI_ASSISTANCE_" + name, raising=False)
    monkeypatch.delenv("RATE_LIMIT_KEY_SECRET", raising=False)
    monkeypatch.delenv("AUTH_JWT_SIGNING_KEY", raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("read-only route initialized a generation dependency")

    monkeypatch.setattr(routes, "LocalAiModelProvider", forbidden)
    monkeypatch.setattr(routes, "AssistanceLimits", forbidden)
    app = create_app()
    app.dependency_overrides[get_actor_context] = lambda: actor
    app.dependency_overrides[get_authorization_repository] = lambda: type(
        "Audit", (), {"audit_denial": lambda *args: None}
    )()
    path = f"/executions/{ctx.subject.execution_id}/ai-assistance"
    with TestClient(app) as http:
        assert http.post(path).status_code == 503
        assert http.get(path + "/latest").json() == saved.model_dump(mode="json")
        assert http.get("/me/ai-assistance-capability").json() == {
            "enabled": True,
            "read": True,
            "generate": False,
        }
    assert provider.calls == 0


def test_sliding_window_records_correlated_rejection(setup, database, caplog):
    _, _, _, actor_id, correlation = setup
    actor = ActorContext(actor_id, uuid4(), uuid4(), {}, correlation)
    org = uuid4()
    limits = AssistanceLimits(database, "s" * 32)
    for _ in range(10):
        limits.consume(actor, org)
    with pytest.raises(ApiError) as exc:
        limits.consume(actor, org)
    assert exc.value.status_code == 429
    with psycopg.connect(database) as connection:
        event = connection.execute(
            "SELECT correlation_id, retry_after_seconds "
            "FROM synergia.rate_limit_events "
            "WHERE operation='ai_assistance_generate' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        connection.execute(
            "UPDATE synergia.ai_assistance_rate_attempts "
            "SET occurred_at=clock_timestamp()-interval '11 minutes'"
        )
    assert event[0] == correlation and event[1] > 0
    assert "security.rate_limit.rejected" in caplog.text
    record = next(r for r in caplog.records if r.msg == "security.rate_limit.rejected")
    assert record.synergia_fields["correlation_id"] == str(correlation)
    limits.consume(actor, org)


def test_concurrent_generation_calls_model_once(setup, database):
    entered, release = Event(), Event()

    class BlockingProvider(Fake):
        def generate(self, system, prompt, schema):
            with psycopg.connect(database) as connection:
                count = connection.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname=current_database() "
                    "AND pid <> pg_backend_pid()"
                ).fetchone()[0]
            assert count == 0
            entered.set()
            assert release.wait(5)
            return super().generate(system, prompt, schema)

    provider = BlockingProvider(b"")
    service, actor, ctx = fixture_service(setup, database, provider, "complete")
    provider.response = json.dumps(valid(ctx), ensure_ascii=False).encode()
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(service.generate, actor, ctx.subject.execution_id)
        assert entered.wait(5)
        try:
            with pytest.raises(ApiError) as exc:
                service.generate(actor, ctx.subject.execution_id)
            assert exc.value.code == "ai_assistance_in_progress"
        finally:
            release.set()
        first = future.result()
    assert service.generate(actor, ctx.subject.execution_id) == first
    assert provider.calls == 1


def test_runtime_failure_releases_reservation_and_is_audited(setup, database):
    provider = Fake(ProviderError("runtime_unavailable"))
    service, actor, ctx = fixture_service(setup, database, provider, "complete")
    with pytest.raises(ApiError) as exc:
        service.generate(actor, ctx.subject.execution_id)
    assert exc.value.code == "ai_assistance_runtime_unavailable"
    with psycopg.connect(database) as connection:
        events = connection.execute(
            "SELECT action, rejection_code FROM synergia.ai_assistance_events "
            "WHERE execution_id=%s ORDER BY occurred_at",
            (str(ctx.subject.execution_id),),
        ).fetchall()
        count = connection.execute(
            "SELECT count(*) FROM synergia.ai_assistances WHERE execution_id=%s",
            (str(ctx.subject.execution_id),),
        ).fetchone()[0]
    assert events == [("requested", None), ("rejected", "runtime_unavailable")]
    assert count == 0
    provider.response = json.dumps(valid(ctx), ensure_ascii=False).encode()
    assert service.generate(actor, ctx.subject.execution_id).state == "ready"


def test_rate_migration_reversible(database):
    with psycopg.connect(database) as connection:
        connection.execute(
            (
                ROOT
                / "database/rollbacks/0039_create_ai_assistance_rate_attempts.down.sql"
            ).read_text()
        )
        connection.execute(
            (
                ROOT / "database/migrations/0039_create_ai_assistance_rate_attempts.sql"
            ).read_text()
        )


def test_http_rate_limit_and_correlated_audit(setup, database):
    from fastapi.testclient import TestClient

    from app.ai_assistance_config import AiAssistanceConfig
    from app.ai_assistance_routes import (
        enabled_config,
        get_assistance_service,
        get_read_service,
    )
    from app.authorization import get_actor_context, get_authorization_repository
    from app.main import create_app

    service, actor, ctx = fixture_service(setup, database, Fake(b"never"), "complete")
    for _ in range(10):
        service.limits.consume(actor, ctx.subject.organization_id)
    app = create_app()
    app.dependency_overrides[enabled_config] = lambda: AiAssistanceConfig(enabled=True)
    app.dependency_overrides[get_actor_context] = lambda: actor
    app.dependency_overrides[get_assistance_service] = lambda: service
    app.dependency_overrides[get_read_service] = lambda: service
    app.dependency_overrides[get_authorization_repository] = lambda: None
    with TestClient(app) as http:
        response = http.post(
            f"/executions/{ctx.subject.execution_id}/ai-assistance",
            headers={"X-Correlation-ID": str(actor.correlation_id)},
        )
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    with psycopg.connect(database) as connection:
        event = connection.execute(
            "SELECT correlation_id FROM synergia.rate_limit_events "
            "WHERE operation='ai_assistance_generate' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert event[0] == actor.correlation_id


def test_http_corrupt_persisted_result(setup, database):
    from fastapi.testclient import TestClient

    from app.ai_assistance_config import AiAssistanceConfig
    from app.ai_assistance_routes import (
        enabled_config,
        get_assistance_service,
        get_read_service,
    )
    from app.authorization import get_actor_context, get_authorization_repository
    from app.main import create_app

    service, actor, ctx = fixture_service(setup, database, Fake(b"never"))
    app = create_app()
    app.dependency_overrides[enabled_config] = lambda: AiAssistanceConfig(enabled=True)
    app.dependency_overrides[get_actor_context] = lambda: actor
    app.dependency_overrides[get_assistance_service] = lambda: service
    app.dependency_overrides[get_read_service] = lambda: service
    app.dependency_overrides[get_authorization_repository] = lambda: None
    path = f"/executions/{ctx.subject.execution_id}/ai-assistance"
    with TestClient(app) as http:
        response = http.post(path)
        assert response.status_code == 200
        with psycopg.connect(database) as connection:
            connection.execute(
                "UPDATE synergia.ai_assistances SET elapsed_ms=elapsed_ms+1 "
                "WHERE id=%s",
                (response.json()["assistance_id"],),
            )
        corrupt = http.get(path + "/latest")
    assert corrupt.status_code == 500
    assert corrupt.json()["error"]["code"] == "ai_assistance_integrity_error"


def test_http_concurrent_generation_returns_conflict(setup, database):
    from fastapi.testclient import TestClient

    from app.ai_assistance_config import AiAssistanceConfig
    from app.ai_assistance_routes import (
        enabled_config,
        get_assistance_service,
        get_read_service,
    )
    from app.authorization import get_actor_context, get_authorization_repository
    from app.main import create_app

    entered, release = Event(), Event()

    class Blocking(Fake):
        def generate(self, system, prompt, schema):
            entered.set()
            assert release.wait(5)
            return super().generate(system, prompt, schema)

    provider = Blocking(b"")
    service, actor, ctx = fixture_service(setup, database, provider, "complete")
    provider.response = json.dumps(valid(ctx), ensure_ascii=False).encode()
    app = create_app()
    app.dependency_overrides[enabled_config] = lambda: AiAssistanceConfig(enabled=True)
    app.dependency_overrides[get_actor_context] = lambda: actor
    app.dependency_overrides[get_assistance_service] = lambda: service
    app.dependency_overrides[get_read_service] = lambda: service
    app.dependency_overrides[get_authorization_repository] = lambda: None
    path = f"/executions/{ctx.subject.execution_id}/ai-assistance"
    with TestClient(app) as http, ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(http.post, path)
        assert entered.wait(5)
        try:
            conflict = http.post(path)
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "ai_assistance_in_progress"
        finally:
            release.set()
        assert first.result().status_code == 200
    assert provider.calls == 1
