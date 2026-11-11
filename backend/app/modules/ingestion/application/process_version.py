"""Use case: turn one document version into chunks (runs in a worker, never in the API).

    claim the job -> check the version still exists -> read every page (heartbeat after each)
    -> OCR the pages that look scanned -> clean the text -> cut into chunks
    -> compute their embeddings (stage 6, when a model is configured)
    -> in ONE transaction: replace the chunks and embeddings, mark the job ready, update the
       document.

Every step that changes the database is its own short transaction inside the organization
(`uow_factory(organization_id)` sets the RLS context), so the progress is visible from the API
while the worker is still busy.
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import structlog

from app.ai.providers.embeddings import EmbeddingProvider
from app.modules.documents.domain.entities import DocumentStatus
from app.modules.extraction.domain.normalization import normalize_pages
from app.modules.extraction.domain.text import PageText
from app.modules.ingestion.domain.chunking import Chunk, ChunkingOptions, chunk_blocks
from app.modules.ingestion.domain.jobs import LEASE, MAX_ATTEMPTS, JobStatus, ProcessingJob
from app.modules.ingestion.domain.ports import (
    ChunkVectors,
    DocumentReader,
    LocalFiles,
    ProcessingUnitOfWork,
    TextExtractor,
    UnitOfWorkFactory,
    VersionToProcess,
)
from app.shared.ids import utc_now

logger = structlog.get_logger("app.ingestion")

# Chunks per call to the embedding model (a heartbeat goes between calls).
EMBEDDING_BATCH = 32


class Outcome(StrEnum):
    READY = "ready"
    FAILED = "failed"
    SKIPPED = "skipped"  # someone else has the job, it is already done, or the document is gone


class ExtractionFailedError(Exception):
    """The file cannot be read. Not retried: the message is shown to the user.

    Any other exception (database down, disk error) escapes, and the worker retries the task.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True)
class ProcessResult:
    outcome: Outcome
    chunk_count: int = 0


