"""Ingestion repositories with SQLAlchemy, and the unit of work the worker uses."""

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.ingestion.domain.chunking import Chunk
from app.modules.ingestion.domain.jobs import RUNNING, JobStatus, ProcessingJob
from app.modules.ingestion.domain.ports import ChunkVectors, DocumentGateway, StoredChunk
from app.modules.ingestion.infrastructure.models import (
    ChunkEmbeddingModel,
    DocumentChunkModel,
    ProcessingJobModel,
)
from app.shared.ids import new_id


def _job(model: ProcessingJobModel) -> ProcessingJob:
    return ProcessingJob(
        id=model.id,
        organization_id=model.organization_id,
        document_id=model.document_id,
        version_id=model.version_id,
        status=JobStatus(model.status),
        attempts=model.attempts,
        created_at=model.created_at,
        updated_at=model.updated_at,
        error=model.error,
        locked_until=model.locked_until,
        started_at=model.started_at,
        finished_at=model.finished_at,
        pages_total=model.pages_total,
        pages_done=model.pages_done,
        ocr_pages=model.ocr_pages,
        chunk_count=model.chunk_count,
    )


class SqlJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_pending(self, job: ProcessingJob) -> ProcessingJob:
        values = {
            "id": job.id,
            "organization_id": job.organization_id,
            "document_id": job.document_id,
            "version_id": job.version_id,
            "status": JobStatus.PENDING.value,
            "attempts": 0,
            "pages_done": 0,
            "ocr_pages": 0,
            "chunk_count": 0,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
        upsert = pg_insert(ProcessingJobModel).values(values)
        statement = upsert.on_conflict_do_update(
            index_elements=[ProcessingJobModel.version_id],
            set_={
                "status": JobStatus.PENDING.value,
                "attempts": 0,
                "error": None,
                "locked_until": None,
                "started_at": None,
                "finished_at": None,
                "pages_total": None,
                "pages_done": 0,
                "ocr_pages": 0,
                "chunk_count": 0,
                "updated_at": job.updated_at,
            },
        ).returning(ProcessingJobModel)
        model = (await self._session.execute(statement)).scalar_one()
        return _job(model)

    async def get(self, organization_id: UUID, job_id: UUID) -> ProcessingJob | None:
        model = await self._session.scalar(
            select(ProcessingJobModel).where(
                ProcessingJobModel.organization_id == organization_id,
                ProcessingJobModel.id == job_id,
            )
        )
        return _job(model) if model else None

    async def latest_for_document(
        self, organization_id: UUID, document_id: UUID
    ) -> ProcessingJob | None:
        # A version's job is created when it is uploaded: the newest job is the newest version's.
        model = await self._session.scalar(
            select(ProcessingJobModel)
            .where(
                ProcessingJobModel.organization_id == organization_id,
                ProcessingJobModel.document_id == document_id,
            )
            .order_by(ProcessingJobModel.created_at.desc(), ProcessingJobModel.id.desc())
            .limit(1)
        )
        return _job(model) if model else None

    async def claim(
        self, organization_id: UUID, job_id: UUID, *, now: datetime, until: datetime
    ) -> ProcessingJob | None:
        # One statement: if two workers race, PostgreSQL lets only one UPDATE match the row.
        statement = (
            update(ProcessingJobModel)
            .where(
                ProcessingJobModel.organization_id == organization_id,
                ProcessingJobModel.id == job_id,
                or_(
                    ProcessingJobModel.status == JobStatus.PENDING.value,
                    (ProcessingJobModel.status.in_([s.value for s in RUNNING]))
                    & (ProcessingJobModel.locked_until < now),
                ),
            )
            .values(
                status=JobStatus.EXTRACTING.value,
                attempts=ProcessingJobModel.attempts + 1,
                locked_until=until,
                started_at=now,
                error=None,
                pages_done=0,
                ocr_pages=0,
                updated_at=now,
            )
            .returning(ProcessingJobModel)
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return _job(model) if model else None

    async def heartbeat(
        self,
        organization_id: UUID,
        job_id: UUID,
        *,
        status: JobStatus,
        until: datetime,
        pages_total: int | None,
        pages_done: int,
        ocr_pages: int,
    ) -> None:
        await self._session.execute(
            update(ProcessingJobModel)
            .where(
                ProcessingJobModel.organization_id == organization_id,
                ProcessingJobModel.id == job_id,
            )
            .values(
                status=status.value,
                locked_until=until,
                pages_total=pages_total,
                pages_done=pages_done,
                ocr_pages=ocr_pages,
            )
        )

    async def finish(
        self,
        organization_id: UUID,
        job_id: UUID,
        *,
        status: JobStatus,
        now: datetime,
        error: str | None = None,
        chunk_count: int = 0,
    ) -> None:
        await self._session.execute(
            update(ProcessingJobModel)
            .where(
                ProcessingJobModel.organization_id == organization_id,
                ProcessingJobModel.id == job_id,
            )
            .values(
                status=status.value,
                error=error,
                chunk_count=chunk_count,
                locked_until=None,
                finished_at=now,
                updated_at=now,
            )
        )

    async def release(
        self, organization_id: UUID, job_id: UUID, *, now: datetime, error: str
    ) -> None:
        await self._session.execute(
            update(ProcessingJobModel)
            .where(
                ProcessingJobModel.organization_id == organization_id,
                ProcessingJobModel.id == job_id,
            )
            .values(status=JobStatus.PENDING.value, locked_until=None, error=error, updated_at=now)
        )

    async def touch(self, organization_id: UUID, job_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(ProcessingJobModel)
            .where(
                ProcessingJobModel.organization_id == organization_id,
                ProcessingJobModel.id == job_id,
            )
            .values(updated_at=now)
        )


class SqlChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_version(
        self,
        organization_id: UUID,
        document_id: UUID,
        version_id: UUID,
        chunks: Sequence[Chunk],
        embeddings: ChunkVectors | None = None,
    ) -> None:
        # All of the document's chunks go: this version's (a re-run) and older versions'.
        await self._session.execute(
            delete(DocumentChunkModel).where(
                DocumentChunkModel.organization_id == organization_id,
                DocumentChunkModel.document_id == document_id,
            )
        )
        if embeddings is not None and len(embeddings.vectors) != len(chunks):
            raise ValueError("one embedding per chunk is required")
        ids = [new_id() for _ in chunks]
        if chunks:
            await self._session.execute(
                insert(DocumentChunkModel),
                [
                    {
                        "id": chunk_id,
                        "organization_id": organization_id,
                        "document_id": document_id,
                        "version_id": version_id,
                        "position": chunk.position,
                        "content": chunk.content,
                        "section": chunk.section,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "token_count": chunk.token_count,
                    }
                    for chunk_id, chunk in zip(ids, chunks, strict=True)
                ],
            )
        if chunks and embeddings is not None:
            await self._session.execute(
                insert(ChunkEmbeddingModel),
                [
                    {
                        "id": new_id(),
                        "organization_id": organization_id,
                        "document_id": document_id,
                        "chunk_id": chunk_id,
                        "model": embeddings.model,
                        "embedding": vector,
                    }
                    for chunk_id, vector in zip(ids, embeddings.vectors, strict=True)
                ],
            )

    async def list_for_document(
        self, organization_id: UUID, document_id: UUID, *, limit: int, after_position: int | None
    ) -> list[StoredChunk]:
        query = (
            select(DocumentChunkModel)
            .where(
                DocumentChunkModel.organization_id == organization_id,
                DocumentChunkModel.document_id == document_id,
            )
            .order_by(DocumentChunkModel.position)
            .limit(limit)
        )
        if after_position is not None:
            query = query.where(DocumentChunkModel.position > after_position)
        return [
            StoredChunk(
                id=model.id,
                document_id=model.document_id,
                version_id=model.version_id,
                chunk=Chunk(
                    position=model.position,
                    content=model.content,
                    section=model.section,
                    page_start=model.page_start,
                    page_end=model.page_end,
                    token_count=model.token_count,
                ),
            )
            for model in await self._session.scalars(query)
        ]


class SqlProcessingUnitOfWork:
    """The repositories of one transaction (see SqlUnitOfWorkFactory)."""

    def __init__(self, session: AsyncSession, documents: DocumentGateway) -> None:
        self.jobs = SqlJobRepository(session)
        self.chunks = SqlChunkRepository(session)
        self.documents = documents

    async def __aenter__(self) -> "SqlProcessingUnitOfWork":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class SqlUnitOfWorkFactory:
    """`async with factory(organization_id) as uow:` is one short transaction inside that
    organization: it sets the RLS context, and commits on the way out (or rolls back on error).

    `documents_for` builds the documents gateway for the session (the documents module's code,
    passed in by whoever wires the worker, so ingestion does not import its internals).
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        documents_for: Callable[[AsyncSession], DocumentGateway],
    ) -> None:
        self._sessions = sessions
        self._documents_for = documents_for

    @asynccontextmanager
    async def __call__(self, organization_id: UUID) -> AsyncIterator[SqlProcessingUnitOfWork]:
        async with self._sessions() as session, session.begin():
            await SqlTenantContext(session).set_organization(organization_id)
            yield SqlProcessingUnitOfWork(session, self._documents_for(session))
