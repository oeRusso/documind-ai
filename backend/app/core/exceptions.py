"""Centralized error handling: every error leaves the API with the same shape.

{ "error": { "code": "...", "message": "...", "request_id": "..." } }
"""

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import REQUEST_ID_HEADER, current_request_id
from app.shared.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    TooManyRequestsError,
    UnauthorizedError,
    UnsupportedMediaTypeError,
    ValidationError,
)

logger = structlog.get_logger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# Most specific class first: the first isinstance() match wins.
_DOMAIN_STATUS: list[tuple[type[DomainError], int]] = [
    (UnauthorizedError, status.HTTP_401_UNAUTHORIZED),
    (ForbiddenError, status.HTTP_403_FORBIDDEN),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (PayloadTooLargeError, status.HTTP_413_CONTENT_TOO_LARGE),
    (UnsupportedMediaTypeError, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
    (ValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (TooManyRequestsError, status.HTTP_429_TOO_MANY_REQUESTS),
    (ServiceUnavailableError, status.HTTP_503_SERVICE_UNAVAILABLE),
]

_HTTP_CODES: dict[int, tuple[str, str]] = {
    404: ("not_found", "Recurso no encontrado"),
    405: ("method_not_allowed", "Método no permitido"),
    411: ("length_required", "Falta el tamaño del pedido (Content-Length)"),
    413: ("payload_too_large", "El archivo es demasiado grande"),
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = current_request_id()
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, request_id=request_id, details=details)
    )
    headers = dict(headers or {})
    if request_id:
        headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        status_code = next(
            (code for cls, code in _DOMAIN_STATUS if isinstance(exc, cls)),
            status.HTTP_400_BAD_REQUEST,
        )
        # RFC 9110: a 401 says how to authenticate.
        headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
        if isinstance(exc, TooManyRequestsError):
            headers = {"Retry-After": str(exc.retry_after_seconds)}
        return error_response(
            status_code, exc.code, exc.message, details=exc.details, headers=headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = _HTTP_CODES.get(exc.status_code, ("http_error", str(exc.detail)))
        return error_response(exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
            for err in exc.errors()
        ]
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", "Datos inválidos", details
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # Full traceback goes to the logs; the client only gets a generic message.
        logger.exception("unhandled_error", exc_type=type(exc).__name__)
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Error interno del servidor"
        )
