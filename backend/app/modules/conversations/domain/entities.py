"""Conversations, messages and saved citations (stage 8). Pure dataclasses, no SQL.

A conversation belongs to ONE person inside ONE organization: the history is private (another
member of the same organization gets 404, like a document of another organization).

Each question makes two messages: the person's (`user`) and the answer (`assistant`). The answer
row is created *before* generating, with status `streaming`, and is completed at the end. If the
person presses Stop or the model fails, it is saved as `stopped` or `failed` with what was
written so far: the history never loses a question.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

TITLE_CHARS = 80
MAX_SCOPE_DOCUMENTS = 50


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(StrEnum):
    STREAMING = "streaming"  # being generated (or the process died midway)
    COMPLETE = "complete"
    STOPPED = "stopped"  # the person pressed Stop / closed the page
    FAILED = "failed"  # the model failed


class Feedback(StrEnum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"


@dataclass(frozen=True, slots=True)
class SavedCitation:
    marker: int
    document_id: UUID | None  # None if the document was purged later (the title remains)
    document_title: str
    page_start: int | None
    page_end: int | None
    excerpt: str
    chunk_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class Message:
    id: UUID
    organization_id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    status: MessageStatus
    created_at: datetime
    no_evidence: bool | None = None  # only answers: the documents did not answer
    feedback: Feedback | None = None  # only answers
    citations: tuple[SavedCitation, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class Conversation:
    id: UUID
    organization_id: UUID
    user_id: UUID
    title: str | None  # None until the first question (it becomes the title)
    # Scope: None = every document of the organization; otherwise only these.
    document_ids: tuple[UUID, ...] | None
    created_at: datetime
    updated_at: datetime

    def touched(self, now: datetime, *, title: str | None = None) -> "Conversation":
        return replace(self, updated_at=now, title=self.title or title)


@dataclass(frozen=True, slots=True)
class Turn:
    """The last question and its answer: what a follow-up question leans on."""

    question: str
    answer: str


def title_from_question(question: str) -> str:
    text = " ".join(question.split())
    if len(text) <= TITLE_CHARS:
        return text
    return text[:TITLE_CHARS].rsplit(" ", 1)[0] + "…"


def normalize_scope(document_ids: list[UUID] | tuple[UUID, ...] | None) -> tuple[UUID, ...] | None:
    """None or empty = all documents. Duplicates removed, order kept."""
    if not document_ids:
        return None
    return tuple(dict.fromkeys(document_ids))
