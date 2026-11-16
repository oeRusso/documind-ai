"""Wiring: which concrete implementation each ingestion use case receives (API side)."""

from app.core.dependencies import SessionDep
from app.core.jobs import JobQueueDep
from app.modules.documents.application.ingestion_gateway import DocumentsForIngestion
from app.modules.documents.infrastructure.sql_repository import SqlDocumentRepository
from app.modules.ingestion.application.jobs import (
    GetProcessingStatus,
    ListChunks,
    ReprocessDocument,
    ScheduleProcessing,
)
from app.modules.ingestion.infrastructure.sql_repository import (
    SqlChunkRepository,
    SqlJobRepository,
)


def _documents(session: SessionDep) -> DocumentsForIngestion:
    return DocumentsForIngestion(SqlDocumentRepository(session))


def provide_scheduler(session: SessionDep, queue: JobQueueDep) -> ScheduleProcessing:
    return ScheduleProcessing(SqlJobRepository(session), queue)


def provide_processing_status(session: SessionDep, queue: JobQueueDep) -> GetProcessingStatus:
    return GetProcessingStatus(_documents(session), SqlJobRepository(session), queue)


def provide_reprocess(session: SessionDep, queue: JobQueueDep) -> ReprocessDocument:
    return ReprocessDocument(_documents(session), provide_scheduler(session, queue))


def provide_list_chunks(session: SessionDep) -> ListChunks:
    return ListChunks(_documents(session), SqlChunkRepository(session))
