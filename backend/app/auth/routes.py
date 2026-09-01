from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.config import AuthConfig
from app.auth.models import LoginRequest, LogoutResponse, TokenResponse
from app.auth.repository import AuthRepository, PostgresAuthRepository
from app.auth.security import AccessClaims
from app.auth.service import AuthService
from app.errors import ApiError, ErrorResponse

router = APIRouter(prefix="/auth", tags=["authentication"])
bearer = HTTPBearer(auto_error=False)

ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Credencial ou sessao invalida"},
    403: {"model": ErrorResponse, "description": "Origem nao autorizada"},
    429: {"model": ErrorResponse, "description": "Limite de tentativas excedido"},
    503: {"model": ErrorResponse, "description": "Autenticacao indisponivel"},
}


def get_auth_config() -> AuthConfig:
    return AuthConfig.from_env()


def get_auth_repository() -> Generator[AuthRepository, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ApiError(503, "database_not_configured", "Autenticacao indisponivel")
    yield PostgresAuthRepository(database_url)


Config = Annotated[AuthConfig, Depends(get_auth_config)]
Repository = Annotated[AuthRepository, Depends(get_auth_repository)]


def get_auth_service(repository: Repository, config: Config) -> AuthService:
    return AuthService(repository, config)


Service = Annotated[AuthService, Depends(get_auth_service)]


def _validate_origin(request: Request, config: AuthConfig) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in config.allowed_origins:
        raise ApiError(403, "origin_not_allowed", "Origem da requisicao nao autorizada")


def _set_refresh_cookie(
    response: Response,
    config: AuthConfig,
    token: str,
    expires_at: datetime,
) -> None:
    now = datetime.now(UTC)
    max_age = max(0, int((expires_at - now).total_seconds()))
    response.set_cookie(
        key=config.cookie_name,
        value=token,
        max_age=max_age,
        expires=expires_at,
        path="/auth",
        secure=config.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response, config: AuthConfig) -> None:
    response.delete_cookie(
        key=config.cookie_name,
        path="/auth",
        secure=config.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: Service,
) -> AccessClaims:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(401, "invalid_access_token", "Sessao invalida ou expirada")
    return service.access_claims(credentials.credentials)


CurrentClaims = Annotated[AccessClaims, Depends(_claims)]


@router.post(
    "/login",
    response_model=TokenResponse,
    responses=ERROR_RESPONSES,
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Service,
    config: Config,
) -> TokenResponse:
    _validate_origin(request, config)
    client_ip = request.client.host if request.client else None
    session, access_token, expires_in = service.login(
        payload.email, payload.password, client_ip
    )
    _set_refresh_cookie(
        response, config, session.refresh_token, session.refresh_expires_at
    )
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        session_id=session.session_id,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses=ERROR_RESPONSES,
)
def refresh(
    request: Request,
    response: Response,
    service: Service,
    config: Config,
    refresh_token: Annotated[str | None, Cookie(alias="synergia_refresh")] = None,
) -> TokenResponse:
    _validate_origin(request, config)
    if not refresh_token:
        raise ApiError(401, "invalid_refresh_token", "Sessao invalida ou expirada")
    result, access_token, expires_in = service.refresh(refresh_token)
    assert result.refresh_token and result.refresh_expires_at and result.session_id
    _set_refresh_cookie(
        response, config, result.refresh_token, result.refresh_expires_at
    )
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        session_id=result.session_id,
    )


@router.post("/logout", response_model=LogoutResponse, responses=ERROR_RESPONSES)
def logout(
    request: Request,
    response: Response,
    claims: CurrentClaims,
    service: Service,
    config: Config,
) -> LogoutResponse:
    _validate_origin(request, config)
    revoked = service.logout(claims)
    _clear_refresh_cookie(response, config)
    return LogoutResponse(revoked_sessions=revoked)


@router.post("/logout-all", response_model=LogoutResponse, responses=ERROR_RESPONSES)
def logout_all(
    request: Request,
    response: Response,
    claims: CurrentClaims,
    service: Service,
    config: Config,
) -> LogoutResponse:
    _validate_origin(request, config)
    revoked = service.logout_all(claims)
    _clear_refresh_cookie(response, config)
    return LogoutResponse(revoked_sessions=revoked)
