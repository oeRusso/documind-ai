"""App factory: builds the FastAPI app and wires middleware, error handlers and routers.

Run with:  uvicorn app.main:create_app --factory
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.core.request_context import request_context_middleware
from app.infrastructure.database.session import create_engine, create_session_factory
from app.modules.auth.presentation.router import router as auth_router
from app.modules.organizations.presentation.members_router import router as members_router
from app.modules.organizations.presentation.router import router as organizations_router

API_V1_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    engine = create_engine(str(settings.database_url))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    app.middleware("http")(request_context_middleware)
    register_exception_handlers(app)

    api_v1 = APIRouter(prefix=API_V1_PREFIX)
    api_v1.include_router(auth_router)
    api_v1.include_router(organizations_router)
    api_v1.include_router(members_router)

    app.include_router(health_router)
    app.include_router(api_v1)
    return app
