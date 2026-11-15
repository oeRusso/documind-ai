"""Use case: the usage overview of the active organization (stage 10).

Only owners and admins (VIEW_ANALYTICS). It asks the other modules through their application
layer (CLAUDE.md: a module never reads another one's tables) and only gets aggregated numbers,
plus the questions the documents could not answer, without who asked them (ADR 0012).
"""

from collections.abc import Callable
from datetime import datetime, timedelta

from app.modules.analytics.domain.overview import DayCount, Overview
from app.modules.conversations.application.usage import GetQuestionUsage
from app.modules.ingestion.application.usage import GetProcessingUsage
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.permissions import Permission, ensure_permission
from app.shared.ids import utc_now

ALLOWED_DAYS = (7, 30, 90)


class GetOverview:
    def __init__(
        self,
        questions: GetQuestionUsage,
        processing: GetProcessingUsage,
        *,
        tz: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._questions = questions
        self._processing = processing
        self._tz = tz
        self._clock = clock

    async def execute(self, actor: Membership, days: int = 30) -> Overview:
        ensure_permission(actor.role, Permission.VIEW_ANALYTICS)
        days = days if days in ALLOWED_DAYS else 30
        now = self._clock()
        since = now - timedelta(days=days)
        org = actor.organization_id
        usage, unanswered = await self._questions.execute(org, since, tz=self._tz)
        processing = await self._processing.execute(org, since)

        by_day = dict(usage.questions_by_day)
        first = (since + timedelta(days=1)).date()
        series = [
            DayCount(day, by_day.get(day, 0))
            for day in (first + timedelta(days=n) for n in range(days))
        ]
        return Overview(
            days=days,
            since=since,
            questions_by_day=series,
            questions=sum(n for _, n in usage.questions_by_day),
            answered=usage.answered,
            no_evidence=usage.no_evidence,
            interrupted=usage.interrupted,
            helpful=usage.helpful,
            not_helpful=usage.not_helpful,
            people=usage.people,
            documents_ready=processing.documents_ready,
            documents_failed=processing.documents_failed,
            pages=processing.pages,
            ocr_pages=processing.ocr_pages,
            documents_pending=processing.pending,
            unanswered=[(q.question, q.asked_at) for q in unanswered],
        )
