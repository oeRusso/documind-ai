"""Processing numbers of an organization (stage 10, for analytics)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProcessingUsage:
    documents_ready: int  # processing finished in the period
    documents_failed: int
    pages: int
    ocr_pages: int
    pending: int  # waiting or being processed now


class ProcessingStats(Protocol):
    async def usage(self, organization_id: UUID, since: datetime) -> ProcessingUsage: ...
