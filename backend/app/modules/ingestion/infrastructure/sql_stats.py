"""SQL for the processing numbers (filtered by organization; RLS is the second layer)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ingestion.domain.stats import ProcessingUsage


class SqlProcessingStats:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def usage(self, organization_id: UUID, since: datetime) -> ProcessingUsage:
        row = (
            await self._session.execute(
                text("""
                    WITH recent AS (
                      SELECT * FROM processing_jobs
                      WHERE organization_id = :org AND finished_at >= :since
                    )
                    SELECT
                      (SELECT count(*) FROM recent WHERE status = 'ready'),
                      (SELECT count(*) FROM recent WHERE status = 'failed'),
                      (SELECT coalesce(sum(pages_done), 0) FROM recent WHERE status = 'ready'),
                      (SELECT coalesce(sum(ocr_pages), 0) FROM recent WHERE status = 'ready'),
                      count(*) FILTER (WHERE status NOT IN ('ready', 'failed'))
                    FROM processing_jobs
                    WHERE organization_id = :org
                """),
                {"org": organization_id, "since": since},
            )
        ).one()
        return ProcessingUsage(
            documents_ready=int(row[0]),
            documents_failed=int(row[1]),
            pages=int(row[2]),
            ocr_pages=int(row[3]),
            pending=int(row[4]),
        )
