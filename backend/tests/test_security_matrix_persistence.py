from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.auth.config import AuthConfig
from app.auth.security import TokenCodec
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from security_matrix import ROLES, load_cases  # noqa: E402

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_authorization,
    pytest.mark.security,
]
CASES = load_cases()
KEY = "runtime-security-matrix-signing-key-at-least-32-bytes"
PATH_VALUES = {
    "execution_id": "security-missing-execution",
    "workorder_number": "SECURITY-MISSING-WO",
    "lot_number": "SECURITY-MISSING-LOT",
    "serial_number": "SECURITY-MISSING-SERIAL",
    "pending_id": "1",
    "evidence_id": "1",
    "user_id": "00000000-0000-4000-8000-000000000001",
    "group_id": "00000000-0000-4000-8000-000000000002",
    "role_id": "00000000-0000-4000-8000-000000000003",
    "left_id": "00000000-0000-4000-8000-000000000004",
    "right_id": "00000000-0000-4000-8000-000000000005",
}


@dataclass
class RuntimeActors:
    database_url: str
    config: AuthConfig
    users: dict[str, UUID]
    sessions: dict[str, UUID]

    def token(self, role: str, *, disposable: bool = False) -> str:
        session_id = self.sessions[role]
        if disposable:
            session_id = uuid4()
            now = datetime.now(UTC)
            with psycopg.connect(self.database_url) as connection:
                connection.execute(
                    """
                    INSERT INTO synergia.identity_sessions (
                        id, user_id, status, authenticated_at, last_seen_at,
                        idle_expires_at, absolute_expires_at,
                        authentication_method
                    ) VALUES (%s, %s, 'active', %s, %s, %s, %s, 'synthetic')
                    """,
                    (
                        session_id,
                        self.users[role],
                        now,
                        now,
                        now + timedelta(hours=8),
                        now + timedelta(hours=24),
                    ),
                )
        return TokenCodec(self.config).issue_access(self.users[role], session_id)[0]


@pytest.fixture(scope="module")
def runtime_actors() -> RuntimeActors:
    database_url = os.environ["DATABASE_URL"]
    previous = {
        key: os.environ.get(key)
        for key in (
            "SYNERGIA_ENV",
            "AUTH_JWT_SIGNING_KEY",
            "AUTH_JWT_ISSUER",
            "AUTH_JWT_AUDIENCE",
        )
    }
    os.environ.update(
        {
            "SYNERGIA_ENV": "test",
            "AUTH_JWT_SIGNING_KEY": KEY,
            "AUTH_JWT_ISSUER": "synergia-runtime-security",
            "AUTH_JWT_AUDIENCE": "synergia-runtime-security-api",
        }
    )
    suffix = uuid4().hex[:10]
    organization_id = uuid4()
    users: dict[str, UUID] = {}
    sessions: dict[str, UUID] = {}
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO synergia.iam_organizations (
                id, organization_code, display_name
            ) VALUES (%s, %s, %s)
            """,
            (organization_id, f"security-{suffix}", f"Security {suffix}"),
        )
        for role in ROLES:
            user_id = uuid4()
            session_id = uuid4()
            users[role] = user_id
            sessions[role] = session_id
            connection.execute(
                """
                INSERT INTO synergia.identity_users (id, status, display_name)
                VALUES (%s, 'active', %s)
                """,
                (user_id, f"Security {role} {suffix}"),
            )
            connection.execute(
                """
                INSERT INTO synergia.identity_sessions (
                    id, user_id, status, authenticated_at, last_seen_at,
                    idle_expires_at, absolute_expires_at,
                    authentication_method
                ) VALUES (
                    %s, %s, 'active', now(), now(),
                    now() + interval '8 hours', now() + interval '24 hours',
                    'synthetic'
                )
                """,
                (session_id, user_id),
            )
            connection.execute(
                """
                INSERT INTO synergia.user_role_assignments (
                    user_id, role_id, organization_id
                )
                SELECT %s, id, %s FROM synergia.roles
                WHERE normalized_key = %s
                """,
                (user_id, None if role == "admin" else organization_id, role),
            )
    actors = RuntimeActors(database_url, AuthConfig.from_env(), users, sessions)
    try:
        yield actors
    finally:
        with psycopg.connect(database_url) as connection:
            user_ids = list(users.values())
            connection.execute(
                """
                UPDATE synergia.user_role_assignments
                SET revoked_at = now(), revocation_reason = 'security test cleanup'
                WHERE user_id = ANY(%s) AND revoked_at IS NULL
                """,
                (user_ids,),
            )
            connection.execute(
                """
                UPDATE synergia.identity_sessions
                SET status = 'revoked', revoked_at = now(),
                    revocation_reason = 'security_test_cleanup'
                WHERE user_id = ANY(%s) AND status = 'active'
                """,
                (user_ids,),
            )
            connection.execute(
                """
                UPDATE synergia.identity_users
                SET status = 'inactive', deactivated_at = now()
                WHERE id = ANY(%s) AND status = 'active'
                """,
                (user_ids,),
            )
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def concrete_path(path: str) -> str:
    for parameter, value in PATH_VALUES.items():
        path = path.replace(f"{{{parameter}}}", value)
    assert "{" not in path
    return path


@pytest.mark.parametrize(
    ("case", "role"),
    [(case, role) for case in CASES for role in ROLES],
    ids=[f"{case.method}-{case.path}-{role}" for case in CASES for role in ROLES],
)
def test_role_route_method_matrix_executes_real_authorization(
    case, role, runtime_actors
) -> None:
    headers = {
        "Authorization": f"Bearer {runtime_actors.token(role, disposable=True)}",
        "X-Correlation-ID": str(uuid4()),
    }

    with TestClient(app) as client:
        response = client.request(
            case.method,
            concrete_path(case.path),
            headers=headers,
            json={} if case.method in {"POST", "PUT", "PATCH", "DELETE"} else None,
        )

    if role in case.allowed_roles:
        assert response.status_code not in {401, 403}, (
            f"{case.identifier} deveria permitir {role}: {response.text}"
        )
    else:
        assert response.status_code == 403, (
            f"{case.identifier} deveria negar {role}: "
            f"status={response.status_code} body={response.text}"
        )
