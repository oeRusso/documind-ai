"""Liveness and readiness probes. They live outside /api/v1 on purpose."""

import asyncio

import structlog
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.exceptions import ErrorResponse, error_response

router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)

_READY_TIMEOUT_SECONDS = 2.0


@router.get("/health")
async def health() -> dict[str, str]:
    """The process is alive. Does not touch the database."""
    return {"status": "ok"}


@router.get(
    "/ready",
    responses={
        status.HTTP_200_OK: {"content": {"application/json": {"example": {"status": "ready"}}}},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def ready(request: Request) -> JSONResponse:
    """The API can serve traffic: the database answers `SELECT 1`."""
    engine: AsyncEngine = request.app.state.engine
    try:
        async with asyncio.timeout(_READY_TIMEOUT_SECONDS), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # any failure means "not ready"
        logger.warning("database_not_ready", error=type(exc).__name__)
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "database_unavailable",
            "La base de datos no está disponible",
        )
    return JSONResponse({"status": "ready"})
