"""Conversations with fakes: privacy (404), scope, history, follow-ups, saving answers, ratings."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.ai.concurrency import GenerationQueue
from app.ai.providers.llm import LLMServiceError
from app.modules.conversations.application.manage_conversations import (
    DeleteConversation,
    GetConversation,
    ListConversations,
    RateAnswer,
    RateAnswerCommand,
    StartConversation,
    UpdateConversation,
    UpdateConversationCommand,
)
from app.modules.conversations.application.send_message import (
    MessageStarted,
    SendMessage,
    SendMessageCommand,
)
from app.modules.conversations.domain.entities import (
    Feedback,
    MessageRole,
    MessageStatus,
    title_from_question,
)
from app.modules.conversations.domain.errors import (
    ConversationNotFoundError,
    FeedbackOnlyForAnswersError,
    TooManyScopeDocumentsError,
)
from app.modules.knowledge.application.answer_question import AnswerQuestion
from app.modules.knowledge.application.search_documents import SearchDocuments
from app.modules.knowledge.domain.answer import Token
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from tests.fakes import (
    FakeAnswerRecorder,
    FakeEmbeddingProvider,
    FakeLLMProvider,
    InMemoryConversationRepository,
)
from tests.unit.test_answer_question import GOOD, OPTIONS, ORG, FakeChunkSearch


def member(role: Role = Role.VIEWER, org: object = ORG) -> Membership:
    return Membership.create(
        id=uuid4(),
        organization_id=org,  # type: ignore[arg-type]
        user_id=uuid4(),
        role=role,
        now=datetime.now(UTC),
    )


class World:
    def __init__(self, llm: FakeLLMProvider | None = None) -> None:
        self.repo = InMemoryConversationRepository()
        self.recorder = FakeAnswerRecorder(self.repo)
        self.search = FakeChunkSearch(GOOD)
        self.llm = llm or FakeLLMProvider(["Un mes ", "[1]."])
        answers = AnswerQuestion(
            SearchDocuments(self.search, FakeEmbeddingProvider()),
            self.llm,
            GenerationQueue(slots=1),
            OPTIONS,
        )
        self.send = SendMessage(self.repo, answers, self.recorder)

    async def ask(self, actor: Membership, conversation_id: object, question: str) -> list[object]:
        prepared = await self.send.prepare(
            SendMessageCommand(actor, conversation_id, question)  # type: ignore[arg-type]
        )
        return [e async for e in self.send.stream(prepared)]


async def test_a_conversation_is_private_to_its_author() -> None:
    world = World()
    ana, bob = member(), member()
    conversation = await StartConversation(world.repo).execute(ana)

    with pytest.raises(ConversationNotFoundError):
        await GetConversation(world.repo).execute(bob, conversation.id)
    with pytest.raises(ConversationNotFoundError):
        await world.ask(bob, conversation.id, "¿Preaviso?")
    other_org = member(org=uuid4())
    with pytest.raises(ConversationNotFoundError):
        await DeleteConversation(world.repo).execute(other_org, conversation.id)
    assert (await ListConversations(world.repo).execute(bob)).items == []


async def test_asking_saves_the_question_and_the_answer_with_its_citations() -> None:
    world = World()
    ana = member()
    conversation = await StartConversation(world.repo).execute(ana)

    events = await world.ask(ana, conversation.id, "¿Cuál es el  preaviso?")

    started = events[0]
    assert isinstance(started, MessageStarted)
    detail = await GetConversation(world.repo).execute(ana, conversation.id)
    question, answer = detail.messages
    assert (question.role, question.content) == (MessageRole.USER, "¿Cuál es el preaviso?")
    assert (answer.id, answer.role) == (started.answer_id, MessageRole.ASSISTANT)
    assert answer.content == "Un mes [1]."
    assert answer.status is MessageStatus.COMPLETE
    assert answer.no_evidence is False
    [citation] = answer.citations
    assert citation.marker == 1
    assert citation.chunk_ids == (GOOD[0].chunk_id,)
    assert detail.conversation.title == "¿Cuál es el preaviso?"


async def test_a_follow_up_searches_with_the_previous_question() -> None:
    world = World()
    ana = member()
    conversation = await StartConversation(world.repo).execute(ana)
    await world.ask(ana, conversation.id, "¿Preaviso del empleador?")
    await world.ask(ana, conversation.id, "¿Y el del trabajador?")

    assert world.search.texts[-1] == "¿Preaviso del empleador? ¿Y el del trabajador?"
    # The title stays the first question.
    detail = await GetConversation(world.repo).execute(ana, conversation.id)
    assert detail.conversation.title == "¿Preaviso del empleador?"
    assert len(detail.messages) == 4


async def test_the_scope_limits_the_search_to_the_chosen_documents() -> None:
    world = World()
    ana = member()
    doc = uuid4()
    conversation = await StartConversation(world.repo).execute(ana, document_ids=[doc, doc])
    assert conversation.document_ids == (doc,)

    prepared = await world.send.prepare(SendMessageCommand(ana, conversation.id, "¿Preaviso?"))
    assert prepared.answer.has_evidence  # the fake search ignores the filter; see integration


async def test_too_many_scope_documents_is_rejected() -> None:
    with pytest.raises(TooManyScopeDocumentsError):
        await StartConversation(InMemoryConversationRepository()).execute(
            member(), document_ids=[uuid4() for _ in range(51)]
        )


async def test_closing_the_stream_saves_what_was_written_as_stopped() -> None:
    world = World(FakeLLMProvider(["Un mes ", "y algo más [1]."]))
    ana = member()
    conversation = await StartConversation(world.repo).execute(ana)
    prepared = await world.send.prepare(SendMessageCommand(ana, conversation.id, "¿Preaviso?"))

    stream = world.send.stream(prepared)
    async for event in stream:
        if isinstance(event, Token):
            break  # the person pressed Stop after the first piece
    await stream.aclose()

    answer = world.repo.messages[prepared.started.answer_id]
    assert answer.status is MessageStatus.STOPPED
    assert answer.content == "Un mes"  # what was shown (the filter holds back a trailing space)
    assert answer.citations == ()


async def test_a_model_failure_saves_the_answer_as_failed() -> None:
    world = World(FakeLLMProvider(["Un mes ", "[1]."], fail_after=1))
    ana = member()
    conversation = await StartConversation(world.repo).execute(ana)
    with pytest.raises(LLMServiceError):
        await world.ask(ana, conversation.id, "¿Preaviso?")
    [(_, status)] = world.recorder.finished
    assert status is MessageStatus.FAILED


async def test_only_answers_can_be_rated() -> None:
    world = World()
    ana = member()
    conversation = await StartConversation(world.repo).execute(ana)
    events = await world.ask(ana, conversation.id, "¿Preaviso?")
    started = events[0]
    assert isinstance(started, MessageStarted)
    rate = RateAnswer(world.repo)

    await rate.execute(
        RateAnswerCommand(ana, conversation.id, started.answer_id, Feedback.NOT_HELPFUL)
    )
    assert world.repo.messages[started.answer_id].feedback is Feedback.NOT_HELPFUL
    with pytest.raises(FeedbackOnlyForAnswersError):
        await rate.execute(
            RateAnswerCommand(ana, conversation.id, started.question_id, Feedback.HELPFUL)
        )


async def test_rename_and_change_the_scope() -> None:
    repo = InMemoryConversationRepository()
    ana = member()
    doc = uuid4()
    conversation = await StartConversation(repo).execute(ana, document_ids=[doc])
    update = UpdateConversation(repo)

    renamed = await update.execute(UpdateConversationCommand(ana, conversation.id, title="  Plan "))
    assert (renamed.title, renamed.document_ids) == ("Plan", (doc,))
    everything = await update.execute(
        UpdateConversationCommand(ana, conversation.id, change_scope=True)
    )
    assert everything.document_ids is None


async def test_conversations_are_listed_newest_first_with_a_cursor() -> None:
    repo = InMemoryConversationRepository()
    ana = member()
    start = StartConversation(repo)
    created = [await start.execute(ana) for _ in range(3)]
    page = await ListConversations(repo).execute(ana, limit=2)
    assert [c.id for c in page.items] == [created[2].id, created[1].id]
    assert page.next_before_id == created[1].id
    rest = await ListConversations(repo).execute(ana, limit=2, before_id=page.next_before_id)
    assert [c.id for c in rest.items] == [created[0].id]
    assert rest.next_before_id is None


def test_long_questions_are_cut_at_a_word_for_the_title() -> None:
    title = title_from_question("palabra " * 30)
    assert len(title) <= 81
    assert title.endswith("…")
    assert not title.endswith(" …")
