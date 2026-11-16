"""Usage numbers of the conversations of an organization (stage 10, for analytics). No texts
of a person's conversation leave here except the questions the documents could not answer,
without author: they tell an admin which documents are missing (ADR 0012)."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class QuestionUsage:
    questions_by_day: list[tuple[date, int]]  # only days with questions, oldest first
    answered: int
    no_evidence: int
    interrupted: int  # stopped or failed
    helpful: int
    not_helpful: int
    people: int  # distinct members who asked


@dataclass(frozen=True, slots=True)
class UnansweredQuestion:
    question: str
    asked_at: datetime


class ConversationStats(Protocol):
    async def usage(self, organization_id: UUID, since: datetime, tz: str) -> QuestionUsage: ...

    async def unanswered(
        self, organization_id: UUID, since: datetime, limit: int
    ) -> list[UnansweredQuestion]: ...
