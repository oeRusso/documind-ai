"""SQLAlchemy models of the conversations module (migration 0007). Only columns, no logic.

The three tables carry `organization_id` and Row Level Security. `conversations` also carries
`user_id`: every query filters by it (a conversation is private), RLS by organization.
"""

from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin
from app.modules.conversations.domain.entities import Feedback, MessageRole, MessageStatus


def _in_list(column: str, values: list[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in sorted(values))
    return f"{column} IN ({quoted})"


class ConversationModel(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_owner", "organization_id", "user_id", "id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str | None] = mapped_column(String(200))
    # NULL = every document of the organization.
    document_ids: Mapped[list[UUID] | None] = mapped_column(ARRAY(Uuid))


class MessageModel(TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(_in_list("role", [r.value for r in MessageRole]), name="role_valid"),
        CheckConstraint(_in_list("status", [s.value for s in MessageStatus]), name="status_valid"),
        CheckConstraint(
            f"feedback IS NULL OR {_in_list('feedback', [f.value for f in Feedback])}",
            name="feedback_valid",
        ),
        Index("ix_messages_conversation_id_id", "conversation_id", "id"),
        Index(
            "ix_messages_not_helpful",
            "organization_id",
            "id",
            postgresql_where="feedback = 'not_helpful'",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    no_evidence: Mapped[bool | None] = mapped_column(Boolean)
    feedback: Mapped[str | None] = mapped_column(String(16))


class CitationModel(TimestampMixin, Base):
    __tablename__ = "citations"
    __table_args__ = (CheckConstraint("marker >= 1", name="marker_positive"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    marker: Mapped[int] = mapped_column(Integer)
    # SET NULL: when a deleted document is purged, the history keeps the title and excerpt.
    document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    document_title: Mapped[str] = mapped_column(String(255))
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    excerpt: Mapped[str] = mapped_column(Text)
    # No foreign key: an array cannot have one, and reprocessing replaces chunks anyway.
    chunk_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid))
