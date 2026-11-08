"""The processing pipeline with in-memory fakes (stage 5).

Criterion: killing the worker halfway and starting it again leaves the document neither stuck
nor duplicated. Here the "kill" is a run that claims the job and never finishes; the claim
then expires and the next run does the whole job, replacing (not adding) chunks.
"""

from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from app.modules.documents.domain.entities import DocumentStatus, FileKind
from app.modules.extraction.domain.text import PageText, TextBlock
from app.modules.ingestion.application.jobs import GetProcessingStatus, ScheduleProcessing
from app.modules.ingestion.application.process_version import Outcome, ProcessDocumentVersion
from app.modules.ingestion.domain.chunking import Chunk, ChunkingOptions
from app.modules.ingestion.domain.jobs import LEASE, MAX_ATTEMPTS, RUNNING, JobStatus, ProcessingJob
from app.modules.ingestion.domain.ports import DocumentRef, StoredChunk, VersionToProcess
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from app.shared.ids import new_id
from tests.fakes import FakeJobQueue

T0 = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
ORG = new_id()
DOC = new_id()
VERSION = new_id()


class Jobs:
    def __init__(self) -> None:
        self.items: dict[UUID, ProcessingJob] = {}

    async def upsert_pending(self, job: ProcessingJob) -> ProcessingJob:
        existing = next((j for j in self.items.values() if j.version_id == job.version_id), None)
        if existing:
            job = replace(existing, status=JobStatus.PENDING, attempts=0, error=None)
        self.items[job.id] = job
        return job

    async def get(self, organization_id: UUID, job_id: UUID) -> ProcessingJob | None:
        job = self.items.get(job_id)
        return job if job and job.organization_id == organization_id else None

    async def latest_for_document(
        self, organization_id: UUID, document_id: UUID
    ) -> ProcessingJob | None:
        jobs = [j for j in self.items.values() if j.document_id == document_id]
        return max(jobs, key=lambda j: j.created_at) if jobs else None

    async def claim(
        self, organization_id: UUID, job_id: UUID, *, now: datetime, until: datetime
    ) -> ProcessingJob | None:
        job = await self.get(organization_id, job_id)
        if job is None:
            return None
        expired = job.status in RUNNING and job.locked_until is not None and job.locked_until < now
        if job.status is not JobStatus.PENDING and not expired:
            return None
        job = replace(
            job, status=JobStatus.EXTRACTING, attempts=job.attempts + 1, locked_until=until
        )
        self.items[job.id] = job
        return job

    async def heartbeat(self, organization_id: UUID, job_id: UUID, **values: object) -> None:
        job = self.items[job_id]
        self.items[job_id] = replace(
            job,
            status=values["status"],  # type: ignore[arg-type]
            locked_until=values["until"],  # type: ignore[arg-type]
            pages_done=values["pages_done"],  # type: ignore[arg-type]
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
        job = self.items[job_id]
        self.items[job_id] = replace(
            job, status=status, error=error, chunk_count=chunk_count, locked_until=None
        )

    async def release(
        self, organization_id: UUID, job_id: UUID, *, now: datetime, error: str
    ) -> None:
        self.items[job_id] = replace(
            self.items[job_id], status=JobStatus.PENDING, locked_until=None, error=error
        )

    async def touch(self, organization_id: UUID, job_id: UUID, now: datetime) -> None:
        self.items[job_id] = replace(self.items[job_id], updated_at=now)


class Chunks:
    def __init__(self) -> None:
        self.items: list[StoredChunk] = []
        self.replacements = 0

    async def replace_for_version(
        self, organization_id: UUID, document_id: UUID, version_id: UUID, chunks: Sequence[Chunk]
    ) -> None:
        self.replacements += 1
        self.items = [c for c in self.items if c.document_id != document_id]
        self.items += [StoredChunk(new_id(), document_id, version_id, chunk) for chunk in chunks]

    async def list_for_document(
        self, organization_id: UUID, document_id: UUID, *, limit: int, after_position: int | None
    ) -> list[StoredChunk]:
        return [c for c in self.items if c.document_id == document_id][:limit]


class Documents:
    def __init__(self) -> None:
        self.status: DocumentStatus = DocumentStatus.PENDING
        self.deleted = False

    async def find(self, organization_id: UUID, document_id: UUID) -> DocumentRef | None:
        return None if self.deleted else DocumentRef(DOC, None, VERSION)

    async def version_to_process(
        self, organization_id: UUID, version_id: UUID
    ) -> VersionToProcess | None:
        if self.deleted or organization_id != ORG:
            return None
        return VersionToProcess(ORG, DOC, VERSION, f"{ORG}/{new_id()}", FileKind.PDF, True)

    async def set_status(
        self, organization_id: UUID, document_id: UUID, status: DocumentStatus
    ) -> None:
        self.status = status


class World:
    def __init__(self, pages: list[PageText]) -> None:
        self.jobs = Jobs()
        self.chunks = Chunks()
        self.documents = Documents()
        self.pages = pages
        self.ocr_text: dict[int, str] = {}
        self.now = T0
        self.crash_at_page: int | None = None
        self.unreadable = False

    @asynccontextmanager
    async def uow(self, organization_id: UUID) -> AsyncIterator["World"]:
        yield self

    @contextmanager
    def open(self, path: Path, kind: FileKind) -> Iterator["World"]:
        if self.unreadable:
            raise ValueError("broken file")
        yield self

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def read_page(self, index: int) -> PageText:
        if self.crash_at_page == index:
            raise KeyboardInterrupt  # stands for the process being killed: nothing runs after
        return self.pages[index]

    def ocr_page(self, index: int) -> PageText:
        return PageText(index + 1, [TextBlock(self.ocr_text[index], index + 1)], ocr=True)

    @asynccontextmanager
    async def local_copy(self, storage_key: str) -> AsyncIterator[Path]:
        yield Path("/nonexistent/fake")

    def use_case(self) -> ProcessDocumentVersion:
        return ProcessDocumentVersion(
            self.uow,  # type: ignore[arg-type]
            self,
            self,
            options=ChunkingOptions(max_tokens=40, overlap_tokens=0),
            clock=lambda: self.now,
        )

    def add_job(self) -> ProcessingJob:
        job = ProcessingJob(new_id(), ORG, DOC, VERSION, JobStatus.PENDING, 0, T0, T0)
        self.jobs.items[job.id] = job
        return job


def text_page(number: int, *paragraphs: str) -> PageText:
    return PageText(number, [TextBlock(p, number) for p in paragraphs])


PAGES = [
    PageText(1, [TextBlock("CLÁUSULA PRIMERA", 1, heading_level=1), TextBlock("El objeto.", 1)]),
    text_page(2, "El plazo es de 30 días."),
]


async def test_processes_a_version_into_chunks() -> None:
    world = World(PAGES)
    job = world.add_job()

    result = await world.use_case().execute(ORG, job.id)

    assert (result.outcome, result.chunk_count) == (Outcome.READY, 1)
    [stored] = world.chunks.items
    assert stored.chunk.section == "CLÁUSULA PRIMERA"
    assert stored.chunk.content == "El objeto.\n\nEl plazo es de 30 días."
    assert (stored.chunk.page_start, stored.chunk.page_end) == (1, 2)
    assert world.jobs.items[job.id].status is JobStatus.READY
    assert world.documents.status is DocumentStatus.READY


async def test_scanned_pages_go_through_ocr() -> None:
    scanned = PageText(2, [], needs_ocr=True)
    world = World([text_page(1, "Texto digital."), scanned])
    world.ocr_text[1] = "Texto escaneado del anexo."
    job = world.add_job()

    await world.use_case().execute(ORG, job.id)

    assert "Texto escaneado del anexo." in world.chunks.items[0].chunk.content


async def test_a_killed_worker_leaves_no_stuck_or_duplicated_document() -> None:
    world = World(PAGES)
    job = world.add_job()
    world.crash_at_page = 1

    with pytest.raises(KeyboardInterrupt):  # the worker dies on page 2
        await world.use_case().execute(ORG, job.id)
    assert world.jobs.items[job.id].status is JobStatus.EXTRACTING
    assert world.chunks.items == []  # nothing half-written

    # The message is redelivered at once: the claim is still valid, so it is skipped.
    world.crash_at_page = None
    assert (await world.use_case().execute(ORG, job.id)).outcome is Outcome.SKIPPED

    # The API notices the expired claim and queues the job again.
    world.now = T0 + LEASE + timedelta(seconds=1)
    queue = FakeJobQueue()
    actor = Membership.create(
        id=new_id(), organization_id=ORG, user_id=new_id(), role=Role.VIEWER, now=T0
    )
    status = await GetProcessingStatus(
        world.documents, world.jobs, queue, clock=lambda: world.now
    ).execute(actor, DOC)
    assert status.requeued and queue.sent == [(ORG, job.id)]

    result = await world.use_case().execute(ORG, job.id)
    assert result.outcome is Outcome.READY
    assert world.jobs.items[job.id].attempts == 2

    # And running it once more (another redelivery) changes nothing.
    world.jobs.items[job.id] = replace(world.jobs.items[job.id], status=JobStatus.PENDING)
    await world.use_case().execute(ORG, job.id)
    assert len(world.chunks.items) == 1


async def test_a_job_is_not_claimed_twice() -> None:
    world = World(PAGES)
    job = world.add_job()
    await world.jobs.claim(ORG, job.id, now=T0, until=T0 + LEASE)  # another worker has it

    result = await world.use_case().execute(ORG, job.id)

    assert result.outcome is Outcome.SKIPPED
    assert world.chunks.items == []


async def test_a_job_of_another_organization_is_never_processed() -> None:
    world = World(PAGES)
    job = world.add_job()

    result = await world.use_case().execute(new_id(), job.id)

    assert result.outcome is Outcome.SKIPPED
    assert world.jobs.items[job.id].status is JobStatus.PENDING


async def test_unreadable_file_fails_with_a_message() -> None:
    world = World(PAGES)
    world.unreadable = True
    job = world.add_job()

    result = await world.use_case().execute(ORG, job.id)

    assert result.outcome is Outcome.FAILED
    assert world.jobs.items[job.id].error == "No se pudo abrir el archivo"
    assert world.documents.status is DocumentStatus.FAILED


async def test_document_deleted_meanwhile_is_skipped() -> None:
    world = World(PAGES)
    world.documents.deleted = True
    job = world.add_job()

    assert (await world.use_case().execute(ORG, job.id)).outcome is Outcome.SKIPPED
    assert world.chunks.items == []


async def test_gives_up_after_too_many_attempts() -> None:
    world = World(PAGES)
    job = world.add_job()
    world.jobs.items[job.id] = replace(job, attempts=MAX_ATTEMPTS)

    result = await world.use_case().execute(ORG, job.id)

    assert result.outcome is Outcome.FAILED
    assert world.documents.status is DocumentStatus.FAILED


async def test_unexpected_error_releases_the_job_for_a_retry() -> None:
    world = World(PAGES)
    job = world.add_job()

    async def broken(*args: object, **kwargs: object) -> None:
        raise ConnectionError("database down")

    world.chunks.replace_for_version = broken  # type: ignore[method-assign]

    with pytest.raises(ConnectionError):
        await world.use_case().execute(ORG, job.id)

    released = world.jobs.items[job.id]
    assert released.status is JobStatus.PENDING
    assert released.error is not None and "ConnectionError" in released.error


async def test_schedule_creates_or_resets_the_job_and_queues_it() -> None:
    jobs = Jobs()
    queue = FakeJobQueue()
    scheduler = ScheduleProcessing(jobs, queue, clock=lambda: T0)

    await scheduler.schedule(ORG, DOC, VERSION)
    [job] = jobs.items.values()
    jobs.items[job.id] = replace(job, status=JobStatus.FAILED, error="x")
    await scheduler.schedule(ORG, DOC, VERSION)  # reprocess: same job, reset

    [again] = jobs.items.values()
    assert (again.id, again.status, again.error) == (job.id, JobStatus.PENDING, None)
    assert queue.sent == [(ORG, job.id), (ORG, job.id)]
