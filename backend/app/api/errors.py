"""Errores homogéneos de la API (`PLAN.md` §10)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse, Response


class ApiError(Exception):
    """Error de dominio con código estable y estado HTTP."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Construye el sobre de error que consume el frontend."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="La petición no es válida.",
        details={"errors": jsonable_encoder(exc.errors())},
    )


async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
    return error_response(
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
    )


async def api_exception_handler(request: Request, exc: Exception) -> Response:
    """Adaptador con la firma que espera Starlette."""
    if not isinstance(exc, ApiError):
        raise exc
    return await api_error_handler(request, exc)


async def validation_exception_handler(request: Request, exc: Exception) -> Response:
    """Adaptador con la firma que espera Starlette."""
    if not isinstance(exc, RequestValidationError):
        raise exc
    return await validation_error_handler(request, exc)


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    """Adaptador con la firma que espera Starlette."""
    if not isinstance(exc, HTTPException):
        raise exc
    return await http_error_handler(request, exc)
