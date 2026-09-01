from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.users import normalize_email


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(
        min_length=1,
        max_length=1024,
        json_schema_extra={"writeOnly": True},
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    session_id: UUID


class LogoutResponse(BaseModel):
    revoked_sessions: int


@dataclass(frozen=True)
class CredentialRecord:
    user_id: UUID
    status: str
    password_hash: str | None


@dataclass(frozen=True)
class SessionResult:
    user_id: UUID
    session_id: UUID
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(frozen=True)
class RefreshResult:
    status: Literal["rotated", "invalid", "replayed"]
    user_id: UUID | None = None
    session_id: UUID | None = None
    refresh_token: str | None = None
    refresh_expires_at: datetime | None = None
