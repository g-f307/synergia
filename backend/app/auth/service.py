from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import jwt

from app.auth.config import AuthConfig
from app.auth.models import RefreshResult, SessionResult
from app.auth.repository import AuthRepository
from app.auth.security import (
    AccessClaims,
    PasswordVerifier,
    TokenCodec,
    protected_identifier,
    sha256_token,
)
from app.errors import ApiError

INVALID_CREDENTIALS = "E-mail ou credencial invalidos"
INVALID_SESSION = "Sessao invalida ou expirada"


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        config: AuthConfig,
        *,
        passwords: PasswordVerifier | None = None,
        tokens: TokenCodec | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.config = config
        self.passwords = passwords or PasswordVerifier()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.tokens = tokens or TokenCodec(config, self.clock)

    def login(
        self, email: str, password: str, client_ip: str | None
    ) -> tuple[SessionResult, str, int]:
        if not self.config.local_auth_enabled:
            raise ApiError(
                503,
                "identity_adapter_unavailable",
                "Adaptador de identidade indisponivel",
            )
        now = self.clock()
        identifier_hash = protected_identifier(email, self.config.signing_key)
        ip_hash = (
            protected_identifier(client_ip, self.config.signing_key)
            if client_ip
            else None
        )
        attempt_id, retry_after = self.repository.begin_login_attempt(
            identifier_hash,
            ip_hash,
            now,
            self.config.login_window_seconds,
            self.config.login_max_attempts,
            self.config.login_block_seconds,
        )
        if attempt_id is None:
            assert retry_after is not None
            raise ApiError(
                429,
                "login_rate_limited",
                "Muitas tentativas de autenticacao",
                {"retry_after": retry_after},
                {"Retry-After": str(retry_after)},
            )

        credentials = self.repository.credentials_for_email(email)
        password_hash = credentials.password_hash if credentials else None
        password_valid = self.passwords.verify(password_hash, password)
        if credentials is None or credentials.status != "active" or not password_valid:
            reason = "invalid_credentials"
            self.repository.fail_login(attempt_id, identifier_hash, reason)
            raise ApiError(401, "invalid_credentials", INVALID_CREDENTIALS)

        updated_hash = self.passwords.updated_hash(credentials.password_hash, password)
        try:
            session = self.repository.create_session(
                attempt_id,
                credentials.user_id,
                now,
                self.config.refresh_idle_hours,
                self.config.refresh_absolute_hours,
                updated_hash,
            )
        except ValueError as exc:
            self.repository.fail_login(
                attempt_id, identifier_hash, "user_status_changed"
            )
            raise ApiError(401, "invalid_credentials", INVALID_CREDENTIALS) from exc
        access_token, expires_in = self.tokens.issue_access(
            session.user_id, session.session_id
        )
        return session, access_token, expires_in

    def refresh(self, refresh_token: str) -> tuple[RefreshResult, str, int]:
        result = self.repository.rotate_refresh(
            sha256_token(refresh_token),
            self.clock(),
            self.config.refresh_idle_hours,
        )
        if result.status == "replayed":
            raise ApiError(401, "refresh_token_reused", INVALID_SESSION)
        if result.status != "rotated":
            raise ApiError(401, "invalid_refresh_token", INVALID_SESSION)
        assert result.user_id and result.session_id and result.refresh_token
        access_token, expires_in = self.tokens.issue_access(
            result.user_id, result.session_id
        )
        return result, access_token, expires_in

    def access_claims(self, access_token: str) -> AccessClaims:
        try:
            return self.tokens.decode_access(access_token)
        except jwt.InvalidTokenError as exc:
            raise ApiError(401, "invalid_access_token", INVALID_SESSION) from exc

    def logout(self, claims: AccessClaims) -> int:
        return self.repository.revoke_session(
            claims.user_id, claims.session_id, self.clock()
        )

    def logout_all(self, claims: AccessClaims) -> int:
        return self.repository.revoke_all_sessions(claims.user_id, self.clock())
