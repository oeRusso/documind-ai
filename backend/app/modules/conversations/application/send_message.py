"""Use case: ask a question inside a conversation, and save the question and the answer.

It wraps knowledge's AnswerQuestion (through its application layer, as CLAUDE.md asks):
1. prepare (inside the request's transaction, so 404/403/422/503 come out as normal errors):
   the conversation is yours -> the previous turn -> AnswerQuestion.prepare with the
   conversation's scope and the previous question -> save the question and an EMPTY answer
   (status `streaming`). The request commits all that before the stream starts.
2. stream: the events of AnswerQuestion, plus a first `MessageStarted` with the ids. At the
   end the answer is completed with its text and citations in a separate short transaction
   (AnswerRecorder). Stop or a model failure still save what was written, as `stopped` or
   `failed`.
"""

from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.ai.providers.llm import LLMServiceError
from app.modules.conversations.application.manage_conversations import get_owned
from app.modules.conversations.domain.entities import (
    Message,
    MessageRole,
    MessageStatus,
    SavedCitation,
    title_from_question,
)
from app.modules.conversations.domain.repository import AnswerRecorder, ConversationRepository
from app.modules.knowledge.application.answer_question import (
    AnswerQuery,
    AnswerQuestion,
    PreparedAnswer,
)
from app.modules.knowledge.domain.answer import AnswerEvent, CitationsReady, Done, Token
from app.modules.organizations.domain.membership import Membership
from app.shared.ids import new_id, utc_now


@dataclass(frozen=True, slots=True)
class SendMessageCommand:
    actor: Membership
    conversation_id: UUID
    question: str


@dataclass(frozen=True, slots=True)
class MessageStarted:
    """First event: where the question and the answer were saved (the page needs the answer id
    to rate it)."""

    conversation_id: UUID
    question_id: UUID
    answer_id: UUID


@dataclass(frozen=True, slots=True)
class PreparedMessage:
    started: MessageStarted
    organization_id: UUID
    answer: PreparedAnswer


ConversationEvent = MessageStarted | AnswerEvent


class SendMessage:
    def __init__(
        self,
        conversations: ConversationRepository,
        answers: AnswerQuestion,
        recorder: AnswerRecorder,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._conversations = conversations
        self._answers = answers
        self._recorder = recorder
        self._clock = clock

    async def prepare(self, command: SendMessageCommand) -> PreparedMessage:
        actor = command.actor
        conversation = await get_owned(self._conversations, actor, command.conversation_id)
        turn = await self._conversations.last_turn(actor.organization_id, conversation.id)
        prepared = await self._answers.prepare(
            AnswerQuery(
                actor,
                command.question,
                document_ids=conversation.document_ids,
                previous_question=turn.question if turn else None,
            )
        )
        now = self._clock()
        question = Message(
            id=new_id(),
            organization_id=actor.organization_id,
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=prepared.question,
            status=MessageStatus.COMPLETE,
            created_at=now,
        )
        answer = Message(
            id=new_id(),
            organization_id=actor.organization_id,
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="",
            status=MessageStatus.STREAMING,
            # A microsecond later keeps the order even if two ids share a millisecond.
            created_at=now + timedelta(microseconds=1),
        )
        await self._conversations.add_messages([question, answer])
        await self._conversations.update(
            conversation.touched(now, title=title_from_question(prepared.question))
        )
        return PreparedMessage(
            MessageStarted(conversation.id, question.id, answer.id),
            actor.organization_id,
            prepared,
        )

    async def stream(self, prepared: PreparedMessage) -> AsyncGenerator[ConversationEvent]:
        yield prepared.started
        text: list[str] = []
        citations: list[SavedCitation] = []
        no_evidence: bool | None = None
        status = MessageStatus.STOPPED  # if the stream is closed before Done
        try:
            async for event in self._answers.stream(prepared.answer):
                match event:
                    case Token(text=piece):
                        text.append(piece)
                    case CitationsReady(citations=cited):
                        citations = [
                            SavedCitation(
                                marker=c.marker,
                                document_id=c.document_id,
                                document_title=c.document_title,
                                page_start=c.page_start,
                                page_end=c.page_end,
                                excerpt=c.excerpt,
                                chunk_ids=c.chunk_ids,
                            )
                            for c in cited
                        ]
                    case Done(no_evidence=value):
                        no_evidence = value
                        status = MessageStatus.COMPLETE
                yield event
        except LLMServiceError:
            status = MessageStatus.FAILED
            raise
        finally:
            # Runs on success, on failure and when the person presses Stop (the generator is
            # closed): the recorder shields itself from that cancellation.
            await self._recorder.finish(
                prepared.organization_id,
                prepared.started.answer_id,
                content="".join(text),
                status=status,
                no_evidence=no_evidence,
                citations=citations if status is MessageStatus.COMPLETE else [],
            )
