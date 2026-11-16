"""What the conversations module offers to analytics (stage 10): aggregated numbers only."""

from datetime import datetime
from uuid import UUID

from app.modules.conversations.domain.stats import (
    ConversationStats,
    QuestionUsage,
    UnansweredQuestion,
)


class GetQuestionUsage:
    def __init__(self, stats: ConversationStats) -> None:
        self._stats = stats

    async def execute(
        self, organization_id: UUID, since: datetime, *, tz: str, unanswered_limit: int = 20
    ) -> tuple[QuestionUsage, list[UnansweredQuestion]]:
        usage = await self._stats.usage(organization_id, since, tz)
        unanswered = await self._stats.unanswered(organization_id, since, unanswered_limit)
        return usage, unanswered
