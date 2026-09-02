from __future__ import annotations

import hashlib
import os
import secrets
from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.authorization import ActorContext, CurrentActor
from app.errors import ApiError, ErrorResponse

router = APIRouter(prefix="/me", tags=["profile"])

SUPPORTED_LOCALES = frozenset({"pt-BR", "en-US", "es-ES"})
ALLOWED_IMAGE_FORMATS = {
    "PNG": ("image/png", ".png"),
    "JPEG": ("image/jpeg", ".jpg"),
    "WEBP": ("image/webp", ".webp"),
}
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_DIMENSION = 1024

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Arquivo de avatar invalido"},
    401: {"model": ErrorResponse, "description": "Sessao invalida"},
    404: {"model": ErrorResponse, "description": "Perfil ou avatar ausente"},
    409: {"model": ErrorResponse, "description": "Versao desatualizada"},
    422: {"model": ErrorResponse, "description": "Preferencia invalida"},
    503: {"model": ErrorResponse, "description": "Perfil indisponivel"},
}


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NotificationPreferences(StrictRequest):
    email: bool = True
    in_app: bool = True


class ProfileUpdate(StrictRequest):
    version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    locale: Literal["pt-BR", "en-US", "es-ES"] | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    notifications: NotificationPreferences | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("o nome deve conter texto")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("fuso horario desconhecido") from exc
        return value

    @model_validator(mode="after")
    def require_change(self) -> ProfileUpdate:
        if all(
            value is None
            for value in (
                self.display_name,
                self.locale,
                self.timezone,
                self.notifications,
            )
        ):
            raise ValueError("informe ao menos uma preferencia")
        return self


class ProfileEmail(BaseModel):
    email: str
    is_primary: bool
    is_verified: bool


class EffectivePermission(BaseModel):
    key: str
    organizations: list[UUID] | None


class AvatarMetadata(BaseModel):
    media_type: str
    size_bytes: int
    sha256: str
    url: str = "/me/avatar"


class ProfileResponse(BaseModel):
    id: UUID
    status: str
    display_name: str
    emails: list[ProfileEmail]
    locale: str
    timezone: str
    notifications: NotificationPreferences
    avatar: AvatarMetadata | None
    permissions: list[EffectivePermission]
    version: int


class ProfileRepository(Protocol):
    def get(self, actor: ActorContext) -> dict | None: ...

    def update(self, actor: ActorContext, payload: ProfileUpdate) -> dict: ...

    def set_avatar(
        self,
        actor: ActorContext,
        *,
        storage_key: str,
        media_type: str,
        size_bytes: int,
        sha256: str,
    ) -> tuple[dict, str | None]: ...

    def remove_avatar(self, actor: ActorContext) -> tuple[dict, str | None]: ...

    def avatar(self, actor: ActorContext) -> dict | None: ...


class PostgresProfileRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _record_event(
        cursor,
        actor: ActorContext,
        event_key: str,
        changed_fields: list[str],
    ) -> None:
        cursor.execute(
            """
            INSERT INTO synergia.identity_access_events (
                event_key, actor_user_id, subject_user_id, session_id,
                entity_type, entity_id, payload, correlation_id
            ) VALUES (%s, %s, %s, %s, 'identity_user', %s, %s, %s)
            """,
            (
                event_key,
                actor.user_id,
                actor.user_id,
                actor.session_id,
                str(actor.user_id),
                Jsonb({"changed_fields": changed_fields}),
                actor.correlation_id,
            ),
        )

    @staticmethod
    def _profile(cursor, user_id: UUID, permissions: dict) -> dict | None:
        cursor.execute(
            """
            SELECT id, status, display_name, locale, timezone,
                   notification_preferences AS notifications,
                   avatar_media_type, avatar_size_bytes, avatar_sha256, version
            FROM synergia.identity_users WHERE id = %s
            """,
            (user_id,),
        )
        profile = cursor.fetchone()
        if profile is None:
            return None
        cursor.execute(
            """
            SELECT normalized_email AS email, is_primary, is_verified
            FROM synergia.user_emails
            WHERE user_id = %s AND disabled_at IS NULL
            ORDER BY is_primary DESC, normalized_email, id
            """,
            (user_id,),
        )
        profile["emails"] = cursor.fetchall()
        profile["avatar"] = (
            {
                "media_type": profile.pop("avatar_media_type"),
                "size_bytes": profile.pop("avatar_size_bytes"),
                "sha256": profile.pop("avatar_sha256"),
            }
            if profile["avatar_media_type"]
            else None
        )
        if profile["avatar"] is None:
            profile.pop("avatar_media_type")
            profile.pop("avatar_size_bytes")
            profile.pop("avatar_sha256")
        profile["permissions"] = [
            {
                "key": key,
                "organizations": None
                if None in scopes
                else sorted(scopes, key=str),
            }
            for key, scopes in sorted(permissions.items())
        ]
        return profile

    def get(self, actor: ActorContext) -> dict | None:
        with self._connect() as connection, connection.cursor() as cursor:
            return self._profile(cursor, actor.user_id, actor.permissions)

    def update(self, actor: ActorContext, payload: ProfileUpdate) -> dict:
        changes = payload.model_dump(exclude={"version"}, exclude_none=True)
        columns = {
            "display_name": payload.display_name,
            "locale": payload.locale,
            "timezone": payload.timezone,
            "notification_preferences": Jsonb(payload.notifications.model_dump())
            if payload.notifications
            else None,
        }
        assignments = [
            f"{key} = %s" for key, value in columns.items() if value is not None
        ]
        values = [value for value in columns.values() if value is not None]
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE synergia.identity_users
                SET {', '.join(assignments)}, version = version + 1,
                    updated_at = now()
                WHERE id = %s AND version = %s AND status = 'active'
                RETURNING id
                """,
                (*values, actor.user_id, payload.version),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "SELECT version, status FROM synergia.identity_users WHERE id = %s",
                    (actor.user_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ApiError(404, "profile_not_found", "Perfil nao encontrado")
                if row["status"] != "active":
                    raise ApiError(409, "profile_inactive", "Perfil nao esta ativo")
                raise ApiError(409, "profile_version_conflict", "Perfil desatualizado")
            self._record_event(
                cursor,
                actor,
                "profile.updated",
                sorted(changes),
            )
            result = self._profile(cursor, actor.user_id, actor.permissions)
            assert result is not None
            return result

    def set_avatar(
        self,
        actor: ActorContext,
        *,
        storage_key: str,
        media_type: str,
        size_bytes: int,
        sha256: str,
    ) -> tuple[dict, str | None]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT avatar_storage_key FROM synergia.identity_users
                WHERE id = %s AND status = 'active' FOR UPDATE
                """,
                (actor.user_id,),
            )
            current = cursor.fetchone()
            if current is None:
                raise ApiError(404, "profile_not_found", "Perfil nao encontrado")
            cursor.execute(
                """
                UPDATE synergia.identity_users
                SET avatar_storage_key = %s, avatar_media_type = %s,
                    avatar_size_bytes = %s, avatar_sha256 = %s,
                    avatar_updated_at = now(), version = version + 1,
                    updated_at = now()
                WHERE id = %s AND status = 'active'
                RETURNING id
                """,
                (
                    storage_key,
                    media_type,
                    size_bytes,
                    sha256,
                    actor.user_id,
                ),
            )
            self._record_event(cursor, actor, "profile.avatar_updated", ["avatar"])
            result = self._profile(cursor, actor.user_id, actor.permissions)
            assert result is not None
            return result, current["avatar_storage_key"]

    def remove_avatar(self, actor: ActorContext) -> tuple[dict, str | None]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT avatar_storage_key FROM synergia.identity_users
                WHERE id = %s AND avatar_storage_key IS NOT NULL FOR UPDATE
                """,
                (actor.user_id,),
            )
            current = cursor.fetchone()
            if current is None:
                raise ApiError(404, "avatar_not_found", "Avatar nao encontrado")
            cursor.execute(
                """
                UPDATE synergia.identity_users
                SET avatar_storage_key = NULL, avatar_media_type = NULL,
                    avatar_size_bytes = NULL, avatar_sha256 = NULL,
                    avatar_updated_at = NULL, version = version + 1,
                    updated_at = now()
                WHERE id = %s AND avatar_storage_key IS NOT NULL
                """,
                (actor.user_id,),
            )
            self._record_event(cursor, actor, "profile.avatar_removed", ["avatar"])
            result = self._profile(cursor, actor.user_id, actor.permissions)
            assert result is not None
            return result, current["avatar_storage_key"]

    def avatar(self, actor: ActorContext) -> dict | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT avatar_storage_key AS storage_key,
                       avatar_media_type AS media_type, avatar_sha256 AS sha256
                FROM synergia.identity_users
                WHERE id = %s AND avatar_storage_key IS NOT NULL
                """,
                (actor.user_id,),
            )
            return cursor.fetchone()


