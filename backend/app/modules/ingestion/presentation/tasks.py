"""Celery tasks: the worker's entry points (like routers are the API's).

Celery tasks are plain (synchronous) functions; each one runs the async use case with
`asyncio.run`, using its own database engine (no pool shared with other processes).
"""

import asyncio
from uuid import UUID

import structlog
from celery import Celery, Task
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.providers.embeddings import EmbeddingProvider
from app.ai.providers.factory import build_embedding_provider
from app.core.config import Settings
from app.infrastructure.queue.celery_app import PROCESS_VERSION_TASK, PURGE_DOCUMENTS_TASK
from app.infrastructure.storage.filesystem import FilesystemStorage
from app.jobs.purge_documents import purge_all
from app.modules.documents.application.ingestion_gateway import DocumentsForIngestion
from app.modules.documents.infrastructure.sql_repository import SqlDocumentRepository
from app.modules.extraction.infrastructure.readers import FileTextExtractor
from app.modules.ingestion.application.process_version import ProcessDocumentVersion
from app.modules.ingestion.domain.ports import DocumentGateway
from app.modules.ingestion.infrastructure.sql_repository import SqlUnitOfWorkFactory

logger = structlog.get_logger("app.worker")

# Retries for unexpected errors (database or disk down): after 1, 2 and 4 minutes.
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 60


def _documents_for(session: AsyncSession) -> DocumentGateway:
    return DocumentsForIngestion(SqlDocumentRepository(session))


async def process(
    settings: Settings,
    organization_id: UUID,
    job_id: UUID,
    *,
    embeddings: EmbeddingProvider | None = None,
) -> str:
    """Run one job. `embeddings` overrides the configured provider (tests use a fake one)."""
    engine = create_async_engine(str(settings.database_url), poolclass=NullPool)
    try:
        use_case = ProcessDocumentVersion(
            SqlUnitOfWorkFactory(
                async_sessionmaker(engine, expire_on_commit=False), _documents_for
            ),
            FileTextExtractor(),
            FilesystemStorage(settings.storage_path),
            embeddings=embeddings or build_embedding_provider(settings),
        )
        result = await use_case.execute(organization_id, job_id)
        return result.outcome.value
    finally:
        await engine.dispose()


def register_tasks(celery: Celery, settings: Settings) -> None:
    @celery.task(name=PROCESS_VERSION_TASK, bind=True, max_retries=MAX_RETRIES)
    def process_version(self: Task, organization_id: str, job_id: str) -> str:
        try:
            return asyncio.run(process(settings, UUID(organization_id), UUID(job_id)))
        except Exception as exc:
            countdown = RETRY_BASE_SECONDS * 2**self.request.retries
            logger.warning(
                "process_version_retry", job_id=job_id, error=type(exc).__name__, in_s=countdown
            )
            raise self.retry(exc=exc, countdown=countdown) from exc

    @celery.task(name=PURGE_DOCUMENTS_TASK)
    def purge_deleted_documents() -> int:
        return asyncio.run(purge_all())
