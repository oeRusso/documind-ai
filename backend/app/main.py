"""App factory: builds the FastAPI app and wires middleware, error handlers and routers.

Run with:  uvicorn app.main:create_app --factory
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI

from app.ai.concurrency import GenerationQueue
from app.ai.providers.factory import build_embedding_provider, build_llm_provider
from app.ai.providers.llm import LLMProvider, LLMServiceError
from app.core.body_limit import MULTIPART_OVERHEAD, body_limit_middleware
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.core.request_context import request_context_middleware
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.mail.smtp import build_mailer
from app.infrastructure.queue.celery_app import create_celery
from app.infrastructure.rate_limit import InMemoryRateLimiter
from app.infrastructure.storage.filesystem import FilesystemStorage
from app.modules.auth.presentation.router import router as auth_router
from app.modules.documents.presentation.router import router as documents_router
from app.modules.ingestion.infrastructure.job_queue import CeleryJobQueue, LoggingJobQueue
from app.modules.ingestion.presentation.router import router as processing_router
from app.modules.knowledge.presentation.chat_router import router as chat_router
from app.modules.knowledge.presentation.router import router as search_router
from app.modules.organizations.presentation.invitations_router import router as invitations_router
from app.modules.organizations.presentation.members_router import router as members_router
from app.modules.organizations.presentation.router import router as organizations_router

API_V1_PREFIX = "/api/v1"

logger = structlog.get_logger("app.main")


async def _warm_up(llm: LLMProvider) -> None:
    """Load the model while the API starts, so the first question does not wait for it."""
    try:
        await llm.warm_up()
        logger.info("llm_ready", model=llm.model)
    except LLMServiceError as exc:
        # Not fatal: Ollama may still be starting; the first question will load it.
        logger.warning("llm_warm_up_failed", model=llm.model, error=str(exc))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    engine = create_engine(str(settings.database_url))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        warm_up = asyncio.create_task(_warm_up(app.state.llm)) if app.state.llm else None
        yield
        if warm_up:
            warm_up.cancel()
        await engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.mailer = build_mailer(settings)
    app.state.rate_limiter = InMemoryRateLimiter()
    app.state.storage = FilesystemStorage(settings.storage_path)
    app.state.embeddings = build_embedding_provider(settings)
    app.state.llm = build_llm_provider(settings)
    app.state.generation_queue = GenerationQueue(settings.llm_max_concurrency)
    app.state.job_queue = (
        CeleryJobQueue(create_celery(settings.celery_broker_url))
        if settings.celery_broker_url
        else LoggingJobQueue()
    )

    # The last one added runs first: the request id exists before the size check answers.
    app.middleware("http")(body_limit_middleware(settings.max_upload_bytes + MULTIPART_OVERHEAD))
    app.middleware("http")(request_context_middleware)
    register_exception_handlers(app)

    api_v1 = APIRouter(prefix=API_V1_PREFIX)
    api_v1.include_router(auth_router)
    api_v1.include_router(organizations_router)
    api_v1.include_router(members_router)
    api_v1.include_router(invitations_router)
    api_v1.include_router(documents_router)
    api_v1.include_router(processing_router)
    api_v1.include_router(search_router)
    api_v1.include_router(chat_router)

    app.include_router(health_router)
    app.include_router(api_v1)
    return app
