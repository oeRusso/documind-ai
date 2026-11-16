"""What the conversations module needs from the outside world (interfaces only).

`Protocol` is like a PHP `interface`, but implicit: any class with these methods fits,
without writing `implements`. The SQL versions live in infrastructure/, fakes in tests/.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.conversations.domain.entities import (
    Conversation,
    Feedback,
    Message,
    MessageStatus,
    SavedCitation,
    Turn,
)


class ConversationRepository(Protocol):
    """Every method filters by organization AND user: a conversation is private."""

    async def add(self, conversation: Conversation) -> None: ...

    async def get(
        self, organization_id: UUID, user_id: UUID, conversation_id: UUID
    ) -> Conversation | None: ...

    async def list_page(
        self, organization_id: UUID, user_id: UUID, *, limit: int, before_id: UUID | None
    ) -> list[Conversation]: ...

    async def update(self, conversation: Conversation) -> None: ...

    async def delete(self, organization_id: UUID, conversation_id: UUID) -> None: ...

    async def add_messages(self, messages: Sequence[Message]) -> None: ...

    async def list_messages(self, organization_id: UUID, conversation_id: UUID) -> list[Message]:
        """Oldest first, each answer with its citations."""
        ...

    async def last_turn(self, organization_id: UUID, conversation_id: UUID) -> Turn | None: ...

    async def get_message(
        self, organization_id: UUID, conversation_id: UUID, message_id: UUID
    ) -> Message | None: ...

    async def set_feedback(
        self, organization_id: UUID, message_id: UUID, feedback: Feedback | None, now: datetime
    ) -> None: ...

    async def list_rated_not_helpful(
        self, organization_id: UUID, *, limit: int
    ) -> list[tuple[Message, Message]]:
        """(question, answer) pairs whose answer was marked not helpful, newest first."""
        ...


class AnswerRecorder(Protocol):
    """Saves the end of an answer in its OWN short transaction.

    The request's transaction is already committed when the answer starts streaming (the
    question and the empty answer are saved first), and generating can take a minute: a
    transaction must not stay open that long.
    """

    async def finish(
        self,
        organization_id: UUID,
        message_id: UUID,
        *,
        content: str,
        status: MessageStatus,
        no_evidence: bool | None,
        citations: Sequence[SavedCitation],
    ) -> None: ...