def get_profile_repository() -> Generator[ProfileRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ApiError(503, "database_not_configured", "Perfil indisponivel")
    yield PostgresProfileRepository(database_url)


Repository = Annotated[ProfileRepository, Depends(get_profile_repository)]


def avatar_root() -> Path:
    root = Path(os.getenv("PROFILE_AVATAR_STORAGE_ROOT", ".data/avatars")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _avatar_path(storage_key: str) -> Path:
    root = avatar_root()
    target = (root / storage_key[:2] / storage_key).resolve()
    if not target.is_relative_to(root):
        raise ApiError(404, "avatar_not_found", "Avatar nao encontrado")
    return target


def _inspect_avatar(upload: UploadFile) -> tuple[bytes, str, str, str]:
    data = upload.file.read(MAX_AVATAR_BYTES + 1)
    if not data or len(data) > MAX_AVATAR_BYTES:
        raise ApiError(400, "avatar_size_invalid", "Tamanho de avatar invalido")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise ApiError(
            400, "avatar_content_invalid", "Conteudo de avatar invalido"
        ) from exc
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ApiError(400, "avatar_type_invalid", "Tipo de avatar nao permitido")
    media_type, extension = ALLOWED_IMAGE_FORMATS[image_format]
    declared = (upload.content_type or "").split(";", 1)[0].lower()
    if declared != media_type:
        raise ApiError(400, "avatar_media_mismatch", "Tipo declarado divergente")
    filename_extension = Path(upload.filename or "").suffix.lower()
    allowed_extensions = {extension}
    if image_format == "JPEG":
        allowed_extensions.add(".jpeg")
    if filename_extension not in allowed_extensions:
        raise ApiError(400, "avatar_extension_mismatch", "Extensao divergente")
    if width > MAX_AVATAR_DIMENSION or height > MAX_AVATAR_DIMENSION:
        raise ApiError(
            400, "avatar_dimensions_invalid", "Dimensoes de avatar invalidas"
        )
    return data, media_type, extension, hashlib.sha256(data).hexdigest()


@router.get("", response_model=ProfileResponse, responses=ERROR_RESPONSES)
def get_profile(actor: CurrentActor, repository: Repository) -> dict:
    profile = repository.get(actor)
    if profile is None:
        raise ApiError(404, "profile_not_found", "Perfil nao encontrado")
    return profile


@router.patch("", response_model=ProfileResponse, responses=ERROR_RESPONSES)
def update_profile(
    payload: ProfileUpdate,
    actor: CurrentActor,
    repository: Repository,
) -> dict:
    return repository.update(actor, payload)


@router.post(
    "/avatar",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def upload_avatar(
    actor: CurrentActor,
    repository: Repository,
    avatar: Annotated[UploadFile, File()],
) -> dict:
    data, media_type, extension, digest = _inspect_avatar(avatar)
    storage_key = f"{secrets.token_hex(24)}{extension}"
    target = _avatar_path(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    try:
        profile, previous = repository.set_avatar(
            actor,
            storage_key=storage_key,
            media_type=media_type,
            size_bytes=len(data),
            sha256=digest,
        )
    except Exception:
        target.unlink(missing_ok=True)
        raise
    if previous and previous != storage_key:
        _avatar_path(previous).unlink(missing_ok=True)
    return profile


@router.delete("/avatar", response_model=ProfileResponse, responses=ERROR_RESPONSES)
def delete_avatar(actor: CurrentActor, repository: Repository) -> dict:
    profile, previous = repository.remove_avatar(actor)
    if previous:
        _avatar_path(previous).unlink(missing_ok=True)
    return profile


@router.get("/avatar", responses=ERROR_RESPONSES)
def download_avatar(actor: CurrentActor, repository: Repository) -> Response:
    avatar = repository.avatar(actor)
    if avatar is None:
        raise ApiError(404, "avatar_not_found", "Avatar nao encontrado")
    target = _avatar_path(avatar["storage_key"])
    if not target.is_file():
        raise ApiError(404, "avatar_not_found", "Avatar nao encontrado")
    data = target.read_bytes()
    if hashlib.sha256(data).hexdigest() != avatar["sha256"]:
        raise ApiError(409, "avatar_integrity_error", "Avatar indisponivel")
    return Response(
        content=data,
        media_type=avatar["media_type"],
        headers={"Cache-Control": "private, no-store"},
    )
