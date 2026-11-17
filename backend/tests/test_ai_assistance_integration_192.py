"""Ensaio integrado real em PostgreSQL + API sem overrides de auth/org/repo."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from uuid import UUID, uuid4

import psycopg
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from test_ai_assistance_e2e_gates import (
    DIGEST,
    MODEL,
    _start_synthetic_ollama,
    _SyntheticOllamaState,
)

from app.ai_assistance_context import ExecutionContextBuilder
from app.ai_assistance_context_reader import PostgresContextReader
from app.ai_assistance_fallback import required_limitations
from app.authorization import ActorContext
from app.main import create_app

pytestmark = [pytest.mark.integration]

BUSINESS_TABLES = (
    "workorders",
    "lots",
    "serials",
    "classifications",
    "pending_items",
    "pipeline_issues",
    "source_files",
)


def _snapshot_business_content(database_url: str, execution_id: str) -> dict[str, str]:
    snapshots: dict[str, str] = {}
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        exec_row = conn.execute(
            "SELECT * FROM synergia.executions WHERE id = %s",
            (execution_id,),
        ).fetchone()
        snapshots["executions"] = hashlib.sha256(
            json.dumps(exec_row, default=str, sort_keys=True).encode("utf-8")
        ).hexdigest()
        for table in BUSINESS_TABLES:
            rows = conn.execute(
                f"SELECT * FROM synergia.{table} WHERE execution_id = %s",
                (execution_id,),
            ).fetchall()
            normalized = sorted(
                json.dumps(row, default=str, sort_keys=True) for row in rows
            )
            snapshots[table] = hashlib.sha256(
                "\n".join(normalized).encode("utf-8")
            ).hexdigest()
    return snapshots


def _nearest_rank_p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    rank = math.ceil(0.95 * len(ordered)) - 1
    return ordered[max(0, min(rank, len(ordered) - 1))]


def _seed_self_contained_tenants(database_url: str, password: str) -> dict[str, str]:
    suffix = uuid4().hex[:8]
    org_a = str(uuid4())
    org_b = str(uuid4())
    user_a = str(uuid4())
    user_b = str(uuid4())
    email_a = f"int192-a-{suffix}@example.invalid"
    email_b = f"int192-b-{suffix}@example.invalid"
    exec_a = str(uuid4())
    exec_b_other = str(uuid4())
    pw_hash = PasswordHasher().hash(password)

    with psycopg.connect(database_url) as conn:
        for oid, code, name in (
            (org_a, f"syn-192-a-{suffix}", "Synthetic 192 Org A"),
            (org_b, f"syn-192-b-{suffix}", "Synthetic 192 Org B"),
        ):
            conn.execute(
                """INSERT INTO synergia.iam_organizations
                (id, organization_code, display_name) VALUES (%s, %s, %s)""",
                (oid, code, name),
            )
        for uid, email, oid in (
            (user_a, email_a, org_a),
            (user_b, email_b, org_b),
        ):
            conn.execute(
                """INSERT INTO synergia.identity_users
                (id, status, display_name, local_password_hash, locale)
                VALUES (%s, 'active', 'Synthetic 192 User', %s, 'en-US')""",
                (uid, pw_hash),
            )
            conn.execute(
                """INSERT INTO synergia.user_emails
                (user_id, email, is_primary, is_verified, verified_at)
                VALUES (%s, %s, true, true, now())""",
                (uid, email),
            )
            conn.execute(
                """INSERT INTO synergia.user_role_assignments
                (user_id, role_id, organization_id)
                SELECT %s, id, %s FROM synergia.roles
                WHERE normalized_key = 'gestor'""",
                (uid, oid),
            )
        for ex_id in (exec_a, exec_b_other):
            conn.execute(
                """INSERT INTO synergia.executions
                (id, organization_id, initiated_by_user_id, status, source, finished_at)
                VALUES (%s, %s, %s, 'completed', 'N-FP', now())""",
                (ex_id, org_a, user_a),
            )
            src_id = conn.execute(
                """INSERT INTO synergia.source_files
                (execution_id, file_name, content_hash, source, size_bytes)
                VALUES (%s, 'synthetic.csv', %s, 'N-FP', 128) RETURNING id""",
                (ex_id, uuid4().hex * 2),
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO synergia.pipeline_issues
                (execution_id, source_file_id, scope, severity, code, reason)
                VALUES (%s, %s, 'record', 'error', 'invalid_value',
                'Synthetic integration evidence')""",
                (ex_id, src_id),
            )
        conn.commit()
    return {
        "org_a": org_a,
        "org_b": org_b,
        "user_a": user_a,
        "email_a": email_a,
        "email_b": email_b,
        "exec_a": exec_a,
        "exec_b_other": exec_b_other,
    }


