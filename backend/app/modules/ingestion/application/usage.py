"""What the ingestion module offers to analytics (stage 10)."""

from datetime import datetime
from uuid import UUID

from app.modules.ingestion.domain.stats import ProcessingStats, ProcessingUsage


class GetProcessingUsage:
    def __init__(self, stats: ProcessingStats) -> None:
        self._stats = stats

    async def execute(self, organization_id: UUID, since: datetime) -> ProcessingUsage:
        return await self._stats.usage(organization_id, since)
