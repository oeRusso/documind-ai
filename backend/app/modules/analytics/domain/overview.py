"""The usage overview of an organization for its admins (stage 10). Pure dataclasses."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class DayCount:
    day: date
    questions: int


@dataclass(frozen=True, slots=True)
class Overview:
    days: int
    since: datetime
    questions_by_day: list[DayCount]  # every day of the period, zeros included
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
    unanswered: list[tuple[str, datetime]]  # the questions without evidence, newest first
