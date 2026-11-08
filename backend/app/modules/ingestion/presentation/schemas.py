"""JSON shapes of the processing endpoints."""

from datetime import datetime

from pydantic import BaseModel

from app.modules.ingestion.domain.jobs import JobStatus, ProcessingJob
from app.modules.ingestion.domain.ports import StoredChunk


class ProcessingRead(BaseModel):
    """`status` is null when the document has no job (uploaded before stage 5)."""

    status: JobStatus | None
    attempts: int = 0
    pages_total: int | None = None
    pages_done: int = 0
    ocr_pages: int = 0
    chunk_count: int = 0
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def build(cls, job: ProcessingJob | None) -> "ProcessingRead":
        if job is None:
            return cls(status=None)
        return cls(
            status=job.status,
            attempts=job.attempts,
            pages_total=job.pages_total,
            pages_done=job.pages_done,
            ocr_pages=job.ocr_pages,
            chunk_count=job.chunk_count,
            error=job.error,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class ChunkRead(BaseModel):
    position: int
    content: str
    section: str | None
    page_start: int | None
    page_end: int | None
    token_count: int

    @classmethod
    def build(cls, stored: StoredChunk) -> "ChunkRead":
        chunk = stored.chunk
        return cls(
            position=chunk.position,
            content=chunk.content,
            section=chunk.section,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            token_count=chunk.token_count,
        )
