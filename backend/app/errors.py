from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException

from app.http_security import HttpSecurityConfig, apply_security_headers
from app.observability.telemetry import safe_log


class ErrorDetail(BaseModel):
    code: str = Field(description="Código estável e legível por máquinas")
    message: str = Field(description="Descrição segura para apresentação")
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers or {}


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        _log_failure(request, exc.status_code, exc.code)
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            details = dict(exc.detail)
            code = str(details.pop("code", "http_error"))
            message = str(details.pop("message", "A requisição não pôde ser atendida"))
        else:
            code = "not_found" if exc.status_code == 404 else "http_error"
            message = str(exc.detail)
            details = {}
        _log_failure(request, exc.status_code, code)
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=_body(code, message, details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        issues = [
            {
                "location": [str(item) for item in error["loc"]],
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        _log_failure(request, 422, "request_validation_error")
        return JSONResponse(
            status_code=422,
            content=_body(
                "request_validation_error",
                "Parâmetros da requisição inválidos",
                {"issues": issues},
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        safe_log(
            logging.ERROR,
            "http.request.unhandled_error",
            exception_type=type(exc).__name__,
        )
        response = JSONResponse(
            status_code=500,
            content=_body(
                "internal_error",
                "Ocorreu uma falha interna ao processar a requisição",
            ),
        )
        apply_security_headers(
            MutableHeaders(raw=response.raw_headers),
            request.url.path,
            HttpSecurityConfig.from_env(),
        )
        return response


def _log_failure(request: Request, status_code: int, error_code: str) -> None:
    route = request.scope.get("route")
    safe_log(
        logging.ERROR if status_code >= 500 else logging.WARNING,
        "http.request.failed",
        method=request.method,
        route=getattr(route, "path", "unmatched"),
        status_code=status_code,
        error_code=error_code,
        outcome="failure",
    )