def test_real_postgres_integration_isolation_degradation_and_p95(monkeypatch):
    database_url = os.environ["DATABASE_URL"]
    password = "synthetic-int-192-password-long"
    seeded = _seed_self_contained_tenants(database_url, password)
    exec_a = seeded["exec_a"]
    exec_b_other = seeded["exec_b_other"]
    org_a = seeded["org_a"]
    user_a = seeded["user_a"]

    monkeypatch.setenv("SYNERGIA_ENV", "test")
    monkeypatch.setenv(
        "AUTH_JWT_SIGNING_KEY",
        os.getenv("AUTH_JWT_SIGNING_KEY", "synthetic-192-jwt-signing-key-at-least-32b"),
    )
    monkeypatch.setenv(
        "AUTH_JWT_ISSUER", os.getenv("AUTH_JWT_ISSUER", "synergia-test")
    )
    monkeypatch.setenv(
        "AUTH_JWT_AUDIENCE", os.getenv("AUTH_JWT_AUDIENCE", "synergia-api")
    )
    monkeypatch.setenv(
        "AUTH_REFRESH_TOKEN_SECRET",
        os.getenv("AUTH_REFRESH_TOKEN_SECRET", "synthetic-192-refresh-secret-32b"),
    )
    monkeypatch.setenv(
        "RATE_LIMIT_KEY_SECRET",
        os.getenv("RATE_LIMIT_KEY_SECRET", "synthetic-192-ratelimit-secret-32b"),
    )

    payload_holder = {"bytes": b""}

    class DynamicState(_SyntheticOllamaState):
        @property
        def payload(self):
            return payload_holder["bytes"]

        @payload.setter
        def payload(self, value):
            pass

    dyn_state = DynamicState(b"{}")
    server, endpoint = _start_synthetic_ollama(dyn_state)

    try:
        monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENABLED", "true")
        monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_GENERATION_ENABLED", "true")
        monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENDPOINT", endpoint)
        monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_MODEL", MODEL)
        monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_DIGEST", DIGEST)

        app = create_app()
        with TestClient(app) as client:
            login_a = client.post(
                "/auth/login",
                json={"email": seeded["email_a"], "password": password},
            )
            assert login_a.status_code == 200
            headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}

            login_b = client.post(
                "/auth/login",
                json={"email": seeded["email_b"], "password": password},
            )
            assert login_b.status_code == 200
            headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

            assert client.get("/health/ready").status_code == 200

            actor_ctx = ActorContext(
                user_id=UUID(user_a),
                session_id=uuid4(),
                token_id=uuid4(),
                permissions={"execution.read": frozenset({UUID(org_a)})},
                correlation_id=uuid4(),
            )
            real_ctx = ExecutionContextBuilder(
                PostgresContextReader(database_url)
            ).build(actor_ctx, UUID(exec_a))
            refs = sorted(real_ctx.evidence_refs())
            payload_holder["bytes"] = json.dumps(
                {
                    "summary": "A execução registra 1 erros, 0 avisos e 0 pendências.",
                    "findings": [
                        {
                            "title": "Registros disponíveis",
                            "explanation": "Há registros disponíveis para conferência.",
                            "evidence_refs": refs[:3],
                        }
                    ],
                    "human_checks": ["Conferência humana das referências disponíveis."],
                    "limitations": required_limitations(real_ctx),
                },
                ensure_ascii=False,
            ).encode("utf-8")

            before_hashes = _snapshot_business_content(database_url, exec_a)
            first = client.post(
                f"/executions/{exec_a}/ai-assistance", json={}, headers=headers_a
            )
            assert first.status_code == 200
            assert first.json()["state"] == "ready"
            assert first.json()["provenance"]["origin"] == "model"
            assert dyn_state.calls == 1

            latest = client.get(
                f"/executions/{exec_a}/ai-assistance/latest", headers=headers_a
            )
            assert latest.status_code == 200
            assert latest.json()["assistance_id"] == first.json()["assistance_id"]

            repeat = client.post(
                f"/executions/{exec_a}/ai-assistance", json={}, headers=headers_a
            )
            assert repeat.status_code == 200
            assert repeat.json()["assistance_id"] == first.json()["assistance_id"]
            assert dyn_state.calls == 1
            assert _snapshot_business_content(database_url, exec_a) == before_hashes

            # Org B cross-tenant denial
            assert (
                client.get(
                    f"/executions/{exec_a}/ai-assistance/latest", headers=headers_b
                ).status_code
                == 404
            )
            assert (
                client.post(
                    f"/executions/{exec_a}/ai-assistance", json={}, headers=headers_b
                ).status_code
                == 404
            )

            # Suspend generation: keep GET latest and readiness
            monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_GENERATION_ENABLED", "false")
            assert (
                client.get(
                    f"/executions/{exec_a}/ai-assistance/latest", headers=headers_a
                ).status_code
                == 200
            )
            assert (
                client.post(
                    f"/executions/{exec_a}/ai-assistance", json={}, headers=headers_a
                ).status_code
                == 503
            )
            assert client.get("/health/ready").status_code == 200
            monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_GENERATION_ENABLED", "true")

            # Real PostgreSQL + API non-inference p95 (5 warmups + 30 measured samples)
            for _ in range(5):
                assert (
                    client.get(f"/executions/{exec_a}", headers=headers_a).status_code
                    == 200
                )
                assert (
                    client.get(
                        f"/executions/{exec_a}/ai-assistance/latest", headers=headers_a
                    ).status_code
                    == 200
                )
            samples_exec: list[float] = []
            samples_latest: list[float] = []
            for _ in range(30):
                t0 = time.perf_counter()
                r1 = client.get(f"/executions/{exec_a}", headers=headers_a)
                t1 = time.perf_counter()
                r2 = client.get(
                    f"/executions/{exec_a}/ai-assistance/latest", headers=headers_a
                )
                t2 = time.perf_counter()
                assert r1.status_code == 200 and r2.status_code == 200
                samples_exec.append((t1 - t0) * 1000.0)
                samples_latest.append((t2 - t1) * 1000.0)

            assert _nearest_rank_p95(samples_exec) < 1000.0
            assert _nearest_rank_p95(samples_latest) < 1000.0
    finally:
        server.shutdown()
        server.server_close()

    # Stopped runtime: previous GET latest still 200, readiness 200, new generation 503
    with TestClient(create_app()) as client_stopped:
        assert (
            client_stopped.get(
                f"/executions/{exec_a}/ai-assistance/latest", headers=headers_a
            ).status_code
            == 200
        )
        assert client_stopped.get("/health/ready").status_code == 200
        assert (
            client_stopped.get(f"/executions/{exec_a}", headers=headers_a).status_code
            == 200
        )
        assert (
            client_stopped.post(
                f"/executions/{exec_b_other}/ai-assistance", json={}, headers=headers_a
            ).status_code
            == 503
        )

        # Disabled flag on server
        monkeypatch.setenv("SYNERGIA_AI_ASSISTANCE_ENABLED", "false")
        cap = client_stopped.get("/me/ai-assistance-capability", headers=headers_a)
        assert cap.status_code == 200
        assert cap.json() == {"enabled": False, "read": False, "generate": False}
        assert (
            client_stopped.get(f"/executions/{exec_a}", headers=headers_a).status_code
            == 200
        )
        assert client_stopped.get("/health/ready").status_code == 200
        assert (
            client_stopped.get(
                f"/executions/{exec_a}/ai-assistance/latest", headers=headers_a
            ).status_code
            == 503
        )
