"""Use cases around processing jobs, run by the API inside a request (RLS context already set).

- ScheduleProcessing: create (or reset) the job of a version and queue it after the commit.
- GetProcessingStatus: the job of a document's newest version; if it is stalled (its worker died,
  or the queue was down when it was created), it is queued again right there.
- ReprocessDocument: run the pipeline again for the newest version (after a failure, or when
  the chunking rules change).
- ListChunks: the chunks of a document, in reading order.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from app.modules.documents.domain.errors import DocumentNotFoundError
from app.modules.ingestion.domain.jobs import JobStatus, ProcessingJob
from app.modules.ingestion.domain.ports import (
    ChunkRepository,
    DocumentGateway,
    JobQueue,
    JobRepository,
    StoredChunk,
)
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.permissions import (
    Permission,
    ensure_permission,
    has_permission,
)
from app.shared.errors import ForbiddenError
from app.shared.ids import new_id, utc_now

logger = structlog.get_logger("app.ingestion")


class ScheduleProcessing:
    """Implements the documents module's ProcessingScheduler port."""

    def __init__(
        self,
        jobs: JobRepository,
        queue: JobQueue,
        *,
        id_factory: Callable[[], UUID] = new_id,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._jobs = jobs
        self._queue = queue
        self._id_factory = id_factory
        self._clock = clock

    async def schedule(self, organization_id: UUID, document_id: UUID, version_id: UUID) -> None:
        now = self._clock()
        job = await self._jobs.upsert_pending(
            ProcessingJob(
                id=self._id_factory(),
                organization_id=organization_id,
                document_id=document_id,
                version_id=version_id,
                status=JobStatus.PENDING,
                attempts=0,
                created_at=now,
                updated_at=now,
            )
        )
        self._queue.enqueue(organization_id, job.id)


@dataclass(frozen=True, slots=True)
class ProcessingStatus:
    job: ProcessingJob | None
    requeued: bool = False


class GetProcessingStatus:
    def __init__(
        self,
        documents: DocumentGateway,
        jobs: JobRepository,
        queue: JobQueue,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._documents = documents
        self._jobs = jobs
        self._queue = queue
        self._clock = clock

    async def execute(self, actor: Membership, document_id: UUID) -> ProcessingStatus:
        ensure_permission(actor.role, Permission.VIEW_DOCUMENTS)
        if await self._documents.find(actor.organization_id, document_id) is None:
            raise DocumentNotFoundError()
        job = await self._jobs.latest_for_document(actor.organization_id, document_id)
        if job is None:
            return ProcessingStatus(None)
        now = self._clock()
        if job.is_stalled(now):
            # Its worker died or it was never queued: queue it again. The claim (in the worker)
            # makes sure that, even if the old message also shows up, only one run happens.
            await self._jobs.touch(actor.organization_id, job.id, now)
            self._queue.enqueue(actor.organization_id, job.id)
            logger.info("job_requeued", job_id=str(job.id), status=job.status.value)
            return ProcessingStatus(job, requeued=True)
        return ProcessingStatus(job)


class CannotReprocessError(ForbiddenError):
    code = "cannot_reprocess"
    message = "Solo quien subió el documento o un administrador puede reprocesarlo"


class ReprocessDocument:
    def __init__(self, documents: DocumentGateway, scheduler: ScheduleProcessing) -> None:
        self._documents = documents
        self._scheduler = scheduler

    async def execute(self, actor: Membership, document_id: UUID) -> None:
        ensure_permission(actor.role, Permission.UPLOAD_DOCUMENTS)
        document = await self._documents.find(actor.organization_id, document_id)
        if document is None:
            raise DocumentNotFoundError()
        is_author = document.created_by_id == actor.user_id
        if not is_author and not has_permission(actor.role, Permission.DELETE_ANY_DOCUMENT):
            raise CannotReprocessError()
        await self._scheduler.schedule(
            actor.organization_id, document_id, document.latest_version_id
        )


class ListChunks:
    def __init__(self, documents: DocumentGateway, chunks: ChunkRepository) -> None:
        self._documents = documents
        self._chunks = chunks

    async def execute(
        self, actor: Membership, document_id: UUID, *, limit: int, after_position: int | None
    ) -> list[StoredChunk]:
        ensure_permission(actor.role, Permission.VIEW_DOCUMENTS)
        if await self._documents.find(actor.organization_id, document_id) is None:
            raise DocumentNotFoundError()
        return await self._chunks.list_for_document(
            actor.organization_id, document_id, limit=limit, after_position=after_position
        )
