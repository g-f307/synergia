from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from app.auth.config import AuthConfig


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    token_id: UUID


class PasswordVerifier:
    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self.hasher = hasher or PasswordHasher()
        self._dummy_hash = self.hasher.hash(
            "synthetic-dummy-password-never-authenticates"
        )

    def verify(self, password_hash: str | None, password: str) -> bool:
        selected_hash = password_hash or self._dummy_hash
        try:
            verified = self.hasher.verify(selected_hash, password)
        except VerificationError:
            return False
        return bool(verified and password_hash is not None)

    def updated_hash(self, password_hash: str, password: str) -> str | None:
        if self.hasher.check_needs_rehash(password_hash):
            return self.hasher.hash(password)
        return None


class TokenCodec:
    def __init__(
        self,
        config: AuthConfig,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.clock = clock or (lambda: datetime.now(UTC))

    def issue_access(self, user_id: UUID, session_id: UUID) -> tuple[str, int]:
        now = self.clock()
        expires = now + timedelta(minutes=self.config.access_minutes)
        payload = {
            "iss": self.config.issuer,
            "aud": self.config.audience,
            "sub": str(user_id),
            "sid": str(session_id),
            "jti": str(uuid4()),
            "iat": now,
            "nbf": now,
            "exp": expires,
            "typ": "access",
        }
        token = jwt.encode(
            payload,
            self.config.signing_key,
            algorithm=self.config.algorithm,
        )
        return token, self.config.access_minutes * 60

    def decode_access(self, token: str) -> AccessClaims:
        payload = jwt.decode(
            token,
            self.config.signing_key,
            algorithms=[self.config.algorithm],
            issuer=self.config.issuer,
            audience=self.config.audience,
            leeway=self.config.clock_skew_seconds,
            options={
                "require": [
                    "iss",
                    "aud",
                    "sub",
                    "sid",
                    "jti",
                    "iat",
                    "nbf",
                    "exp",
                    "typ",
                ],
                "strict_aud": True,
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
        numeric_dates = (payload["iat"], payload["nbf"], payload["exp"])
        if any(not isinstance(value, int | float) for value in numeric_dates):
            raise jwt.InvalidTokenError("invalid numeric date")
        now = self.clock().timestamp()
        leeway = self.config.clock_skew_seconds
        if payload["exp"] <= now - leeway:
            raise jwt.ExpiredSignatureError("token expired")
        if payload["nbf"] > now + leeway or payload["iat"] > now + leeway:
            raise jwt.ImmatureSignatureError("token is not active")
        if payload.get("typ") != "access":
            raise jwt.InvalidTokenError("unexpected token type")
        try:
            return AccessClaims(
                user_id=UUID(payload["sub"]),
                session_id=UUID(payload["sid"]),
                token_id=UUID(payload["jti"]),
            )
        except (TypeError, ValueError) as exc:
            raise jwt.InvalidTokenError("invalid identity claims") from exc


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def sha256_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def protected_identifier(value: str, key: str) -> str:
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()
