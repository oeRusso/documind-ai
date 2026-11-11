"""AnswerQuestion with fakes: search, threshold, context, queue, streaming and citations."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.ai.concurrency import GenerationQueue
from app.ai.providers.llm import LLMServiceError
from app.modules.knowledge.application.answer_question import (
    AnswerOptions,
    AnswerQuery,
    AnswerQuestion,
    ChatUnavailableError,
    EmptyQuestionError,
    is_no_evidence,
)
from app.modules.knowledge.application.prompt import NO_EVIDENCE_ANSWER
from app.modules.knowledge.application.search_documents import SearchDocuments
from app.modules.knowledge.domain.answer import (
    AnswerEvent,
    CitationsReady,
    Done,
    Token,
)
from app.modules.knowledge.domain.search import ChunkMatch
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from tests.fakes import FakeEmbeddingProvider, FakeLLMProvider

ORG = uuid4()
DOC = uuid4()
OPTIONS = AnswerOptions(min_score=0.5, context_tokens=1500, max_answer_tokens=256)


def member(role: Role = Role.VIEWER) -> Membership:
    now = datetime.now(UTC)
    return Membership.create(id=uuid4(), organization_id=ORG, user_id=uuid4(), role=role, now=now)


def match(position: int, content: str, score: float) -> ChunkMatch:
    return ChunkMatch(
        chunk_id=uuid4(),
        document_id=DOC,
        document_title="Ley de Contrato de Trabajo",
        section=None,
        content=content,
        page_start=position + 1,
        page_end=position + 1,
        position=position,
        score=score,
    )


class FakeChunkSearch:
    """Returns fixed matches (its own scores are what the threshold looks at)."""

    def __init__(self, matches: list[ChunkMatch]) -> None:
        self.matches = matches
        self.organizations: list[UUID] = []

    async def by_vector(
        self,
        organization_id: UUID,
        vector: Sequence[float],
        *,
        model: str,
        dimension: int,
        limit: int,
        document_ids: Sequence[UUID] | None,
    ) -> list[ChunkMatch]:
        self.organizations.append(organization_id)
        return self.matches[:limit]

    async def by_text(
        self,
        organization_id: UUID,
        query: str,
        *,
        limit: int,
        document_ids: Sequence[UUID] | None,
    ) -> list[ChunkMatch]:
        self.organizations.append(organization_id)
        return self.matches[:limit]


GOOD = [
    match(0, "El preaviso del empleador es de un mes.", 0.71),
    match(5, "Las vacaciones son de 14 días corridos.", 0.55),
]


def use_case(
    matches: list[ChunkMatch], llm: FakeLLMProvider | None, *, embeddings: bool = True
) -> AnswerQuestion:
    provider = FakeEmbeddingProvider() if embeddings else None
    search = SearchDocuments(FakeChunkSearch(matches), provider)
    return AnswerQuestion(search, llm, GenerationQueue(slots=1), OPTIONS)


async def run(answer: AnswerQuestion, question: str) -> list[AnswerEvent]:
    prepared = await answer.prepare(AnswerQuery(member(), question))
    return [event async for event in answer.stream(prepared)]


def text_of(events: list[AnswerEvent]) -> str:
    return "".join(e.text for e in events if isinstance(e, Token))


async def test_an_answer_streams_its_text_then_its_citations_then_done() -> None:
    llm = FakeLLMProvider(["El preaviso es ", "de un mes ", "[1", "]."])
    events = await run(use_case(GOOD, llm), "¿Cuánto preaviso?")

    assert text_of(events) == "El preaviso es de un mes [1]."
    citations, done = events[-2], events[-1]
    assert isinstance(citations, CitationsReady)
    [citation] = citations.citations
    assert citation.marker == 1
    assert citation.document_id == DOC
    assert citation.document_title == "Ley de Contrato de Trabajo"
    assert (citation.page_start, citation.page_end) == (1, 1)
    assert citation.excerpt == "El preaviso del empleador es de un mes."
    assert done == Done(no_evidence=False)


async def test_the_model_receives_the_rules_the_numbered_chunks_and_the_question() -> None:
    llm = FakeLLMProvider()
    await run(use_case(GOOD, llm), "  ¿Cuánto   preaviso? ")
    [messages] = llm.calls
    assert messages[0].role == "system"
    assert '<fragmento n="1"' in messages[1].content
    assert '<fragmento n="2"' in messages[1].content
    assert messages[1].content.endswith("<pregunta>\n¿Cuánto preaviso?\n</pregunta>")


async def test_below_the_threshold_it_says_no_evidence_without_calling_the_model() -> None:
    llm = FakeLLMProvider()
    weak = [match(0, "Algo que no tiene nada que ver.", 0.31)]
    events = await run(use_case(weak, llm), "¿Quién ganó el mundial?")

    assert llm.calls == []
    assert text_of(events) == NO_EVIDENCE_ANSWER
    assert events[-2] == CitationsReady([])
    assert events[-1] == Done(no_evidence=True)


async def test_no_documents_at_all_is_no_evidence() -> None:
    llm = FakeLLMProvider()
    events = await run(use_case([], llm), "¿Algo?")
    assert llm.calls == []
    assert events[-1] == Done(no_evidence=True)


async def test_without_embeddings_any_word_match_is_enough() -> None:
    llm = FakeLLMProvider(["Un mes [1]."])
    weak = [match(0, "El preaviso del empleador es de un mes.", 0.01)]
    events = await run(use_case(weak, llm, embeddings=False), "preaviso")
    assert len(llm.calls) == 1
    assert events[-1] == Done(no_evidence=False)


async def test_invented_citations_are_removed_from_the_text_and_not_reported() -> None:
    llm = FakeLLMProvider(["Un mes [1] y otra cosa [7]."])
    events = await run(use_case(GOOD, llm), "¿Preaviso?")
    assert text_of(events) == "Un mes [1] y otra cosa."
    citations = events[-2]
    assert isinstance(citations, CitationsReady)
    assert [c.marker for c in citations.citations] == [1]


async def test_when_the_model_says_it_does_not_know_there_are_no_citations() -> None:
    llm = FakeLLMProvider([NO_EVIDENCE_ANSWER, " [1]"])
    events = await run(use_case(GOOD, llm), "¿Quién ganó el mundial?")
    assert events[-2] == CitationsReady([])
    assert events[-1] == Done(no_evidence=True)


async def test_a_model_failure_propagates_and_frees_the_queue() -> None:
    llm = FakeLLMProvider(["Un ", "mes"], fail_after=1)
    answer = use_case(GOOD, llm)
    with pytest.raises(LLMServiceError):
        await run(answer, "¿Preaviso?")
    # The place in line was given back: the next question does not wait.
    llm.fail_after = -1
    events = await run(answer, "¿Preaviso?")
    assert events[-1] == Done(no_evidence=False)


async def test_an_empty_question_is_rejected_before_searching() -> None:
    with pytest.raises(EmptyQuestionError):
        await use_case(GOOD, FakeLLMProvider()).prepare(AnswerQuery(member(), "   "))


async def test_without_a_model_the_chat_is_unavailable() -> None:
    with pytest.raises(ChatUnavailableError):
        await use_case(GOOD, None).prepare(AnswerQuery(member(), "¿Preaviso?"))


async def test_the_search_is_always_filtered_by_the_actor_organization() -> None:
    search = FakeChunkSearch(GOOD)
    answer = AnswerQuestion(
        SearchDocuments(search, FakeEmbeddingProvider()),
        FakeLLMProvider(),
        GenerationQueue(slots=1),
        OPTIONS,
    )
    await answer.prepare(AnswerQuery(member(), "¿Preaviso?"))
    assert search.organizations == [ORG, ORG]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (NO_EVIDENCE_ANSWER, True),
        ("  No encontré evidencia suficiente en los fragmentos.", True),
        ("El preaviso es de un mes [1].", False),
        ("Según [1], no encontré evidencia de otra cosa.", False),
    ],
)
def test_is_no_evidence(answer: str, expected: bool) -> None:
    assert is_no_evidence(answer) is expected
