"""JSON shapes of the conversations endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.conversations.domain.entities import (
    MAX_SCOPE_DOCUMENTS,
    Conversation,
    Feedback,
    Message,
    MessageRole,
    MessageStatus,
    SavedCitation,
)
from app.modules.knowledge.application.answer_question import MAX_QUESTION_CHARS


class ConversationCreate(BaseModel):
    document_ids: list[UUID] | None = Field(
        default=None,
        max_length=MAX_SCOPE_DOCUMENTS,
        description="Alcance: solo estos documentos. Vacío o null: todos los de la organización",
    )


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    document_ids: list[UUID] | None = Field(
        default=None,
        max_length=MAX_SCOPE_DOCUMENTS,
        description="Si se manda (aunque sea null), reemplaza el alcance. null: todos",
    )


class ConversationRead(BaseModel):
    id: UUID
    title: str | None
    document_ids: list[UUID] | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(cls, conversation: Conversation) -> "ConversationRead":
        return cls(
            id=conversation.id,
            title=conversation.title,
            document_ids=list(conversation.document_ids) if conversation.document_ids else None,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class SavedCitationRead(BaseModel):
    marker: int
    document_id: UUID | None
    document_title: str
    page_start: int | None
    page_end: int | None
    excerpt: str

    @classmethod
    def build(cls, citation: SavedCitation) -> "SavedCitationRead":
        return cls(
            marker=citation.marker,
            document_id=citation.document_id,
            document_title=citation.document_title,
            page_start=citation.page_start,
            page_end=citation.page_end,
            excerpt=citation.excerpt,
        )


class MessageRead(BaseModel):
    id: UUID
    role: MessageRole
    content: str
    status: MessageStatus
    no_evidence: bool | None
    feedback: Feedback | None
    citations: list[SavedCitationRead]
    created_at: datetime

    @classmethod
    def build(cls, message: Message) -> "MessageRead":
        return cls(
            id=message.id,
            role=message.role,
            content=message.content,
            status=message.status,
            no_evidence=message.no_evidence,
            feedback=message.feedback,
            citations=[SavedCitationRead.build(c) for c in message.citations],
            created_at=message.created_at,
        )


class ConversationDetailRead(ConversationRead):
    messages: list[MessageRead]


class MessageCreate(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class FeedbackUpdate(BaseModel):
    feedback: Feedback | None = Field(description="`helpful`, `not_helpful` o null para quitarla")