class ProcessDocumentVersion:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        extractor: TextExtractor,
        files: LocalFiles,
        *,
        embeddings: EmbeddingProvider | None = None,
        options: ChunkingOptions | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow = uow_factory
        self._extractor = extractor
        self._files = files
        self._embeddings = embeddings
        self._options = options or ChunkingOptions()
        self._clock = clock

    async def execute(self, organization_id: UUID, job_id: UUID) -> ProcessResult:
        log = logger.bind(organization_id=str(organization_id), job_id=str(job_id))
        now = self._clock()
        async with self._uow(organization_id) as uow:
            job = await uow.jobs.claim(organization_id, job_id, now=now, until=now + LEASE)
            if job is None:
                log.info("job_not_claimed")  # running elsewhere, finished, or not in this org
                return ProcessResult(Outcome.SKIPPED)
            if job.attempts > MAX_ATTEMPTS:
                await self._fail(uow, job, "No se pudo procesar después de varios intentos")
                return ProcessResult(Outcome.FAILED)
            # Belt and braces: the task says organization X; check the version really is X's.
            version = await uow.documents.version_to_process(organization_id, job.version_id)
            if version is None:
                await uow.jobs.finish(
                    organization_id,
                    job.id,
                    status=JobStatus.FAILED,
                    now=now,
                    error="Documento borrado",
                )
                log.info("document_gone")
                return ProcessResult(Outcome.SKIPPED)
            if version.is_latest:
                await uow.documents.set_status(
                    organization_id, version.document_id, DocumentStatus.PROCESSING
                )

        try:
            try:
                pages = await self._read(job, version, log)
            except FileNotFoundError as exc:  # permanent: retrying will not bring it back
                raise ExtractionFailedError("No se encontró el archivo guardado") from exc
            await self._heartbeat(
                job, JobStatus.CHUNKING, len(pages), len(pages), _ocr_count(pages)
            )
            chunks = chunk_blocks(normalize_pages(pages), self._options)
            vectors = await self._embed(job, chunks, len(pages), _ocr_count(pages))
            await self._save(job, version, chunks, vectors)
        except ExtractionFailedError as exc:
            async with self._uow(organization_id) as uow:
                await self._fail(uow, job, exc.message, version)
            log.warning("extraction_failed", error=exc.message)
            return ProcessResult(Outcome.FAILED)
        except Exception as exc:
            # Unexpected (database, disk): give the job back and let the worker retry the task.
            await self._release(job, f"Error temporal ({type(exc).__name__}); se reintenta")
            raise
        log.info("document_ready", chunks=len(chunks), pages=len(pages))
        return ProcessResult(Outcome.READY, len(chunks))

    async def _read(
        self,
        job: ProcessingJob,
        version: VersionToProcess,
        log: structlog.typing.FilteringBoundLogger,
    ) -> list[PageText]:
        started = time.perf_counter()
        async with self._files.local_copy(version.storage_key) as path:
            # `with extractor.open(...)` written by hand: opening and closing are blocking calls
            # that run in a thread, while the loop in between awaits the database.
            try:
                context = self._extractor.open(path, version.kind)
                reader: DocumentReader = await asyncio.to_thread(context.__enter__)
            except Exception as exc:
                raise ExtractionFailedError("No se pudo abrir el archivo") from exc
            try:
                total = reader.page_count
                pages: list[PageText] = []
                for index in range(total):
                    page_started = time.perf_counter()
                    page = await asyncio.to_thread(reader.read_page, index)
                    pages.append(page)
                    log.info(
                        "page_extracted",
                        page=index + 1,
                        ms=round((time.perf_counter() - page_started) * 1000, 1),
                        chars=page.char_count,
                        needs_ocr=page.needs_ocr,
                    )
                    await self._heartbeat(job, JobStatus.EXTRACTING, total, index + 1, 0)

                scanned = [i for i, page in enumerate(pages) if page.needs_ocr]
                for done, index in enumerate(scanned, start=1):
                    await self._heartbeat(job, JobStatus.OCR, total, total, done - 1)
                    page_started = time.perf_counter()
                    pages[index] = await asyncio.to_thread(reader.ocr_page, index)
                    log.info(
                        "page_ocr",
                        page=index + 1,
                        ms=round((time.perf_counter() - page_started) * 1000, 1),
                        chars=pages[index].char_count,
                    )
            except ExtractionFailedError:
                raise
            except Exception as exc:
                raise ExtractionFailedError("No se pudo leer el contenido del archivo") from exc
            finally:
                await asyncio.to_thread(context.__exit__, None, None, None)

        seconds = time.perf_counter() - started
        log.info(
            "document_extracted",
            pages=len(pages),
            ocr_pages=_ocr_count(pages),
            seconds=round(seconds, 2),
            ms_per_page=round(seconds * 1000 / max(len(pages), 1), 1),
        )
        return pages

    async def _embed(
        self, job: ProcessingJob, chunks: list[Chunk], pages: int, ocr_pages: int
    ) -> ChunkVectors | None:
        """Vectors for every chunk, a batch at a time with a heartbeat in between.

        The section goes in front of the text: "Cláusula quinta > Plazos" helps a chunk that
        only says "treinta días" to be found by a question about deadlines.
        """
        if self._embeddings is None or not chunks:
            return None
        texts = [f"{c.section}\n\n{c.content}" if c.section else c.content for c in chunks]
        vectors: list[list[float]] = []
        started = time.perf_counter()
        for start in range(0, len(texts), EMBEDDING_BATCH):
            await self._heartbeat(job, JobStatus.EMBEDDING, pages, pages, ocr_pages)
            vectors += await self._embeddings.embed_documents(
                texts[start : start + EMBEDDING_BATCH]
            )
        logger.info(
            "chunks_embedded",
            job_id=str(job.id),
            chunks=len(chunks),
            model=self._embeddings.model.name,
            seconds=round(time.perf_counter() - started, 2),
        )
        return ChunkVectors(self._embeddings.model.name, vectors)

    async def _save(
        self,
        job: ProcessingJob,
        version: VersionToProcess,
        chunks: list[Chunk],
        vectors: ChunkVectors | None,
    ) -> None:
        """One transaction: replace the chunks (and embeddings), close the job, update the doc."""
        async with self._uow(job.organization_id) as uow:
            await uow.chunks.replace_for_version(
                job.organization_id, version.document_id, version.version_id, chunks, vectors
            )
            await uow.jobs.finish(
                job.organization_id,
                job.id,
                status=JobStatus.READY,
                now=self._clock(),
                chunk_count=len(chunks),
            )
            if version.is_latest:
                await uow.documents.set_status(
                    job.organization_id, version.document_id, DocumentStatus.READY
                )

    async def _release(self, job: ProcessingJob, message: str) -> None:
        try:
            async with self._uow(job.organization_id) as uow:
                await uow.jobs.release(
                    job.organization_id, job.id, now=self._clock(), error=message
                )
        except Exception:  # the database may be the problem: the claim expires on its own
            logger.warning("job_release_failed", job_id=str(job.id))

    async def _heartbeat(
        self, job: ProcessingJob, status: JobStatus, total: int, done: int, ocr: int
    ) -> None:
        now = self._clock()
        async with self._uow(job.organization_id) as uow:
            await uow.jobs.heartbeat(
                job.organization_id,
                job.id,
                status=status,
                until=now + LEASE,
                pages_total=total,
                pages_done=done,
                ocr_pages=ocr,
            )

    async def _fail(
        self,
        uow: ProcessingUnitOfWork,
        job: ProcessingJob,
        message: str,
        version: VersionToProcess | None = None,
    ) -> None:
        await uow.jobs.finish(
            job.organization_id, job.id, status=JobStatus.FAILED, now=self._clock(), error=message
        )
        target = version or await uow.documents.version_to_process(
            job.organization_id, job.version_id
        )
        if target is not None and target.is_latest:
            await uow.documents.set_status(
                job.organization_id, target.document_id, DocumentStatus.FAILED
            )


def _ocr_count(pages: list[PageText]) -> int:
    return sum(1 for page in pages if page.ocr)
