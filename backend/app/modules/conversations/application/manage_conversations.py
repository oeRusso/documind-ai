"""Use cases: start, list, read, change and delete conversations; rate an answer (stage 8).

Order of the checks in every use case:
1. The role can read documents at all -> 403 (every role can; kept for symmetry with the rest).
2. The conversation exists for THIS person in THIS organization -> 404 otherwise. Another
   member's conversation is 404 too: the history is private.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.conversations.domain.entities import (
    MAX_SCOPE_DOCUMENTS,
    Conversation,
    Feedback,
    Message,
    MessageRole,
    normalize_scope,
)
from app.modules.conversations.domain.errors import (
    ConversationNotFoundError,
    FeedbackOnlyForAnswersError,
    MessageNotFoundError,
    TooManyScopeDocumentsError,
)
from app.modules.conversations.domain.repository import ConversationRepository
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.permissions import Permission, ensure_permission
from app.shared.ids import new_id, utc_now

MAX_PAGE_SIZE = 100
TITLE_MAX_CHARS = 200


def _scope(document_ids: list[UUID] | None) -> tuple[UUID, ...] | None:
    scope = normalize_scope(document_ids)
    if scope is not None and len(scope) > MAX_SCOPE_DOCUMENTS:
        raise TooManyScopeDocumentsError()
    return scope


async def get_owned(
    conversations: ConversationRepository, actor: Membership, conversation_id: UUID
) -> Conversation:
    ensure_permission(actor.role, Permission.VIEW_DOCUMENTS)
    conversation = await conversations.get(actor.organization_id, actor.user_id, conversation_id)
    if conversation is None:
        raise ConversationNotFoundError()
    return conversation


class StartConversation:
    def __init__(
        self, conversations: ConversationRepository, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._conversations = conversations
        self._clock = clock

    async def execute(
        self, actor: Membership, *, document_ids: list[UUID] | None = None
    ) -> Conversation:
        """`document_ids` from another organization are harmless: the search filters by the
        actor's organization inside the query, so they simply never match."""
        ensure_permission(actor.role, Permission.VIEW_DOCUMENTS)
        now = self._clock()
        conversation = Conversation(
            id=new_id(),
            organization_id=actor.organization_id,
            user_id=actor.user_id,
            title=None,
            document_ids=_scope(document_ids),
            created_at=now,
            updated_at=now,
        )
        await self._conversations.add(conversation)
        return conversation


@dataclass(frozen=True, slots=True)
class ConversationPage:
    items: list[Conversation]
    next_before_id: UUID | None


class ListConversations:
    def __init__(self, conversations: ConversationRepository) -> None:
        self._conversations = conversations

    async def execute(
        self, actor: Membership, *, limit: int = 20, before_id: UUID | None = None
    ) -> ConversationPage:
        ensure_permission(actor.role, Permission.VIEW_DOCUMENTS)
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        items = await self._conversations.list_page(
            actor.organization_id, actor.user_id, limit=limit + 1, before_id=before_id
        )
        has_more = len(items) > limit
        items = items[:limit]
        return ConversationPage(items, items[-1].id if has_more and items else None)


@dataclass(frozen=True, slots=True)
class ConversationDetail:
    conversation: Conversation
    messages: list[Message]


class GetConversation:
    def __init__(self, conversations: ConversationRepository) -> None:
        self._conversations = conversations

    async def execute(self, actor: Membership, conversation_id: UUID) -> ConversationDetail:
        conversation = await get_owned(self._conversations, actor, conversation_id)
        messages = await self._conversations.list_messages(actor.organization_id, conversation.id)
        return ConversationDetail(conversation, messages)


@dataclass(frozen=True, slots=True)
class UpdateConversationCommand:
    actor: Membership
    conversation_id: UUID
    title: str | None = None  # None: unchanged
    document_ids: list[UUID] | None = None
    change_scope: bool = False  # document_ids=None with change_scope=True means "all documents"


class UpdateConversation:
    def __init__(
        self, conversations: ConversationRepository, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._conversations = conversations
        self._clock = clock

    async def execute(self, command: UpdateConversationCommand) -> Conversation:
        conversation = await get_owned(self._conversations, command.actor, command.conversation_id)
        title = conversation.title
        if command.title is not None:
            title = " ".join(command.title.split())[:TITLE_MAX_CHARS] or conversation.title
        scope = _scope(command.document_ids) if command.change_scope else conversation.document_ids
        updated = Conversation(
            id=conversation.id,
            organization_id=conversation.organization_id,
            user_id=conversation.user_id,
            title=title,
            document_ids=scope,
            created_at=conversation.created_at,
            updated_at=self._clock(),
        )
        await self._conversations.update(updated)
        return updated


class DeleteConversation:
    """Deletes the conversation with its messages and citations (no undo, it is your history)."""

    def __init__(self, conversations: ConversationRepository) -> None:
        self._conversations = conversations

    async def execute(self, actor: Membership, conversation_id: UUID) -> None:
        conversation = await get_owned(self._conversations, actor, conversation_id)
        await self._conversations.delete(actor.organization_id, conversation.id)


@dataclass(frozen=True, slots=True)
class RateAnswerCommand:
    actor: Membership
    conversation_id: UUID
    message_id: UUID
    feedback: Feedback | None  # None removes the rating


class RateAnswer:
    """ "Útil / no útil". The not helpful ones feed the evaluation dataset
    (`python -m evaluation.export_feedback` lists them for a person to review)."""

    def __init__(
        self, conversations: ConversationRepository, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._conversations = conversations
        self._clock = clock

    async def execute(self, command: RateAnswerCommand) -> None:
        conversation = await get_owned(self._conversations, command.actor, command.conversation_id)
        message = await self._conversations.get_message(
            command.actor.organization_id, conversation.id, command.message_id
        )
        if message is None:
            raise MessageNotFoundError()
        if message.role is not MessageRole.ASSISTANT:
            raise FeedbackOnlyForAnswersError()
        await self._conversations.set_feedback(
            command.actor.organization_id, message.id, command.feedback, self._clock()
        )


@dataclass(frozen=True, slots=True)
class FeedbackCandidate:
    """An answer rated "no útil", ready for a person to turn into a dataset question."""

    question: Message
    answer: Message


class ListNotHelpfulAnswers:
    """For the operator (app/jobs/export_feedback.py), not for an HTTP endpoint: it reads every
    member's history of one organization. The repository still filters by that organization."""

    def __init__(self, conversations: ConversationRepository) -> None:
        self._conversations = conversations

    async def execute(self, organization_id: UUID, *, limit: int = 200) -> list[FeedbackCandidate]:
        pairs = await self._conversations.list_rated_not_helpful(organization_id, limit=limit)
        return [FeedbackCandidate(question, answer) for question, answer in pairs]
