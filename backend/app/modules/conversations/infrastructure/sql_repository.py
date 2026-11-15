"""SQL implementations of the conversations ports.

Every query filters by `organization_id` (and conversations by `user_id` too); RLS is the
second layer. `SqlAnswerRecorder` opens its own short transaction to complete an answer.
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import anyio
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.conversations.domain.entities import (
    Conversation,
    Feedback,
    Message,
    MessageRole,
    MessageStatus,
    SavedCitation,
    Turn,
)
from app.modules.conversations.infrastructure.models import (
    CitationModel,
    ConversationModel,
    MessageModel,
)
from app.shared.ids import new_id


def _conversation(model: ConversationModel) -> Conversation:
    return Conversation(
        id=model.id,
        organization_id=model.organization_id,
        user_id=model.user_id,
        title=model.title,
        document_ids=tuple(model.document_ids) if model.document_ids else None,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _citation(model: CitationModel) -> SavedCitation:
    return SavedCitation(
        marker=model.marker,
        document_id=model.document_id,
        document_title=model.document_title,
        page_start=model.page_start,
        page_end=model.page_end,
        excerpt=model.excerpt,
        chunk_ids=tuple(model.chunk_ids),
    )


def _message(model: MessageModel, citations: Sequence[SavedCitation] = ()) -> Message:
    return Message(
        id=model.id,
        organization_id=model.organization_id,
        conversation_id=model.conversation_id,
        role=MessageRole(model.role),
        content=model.content,
        status=MessageStatus(model.status),
        created_at=model.created_at,
        no_evidence=model.no_evidence,
        feedback=Feedback(model.feedback) if model.feedback else None,
        citations=tuple(citations),
    )


class SqlConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, conversation: Conversation) -> None:
        self._session.add(
            ConversationModel(
                id=conversation.id,
                organization_id=conversation.organization_id,
                user_id=conversation.user_id,
                title=conversation.title,
                document_ids=list(conversation.document_ids) if conversation.document_ids else None,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
        )
        await self._session.flush()

    async def get(
        self, organization_id: UUID, user_id: UUID, conversation_id: UUID
    ) -> Conversation | None:
        model = await self._session.scalar(
            select(ConversationModel).where(
                ConversationModel.organization_id == organization_id,
                ConversationModel.user_id == user_id,
                ConversationModel.id == conversation_id,
            )
        )
        return _conversation(model) if model else None

    async def list_page(
        self, organization_id: UUID, user_id: UUID, *, limit: int, before_id: UUID | None
    ) -> list[Conversation]:
        query = (
            select(ConversationModel)
            .where(
                ConversationModel.organization_id == organization_id,
                ConversationModel.user_id == user_id,
            )
            .order_by(ConversationModel.id.desc())  # UUID v7: newest first
            .limit(limit)
        )
        if before_id is not None:
            query = query.where(ConversationModel.id < before_id)
        return [_conversation(m) for m in await self._session.scalars(query)]

    async def update(self, conversation: Conversation) -> None:
        await self._session.execute(
            update(ConversationModel)
            .where(
                ConversationModel.organization_id == conversation.organization_id,
                ConversationModel.id == conversation.id,
            )
            .values(
                title=conversation.title,
                document_ids=list(conversation.document_ids) if conversation.document_ids else None,
                updated_at=conversation.updated_at,
            )
        )

    async def delete(self, organization_id: UUID, conversation_id: UUID) -> None:
        # Messages and citations go with it (ON DELETE CASCADE).
        await self._session.execute(
            delete(ConversationModel).where(
                ConversationModel.organization_id == organization_id,
                ConversationModel.id == conversation_id,
            )
        )

    async def delete_all(self, organization_id: UUID) -> int:
        """Only for the demo reset job: every conversation of the organization goes."""
        result = await self._session.execute(
            delete(ConversationModel).where(ConversationModel.organization_id == organization_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def add_messages(self, messages: Sequence[Message]) -> None:
        for m in messages:
            self._session.add(
                MessageModel(
                    id=m.id,
                    organization_id=m.organization_id,
                    conversation_id=m.conversation_id,
                    role=m.role.value,
                    content=m.content,
                    status=m.status.value,
                    no_evidence=m.no_evidence,
                    feedback=m.feedback.value if m.feedback else None,
                    created_at=m.created_at,
                    updated_at=m.created_at,
                )
            )
            await self._session.flush()  # in order: the question before the answer

    async def _citations_of(
        self, organization_id: UUID, message_ids: Sequence[UUID]
    ) -> dict[UUID, list[SavedCitation]]:
        if not message_ids:
            return {}
        models = await self._session.scalars(
            select(CitationModel)
            .where(
                CitationModel.organization_id == organization_id,
                CitationModel.message_id.in_(message_ids),
            )
            .order_by(CitationModel.message_id, CitationModel.marker)
        )
        by_message: dict[UUID, list[SavedCitation]] = {}
        for model in models:
            by_message.setdefault(model.message_id, []).append(_citation(model))
        return by_message

    async def list_messages(self, organization_id: UUID, conversation_id: UUID) -> list[Message]:
        models = list(
            await self._session.scalars(
                select(MessageModel)
                .where(
                    MessageModel.organization_id == organization_id,
                    MessageModel.conversation_id == conversation_id,
                )
                .order_by(MessageModel.created_at, MessageModel.id)
            )
        )
        citations = await self._citations_of(organization_id, [m.id for m in models])
        return [_message(m, citations.get(m.id, ())) for m in models]

    async def last_turn(self, organization_id: UUID, conversation_id: UUID) -> Turn | None:
        models = list(
            await self._session.scalars(
                select(MessageModel)
                .where(
                    MessageModel.organization_id == organization_id,
                    MessageModel.conversation_id == conversation_id,
                )
                .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
                .limit(2)
            )
        )
        question = next((m for m in models if m.role == MessageRole.USER.value), None)
        if question is None:
            return None
        answer = next(
            (m for m in models if m.role == MessageRole.ASSISTANT.value and m.id > question.id),
            None,
        )
        return Turn(question.content, answer.content if answer else "")

    async def get_message(
        self, organization_id: UUID, conversation_id: UUID, message_id: UUID
    ) -> Message | None:
        model = await self._session.scalar(
            select(MessageModel).where(
                MessageModel.organization_id == organization_id,
                MessageModel.conversation_id == conversation_id,
                MessageModel.id == message_id,
            )
        )
        return _message(model) if model else None

    async def set_feedback(
        self, organization_id: UUID, message_id: UUID, feedback: Feedback | None, now: datetime
    ) -> None:
        await self._session.execute(
            update(MessageModel)
            .where(MessageModel.organization_id == organization_id, MessageModel.id == message_id)
            .values(feedback=feedback.value if feedback else None, updated_at=now)
        )

    async def list_rated_not_helpful(
        self, organization_id: UUID, *, limit: int
    ) -> list[tuple[Message, Message]]:
        answers = list(
            await self._session.scalars(
                select(MessageModel)
                .where(
                    MessageModel.organization_id == organization_id,
                    MessageModel.feedback == Feedback.NOT_HELPFUL.value,
                )
                .order_by(MessageModel.id.desc())
                .limit(limit)
            )
        )
        citations = await self._citations_of(organization_id, [a.id for a in answers])
        pairs = []
        for answer in answers:
            question = await self._session.scalar(
                select(MessageModel)
                .where(
                    MessageModel.organization_id == organization_id,
                    MessageModel.conversation_id == answer.conversation_id,
                    MessageModel.role == MessageRole.USER.value,
                    MessageModel.id < answer.id,
                )
                .order_by(MessageModel.id.desc())
                .limit(1)
            )
            if question is not None:
                pairs.append((_message(question), _message(answer, citations.get(answer.id, ()))))
        return pairs


class SqlAnswerRecorder:
    """Completes an answer in its own transaction, inside the organization (RLS).

    The shield: when the person presses Stop, the server cancels the request's task. A
    cancelled task would also cancel this save, so it runs shielded until it finishes.
    (Like `ignore_user_abort(true)` in PHP, but only for this block.)
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def finish(
        self,
        organization_id: UUID,
        message_id: UUID,
        *,
        content: str,
        status: MessageStatus,
        no_evidence: bool | None,
        citations: Sequence[SavedCitation],
    ) -> None:
        with anyio.CancelScope(shield=True):
            async with self._sessions() as session, session.begin():
                await SqlTenantContext(session).set_organization(organization_id)
                await session.execute(
                    update(MessageModel)
                    .where(
                        MessageModel.organization_id == organization_id,
                        MessageModel.id == message_id,
                    )
                    .values(content=content, status=status.value, no_evidence=no_evidence)
                )
                session.add_all(
                    CitationModel(
                        id=new_id(),
                        organization_id=organization_id,
                        message_id=message_id,
                        marker=c.marker,
                        document_id=c.document_id,
                        document_title=c.document_title,
                        page_start=c.page_start,
                        page_end=c.page_end,
                        excerpt=c.excerpt,
                        chunk_ids=list(c.chunk_ids),
                    )
                    for c in citations
                )
