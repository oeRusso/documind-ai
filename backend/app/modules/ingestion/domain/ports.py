"""Interfaces (ports) of the ingestion module. Implementations: infrastructure/ and tests/fakes."""

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.modules.documents.domain.entities import DocumentStatus, FileKind
from app.modules.extraction.domain.text import PageText
from app.modules.ingestion.domain.chunking import Chunk
from app.modules.ingestion.domain.jobs import JobStatus, ProcessingJob


@dataclass(frozen=True, slots=True)
class StoredChunk:
    id: UUID
    document_id: UUID
    version_id: UUID
    chunk: Chunk


class JobRepository(Protocol):
    async def upsert_pending(self, job: ProcessingJob) -> ProcessingJob:
        """Create the job of a version, or reset it to pending if it already exists."""
        ...

    async def get(self, organization_id: UUID, job_id: UUID) -> ProcessingJob | None: ...

    async def latest_for_document(
        self, organization_id: UUID, document_id: UUID
    ) -> ProcessingJob | None:
        """The job of the document's newest version."""
        ...

    async def claim(
        self, organization_id: UUID, job_id: UUID, *, now: datetime, until: datetime
    ) -> ProcessingJob | None:
        """Take the job if it is pending or its claim expired. None if someone else has it."""
        ...

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
    ) -> None: ...

    async def finish(
        self,
        organization_id: UUID,
        job_id: UUID,
        *,
        status: JobStatus,
        now: datetime,
        error: str | None = None,
        chunk_count: int = 0,
    ) -> None: ...

    async def release(
        self, organization_id: UUID, job_id: UUID, *, now: datetime, error: str
    ) -> None:
        """Give the job back (pending again) after an unexpected error, so a retry can claim it."""
        ...

    async def touch(self, organization_id: UUID, job_id: UUID, now: datetime) -> None:
        """Mark a re-queued job as recently queued (so it is not re-queued again at once)."""
        ...


@dataclass(frozen=True, slots=True)
class ChunkVectors:
    """The embeddings of a list of chunks (same order), all computed with one model."""

    model: str
    vectors: list[list[float]]


class ChunkRepository(Protocol):
    async def replace_for_version(
        self,
        organization_id: UUID,
        document_id: UUID,
        version_id: UUID,
        chunks: Sequence[Chunk],
        embeddings: ChunkVectors | None = None,
    ) -> None:
        """Delete the document's chunks (this version's and older ones') and insert these,
        with their embeddings when given (the old embeddings go with the old chunks)."""
        ...

    async def list_for_document(
        self, organization_id: UUID, document_id: UUID, *, limit: int, after_position: int | None
    ) -> list[StoredChunk]: ...


@dataclass(frozen=True, slots=True)
class VersionToProcess:
    organization_id: UUID
    document_id: UUID
    version_id: UUID
    storage_key: str
    kind: FileKind
    is_latest: bool


@dataclass(frozen=True, slots=True)
class DocumentRef:
    document_id: UUID
    created_by_id: UUID | None
    latest_version_id: UUID


class DocumentGateway(Protocol):
    """What ingestion needs from the documents module (implemented by documents' application)."""

    async def find(self, organization_id: UUID, document_id: UUID) -> DocumentRef | None:
        """A live document of this organization, or None (missing, deleted, or someone else's)."""
        ...

    async def version_to_process(
        self, organization_id: UUID, version_id: UUID
    ) -> VersionToProcess | None:
        """None if the version or its document no longer exist (deleted meanwhile)."""
        ...

    async def set_status(
        self, organization_id: UUID, document_id: UUID, status: DocumentStatus
    ) -> None: ...


class ProcessingUnitOfWork(Protocol):
    """One short transaction inside one organization (RLS context set), with its repositories."""

    @property
    def jobs(self) -> JobRepository: ...

    @property
    def chunks(self) -> ChunkRepository: ...

    @property
    def documents(self) -> DocumentGateway: ...

    async def __aenter__(self) -> "ProcessingUnitOfWork": ...

    async def __aexit__(self, *exc_info: object) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(
        self, organization_id: UUID
    ) -> AbstractAsyncContextManager[ProcessingUnitOfWork]: ...


class DocumentReader(Protocol):
    """An opened document, read one page at a time (so progress and timing are per page)."""

    @property
    def page_count(self) -> int: ...

    def read_page(self, index: int) -> PageText: ...

    def ocr_page(self, index: int) -> PageText: ...


class TextExtractor(Protocol):
    def open(self, path: Path, kind: FileKind) -> AbstractContextManager[DocumentReader]: ...


class LocalFiles(Protocol):
    """A local path for a stored file (the storage may be remote one day)."""

    def local_copy(self, storage_key: str) -> AbstractAsyncContextManager[Path]: ...


class JobQueue(Protocol):
    """Sends a job to the workers. The API queues it only after its transaction committed."""

    def enqueue(self, organization_id: UUID, job_id: UUID) -> None: ...
