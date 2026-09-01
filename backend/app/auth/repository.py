from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.auth.models import CredentialRecord, RefreshResult, SessionResult
from app.auth.security import new_refresh_token, sha256_token


class AuthRepository(Protocol):
    def begin_login_attempt(
        self,
        identifier_hash: str,
        ip_hash: str | None,
        now: datetime,
        window_seconds: int,
        max_attempts: int,
        block_seconds: int,
    ) -> tuple[int | None, int | None]: ...

    def credentials_for_email(self, email: str) -> CredentialRecord | None: ...

    def fail_login(
        self, attempt_id: int, identifier_hash: str, reason: str
    ) -> None: ...

    def create_session(
        self,
        attempt_id: int,
        user_id: UUID,
        now: datetime,
        idle_hours: int,
        absolute_hours: int,
        password_hash: str | None,
    ) -> SessionResult: ...

    def rotate_refresh(
        self,
        token_hash: str,
        now: datetime,
        idle_hours: int,
    ) -> RefreshResult: ...

    def revoke_session(self, user_id: UUID, session_id: UUID, now: datetime) -> int: ...

    def revoke_all_sessions(self, user_id: UUID, now: datetime) -> int: ...


class PostgresAuthRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _event(
        cursor,
        event_key: str,
        entity_type: str,
        entity_id: str,
        *,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        payload: dict | None = None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO synergia.identity_access_events (
                event_key, actor_user_id, subject_user_id, session_id,
                entity_type, entity_id, payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event_key,
                user_id,
                user_id,
                session_id,
                entity_type,
                entity_id,
                Jsonb(payload or {}),
            ),
        )

    def begin_login_attempt(
        self,
        identifier_hash: str,
        ip_hash: str | None,
        now: datetime,
        window_seconds: int,
        max_attempts: int,
        block_seconds: int,
    ) -> tuple[int | None, int | None]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 41))",
                (identifier_hash,),
            )
            cursor.execute(
                """
                DELETE FROM synergia.identity_login_attempts
                WHERE attempted_at < %s - interval '48 hours'
                """,
                (now,),
            )
            cursor.execute(
                """
                SELECT count(*) AS failures, max(blocked_until) AS blocked_until
                FROM synergia.identity_login_attempts
                WHERE identifier_hash = %s
                  AND succeeded = false
                  AND attempted_at >= %s - make_interval(secs => %s)
                """,
                (identifier_hash, now, window_seconds),
            )
            state = cursor.fetchone()
            blocked_until = state["blocked_until"]
            if blocked_until is not None and blocked_until > now:
                retry = max(1, int((blocked_until - now).total_seconds()))
                self._event(
                    cursor,
                    "auth.login_rate_limited",
                    "login_identifier",
                    identifier_hash,
                    payload={"retry_after": retry},
                )
                return None, retry
            if state["failures"] >= max_attempts:
                blocked_until = now + timedelta(seconds=block_seconds)
                cursor.execute(
                    """
                    UPDATE synergia.identity_login_attempts
                    SET blocked_until = %s
                    WHERE id = (
                        SELECT id FROM synergia.identity_login_attempts
                        WHERE identifier_hash = %s AND succeeded = false
                        ORDER BY attempted_at DESC, id DESC LIMIT 1
                    )
                    """,
                    (blocked_until, identifier_hash),
                )
                self._event(
                    cursor,
                    "auth.login_rate_limited",
                    "login_identifier",
                    identifier_hash,
                    payload={"retry_after": block_seconds},
                )
                return None, block_seconds
            cursor.execute(
                """
                INSERT INTO synergia.identity_login_attempts (
                    identifier_hash, ip_hash, succeeded, attempted_at
                ) VALUES (%s, %s, false, %s)
                RETURNING id
                """,
                (identifier_hash, ip_hash, now),
            )
            attempt_id = cursor.fetchone()["id"]
            return attempt_id, None

    def credentials_for_email(self, email: str) -> CredentialRecord | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.status, u.local_password_hash
                FROM synergia.user_emails e
                JOIN synergia.identity_users u ON u.id = e.user_id
                WHERE e.normalized_email = %s AND e.disabled_at IS NULL
                """,
                (email,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return CredentialRecord(
                user_id=row["id"],
                status=row["status"],
                password_hash=row["local_password_hash"],
            )

    def fail_login(self, attempt_id: int, identifier_hash: str, reason: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            self._event(
                cursor,
                "auth.login_failed",
                "login_attempt",
                str(attempt_id),
                payload={"identifier_hash": identifier_hash, "reason": reason},
            )

    def create_session(
        self,
        attempt_id: int,
        user_id: UUID,
        now: datetime,
        idle_hours: int,
        absolute_hours: int,
        password_hash: str | None,
    ) -> SessionResult:
        session_id = uuid4()
        family_id = uuid4()
        refresh_token = new_refresh_token()
        idle_expires_at = now + timedelta(hours=idle_hours)
        absolute_expires_at = now + timedelta(hours=absolute_hours)
        refresh_expires_at = min(idle_expires_at, absolute_expires_at)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, status FROM synergia.identity_users
                WHERE id = %s FOR UPDATE
                """,
                (user_id,),
            )
            user = cursor.fetchone()
            if user is None or user["status"] != "active":
                raise ValueError("user is not active")
            if password_hash is not None:
                cursor.execute(
                    """
                    UPDATE synergia.identity_users
                    SET local_password_hash = %s WHERE id = %s
                    """,
                    (password_hash, user_id),
                )
            cursor.execute(
                """
                UPDATE synergia.identity_login_attempts
                SET succeeded = true WHERE id = %s
                """,
                (attempt_id,),
            )
            cursor.execute(
                """
                INSERT INTO synergia.identity_sessions (
                    id, user_id, authenticated_at, last_seen_at, idle_expires_at,
                    absolute_expires_at, authentication_method
                ) VALUES (%s, %s, %s, %s, %s, %s, 'local')
                """,
                (
                    session_id,
                    user_id,
                    now,
                    now,
                    idle_expires_at,
                    absolute_expires_at,
                ),
            )
            cursor.execute(
                """
                INSERT INTO synergia.session_refresh_tokens (
                    session_id, family_id, token_hash, issued_at, expires_at
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    family_id,
                    sha256_token(refresh_token),
                    now,
                    refresh_expires_at,
                ),
            )
            self._event(
                cursor,
                "auth.login_succeeded",
                "identity_session",
                str(session_id),
                user_id=user_id,
                session_id=session_id,
                payload={"authentication_method": "local"},
            )
        return SessionResult(
            user_id=user_id,
            session_id=session_id,
            refresh_token=refresh_token,
            refresh_expires_at=refresh_expires_at,
        )

    @staticmethod
    def _revoke_family(cursor, session_id: UUID, now: datetime, reason: str) -> None:
        cursor.execute(
            """
            UPDATE synergia.session_refresh_tokens
            SET status = 'revoked', revoked_at = %s, revocation_reason = %s
            WHERE session_id = %s AND status = 'active'
            """,
            (now, reason, session_id),
        )
        cursor.execute(
            """
            UPDATE synergia.identity_sessions
            SET status = 'revoked', revoked_at = %s, revocation_reason = %s
            WHERE id = %s AND status = 'active'
            """,
            (now, reason, session_id),
        )

    def rotate_refresh(
        self,
        token_hash: str,
        now: datetime,
        idle_hours: int,
    ) -> RefreshResult:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rt.id, rt.session_id, rt.family_id, rt.status AS token_status,
                       rt.expires_at, s.user_id, s.status AS session_status,
                       s.idle_expires_at, s.absolute_expires_at,
                       u.status AS user_status
                FROM synergia.session_refresh_tokens rt
                JOIN synergia.identity_sessions s ON s.id = rt.session_id
                JOIN synergia.identity_users u ON u.id = s.user_id
                WHERE rt.token_hash = %s
                FOR UPDATE OF rt, s
                """,
                (token_hash,),
            )
            current = cursor.fetchone()
            if current is None:
                self._event(
                    cursor,
                    "auth.refresh_failed",
                    "refresh_token",
                    "unknown",
                    payload={"reason": "invalid_refresh_token"},
                )
                return RefreshResult(status="invalid")
            if current["token_status"] == "used":
                self._revoke_family(
                    cursor, current["session_id"], now, "refresh_token_reuse"
                )
                self._event(
                    cursor,
                    "auth.refresh_reused",
                    "identity_session",
                    str(current["session_id"]),
                    user_id=current["user_id"],
                    session_id=current["session_id"],
                )
                return RefreshResult(status="replayed")
            valid = (
                current["token_status"] == "active"
                and current["session_status"] == "active"
                and current["user_status"] == "active"
                and current["expires_at"] > now
                and current["absolute_expires_at"] > now
            )
            if not valid:
                if current["token_status"] == "active" and current["expires_at"] <= now:
                    cursor.execute(
                        """
                        UPDATE synergia.session_refresh_tokens
                        SET status = 'expired' WHERE id = %s
                        """,
                        (current["id"],),
                    )
                if (
                    current["session_status"] == "active"
                    and (
                        current["idle_expires_at"] <= now
                        or current["absolute_expires_at"] <= now
                    )
                ):
                    cursor.execute(
                        """
                        UPDATE synergia.identity_sessions
                        SET status = 'expired' WHERE id = %s
                        """,
                        (current["session_id"],),
                    )
                self._event(
                    cursor,
                    "auth.refresh_failed",
                    "identity_session",
                    str(current["session_id"]),
                    user_id=current["user_id"],
                    session_id=current["session_id"],
                    payload={"reason": "inactive_or_expired"},
                )
                return RefreshResult(status="invalid")

            refresh_token = new_refresh_token()
            replacement_id = uuid4()
            idle_expires_at = min(
                now + timedelta(hours=idle_hours), current["absolute_expires_at"]
            )
            cursor.execute(
                """
                INSERT INTO synergia.session_refresh_tokens (
                    id, session_id, family_id, token_hash, issued_at, expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    replacement_id,
                    current["session_id"],
                    current["family_id"],
                    sha256_token(refresh_token),
                    now,
                    idle_expires_at,
                ),
            )
            cursor.execute(
                """
                UPDATE synergia.session_refresh_tokens
                SET status = 'used', used_at = %s, replaced_by_token_id = %s
                WHERE id = %s
                """,
                (now, replacement_id, current["id"]),
            )
            cursor.execute(
                """
                UPDATE synergia.identity_sessions
                SET last_seen_at = %s, idle_expires_at = %s
                WHERE id = %s
                """,
                (now, idle_expires_at, current["session_id"]),
            )
            self._event(
                cursor,
                "auth.refresh_rotated",
                "refresh_token",
                str(replacement_id),
                user_id=current["user_id"],
                session_id=current["session_id"],
            )
            return RefreshResult(
                status="rotated",
                user_id=current["user_id"],
                session_id=current["session_id"],
                refresh_token=refresh_token,
                refresh_expires_at=idle_expires_at,
            )

    def revoke_session(self, user_id: UUID, session_id: UUID, now: datetime) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM synergia.identity_sessions
                WHERE id = %s AND user_id = %s FOR UPDATE
                """,
                (session_id, user_id),
            )
            if cursor.fetchone() is None:
                return 0
            cursor.execute(
                "SELECT status FROM synergia.identity_sessions WHERE id = %s",
                (session_id,),
            )
            was_active = cursor.fetchone()["status"] == "active"
            self._revoke_family(cursor, session_id, now, "logout")
            self._event(
                cursor,
                "auth.logout",
                "identity_session",
                str(session_id),
                user_id=user_id,
                session_id=session_id,
            )
            return int(was_active)

    def revoke_all_sessions(self, user_id: UUID, now: datetime) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM synergia.identity_users WHERE id = %s FOR UPDATE",
                (user_id,),
            )
            if cursor.fetchone() is None:
                return 0
            cursor.execute(
                """
                UPDATE synergia.session_refresh_tokens rt
                SET status = 'revoked', revoked_at = %s,
                    revocation_reason = 'global_logout'
                FROM synergia.identity_sessions s
                WHERE s.id = rt.session_id AND s.user_id = %s AND rt.status = 'active'
                """,
                (now, user_id),
            )
            cursor.execute(
                """
                UPDATE synergia.identity_sessions
                SET status = 'revoked', revoked_at = %s,
                    revocation_reason = 'global_logout'
                WHERE user_id = %s AND status = 'active'
                RETURNING id
                """,
                (now, user_id),
            )
            revoked = [row["id"] for row in cursor.fetchall()]
            self._event(
                cursor,
                "auth.logout_all",
                "identity_user",
                str(user_id),
                user_id=user_id,
                payload={"revoked_sessions": len(revoked)},
            )
            return len(revoked)
