"""Processing jobs: one per document version, with its state and progress. Pure Python.

States: pending -> extracting -> (ocr) -> chunking -> (embedding) -> ready, or failed.

How a crash is survived without duplicates (stage 5 criterion):
- A worker *claims* a job before working on it, and the claim has an expiry (`locked_until`).
  While it works it keeps pushing the expiry forward ("heartbeat").
- If the worker dies, nobody pushes it: the claim expires and the job can be claimed again
  (by the redelivered message, or when someone looks at the document and the API re-queues it).
- Two workers can never hold the same job: claiming is a single UPDATE that only succeeds if
  the job is pending or its claim expired.
- The chunks of a version are replaced in one transaction at the end, so a half-done run
  leaves nothing behind and a repeated run does not duplicate anything.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

# How long a claim lasts without a heartbeat. A worker sends one after every page.
LEASE = timedelta(minutes=3)
MAX_ATTEMPTS = 3
# A job still pending after this long was probably never queued (the queue was down).
PENDING_GRACE = timedelta(minutes=2)


class JobStatus(StrEnum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    OCR = "ocr"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"  # stage 6; skipped when no embedding model is configured
    READY = "ready"
    FAILED = "failed"

    @property
    def is_running(self) -> bool:
        return self in RUNNING

    @property
    def is_final(self) -> bool:
        return self in (JobStatus.READY, JobStatus.FAILED)


RUNNING = frozenset({JobStatus.EXTRACTING, JobStatus.OCR, JobStatus.CHUNKING, JobStatus.EMBEDDING})


@dataclass(frozen=True, slots=True)
class ProcessingJob:
    id: UUID
    organization_id: UUID
    document_id: UUID
    version_id: UUID
    status: JobStatus
    attempts: int
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    locked_until: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    pages_total: int | None = None
    pages_done: int = 0
    ocr_pages: int = 0
    chunk_count: int = 0

    def is_stalled(self, now: datetime) -> bool:
        """True when nobody is working on it and nobody will unless it is queued again."""
        if self.status.is_running:
            return self.locked_until is None or self.locked_until < now
        if self.status is JobStatus.PENDING:
            return now - self.updated_at > PENDING_GRACE
        return False
