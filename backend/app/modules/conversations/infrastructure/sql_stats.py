"""SQL for the conversations usage numbers (filtered by organization; RLS is the second layer)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.domain.stats import QuestionUsage, UnansweredQuestion


class SqlConversationStats:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def usage(self, organization_id: UUID, since: datetime, tz: str) -> QuestionUsage:
        params = {"org": organization_id, "since": since, "tz": tz}
        days = await self._session.execute(
            text("""
                SELECT (m.created_at AT TIME ZONE :tz)::date AS day, count(*) AS n
                FROM messages m
                WHERE m.organization_id = :org AND m.role = 'user' AND m.created_at >= :since
                GROUP BY day ORDER BY day
            """),
            params,
        )
        totals = (
            await self._session.execute(
                text("""
                    SELECT
                      count(*) FILTER (
                        WHERE m.status = 'complete' AND NOT coalesce(m.no_evidence, false)
                      ),
                      count(*) FILTER (WHERE m.status = 'complete' AND m.no_evidence),
                      count(*) FILTER (WHERE m.status IN ('stopped', 'failed', 'streaming')),
                      count(*) FILTER (WHERE m.feedback = 'helpful'),
                      count(*) FILTER (WHERE m.feedback = 'not_helpful'),
                      count(DISTINCT c.user_id)
                    FROM messages m JOIN conversations c ON c.id = m.conversation_id
                    WHERE m.organization_id = :org AND c.organization_id = :org
                      AND m.role = 'assistant' AND m.created_at >= :since
                """),
                params,
            )
        ).one()
        return QuestionUsage(
            questions_by_day=[(row.day, int(row.n)) for row in days],
            answered=int(totals[0]),
            no_evidence=int(totals[1]),
            interrupted=int(totals[2]),
            helpful=int(totals[3]),
            not_helpful=int(totals[4]),
            people=int(totals[5]),
        )

    async def unanswered(
        self, organization_id: UUID, since: datetime, limit: int
    ) -> list[UnansweredQuestion]:
        rows = await self._session.execute(
            text("""
                SELECT q.content, q.created_at
                FROM messages a
                JOIN LATERAL (
                    SELECT content, created_at FROM messages q
                    WHERE q.organization_id = :org AND q.conversation_id = a.conversation_id
                      AND q.role = 'user' AND q.id < a.id
                    ORDER BY q.id DESC LIMIT 1
                ) q ON true
                WHERE a.organization_id = :org AND a.role = 'assistant'
                  AND a.no_evidence AND a.created_at >= :since
                ORDER BY a.id DESC
                LIMIT :limit
            """),
            {"org": organization_id, "since": since, "limit": limit},
        )
        return [UnansweredQuestion(row.content, row.created_at) for row in rows]
