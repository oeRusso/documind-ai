"""GET /api/v1/analytics/overview: usage numbers of the active organization (owners, admins)."""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from app.core.dependencies import SessionDep, SettingsDep
from app.core.exceptions import ErrorResponse
from app.modules.analytics.application.get_overview import GetOverview
from app.modules.auth.presentation.dependencies import CurrentMemberDep
from app.modules.conversations.application.usage import GetQuestionUsage
from app.modules.conversations.infrastructure.sql_stats import SqlConversationStats
from app.modules.ingestion.application.usage import GetProcessingUsage
from app.modules.ingestion.infrastructure.sql_stats import SqlProcessingStats

router = APIRouter(prefix="/analytics", tags=["analytics"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
}


class DayCountRead(BaseModel):
    day: date
    questions: int


class UnansweredRead(BaseModel):
    question: str
    asked_at: datetime


class OverviewRead(BaseModel):
    days: int
    since: datetime
    questions_by_day: list[DayCountRead]
    questions: int
    answered: int
    no_evidence: int
    interrupted: int
    helpful: int
    not_helpful: int
    people: int
    documents_ready: int
    documents_failed: int
    pages: int
    ocr_pages: int
    documents_pending: int
    unanswered: list[UnansweredRead]


def provide_overview(session: SessionDep, settings: SettingsDep) -> GetOverview:
    return GetOverview(
        GetQuestionUsage(SqlConversationStats(session)),
        GetProcessingUsage(SqlProcessingStats(session)),
        tz=settings.analytics_timezone,
    )


@router.get("/overview", responses=_ERRORS)
async def get_overview(
    member: CurrentMemberDep,
    use_case: Annotated[GetOverview, Depends(provide_overview)],
    days: Annotated[int, Query(description="7, 30 o 90")] = 30,
) -> OverviewRead:
    """Uso de la organización: preguntas por día, cuántas no tuvieron respuesta (y cuáles, sin
    autor), valoraciones y documentos procesados. Solo owners y admins."""
    overview = await use_case.execute(member, days)
    return OverviewRead(
        days=overview.days,
        since=overview.since,
        questions_by_day=[
            DayCountRead(day=d.day, questions=d.questions) for d in overview.questions_by_day
        ],
        questions=overview.questions,
        answered=overview.answered,
        no_evidence=overview.no_evidence,
        interrupted=overview.interrupted,
        helpful=overview.helpful,
        not_helpful=overview.not_helpful,
        people=overview.people,
        documents_ready=overview.documents_ready,
        documents_failed=overview.documents_failed,
        pages=overview.pages,
        ocr_pages=overview.ocr_pages,
        documents_pending=overview.documents_pending,
        unanswered=[UnansweredRead(question=q, asked_at=t) for q, t in overview.unanswered],
    )
