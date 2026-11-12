"""Use case: answer a question with the organization's documents, citing them (stage 7).

The flow (Parte 1, §6, "Flujo de una pregunta"):
1. Search (hybrid, same as the search page), filtered by organization inside the query.
2. If the closest chunk is not close enough (RAG_MIN_SCORE), answer "no encontré evidencia"
   WITHOUT calling the model: no chunk, no invention, and no CPU spent.
3. Build the context: best chunks within the token budget, numbered [1], [2]...
4. Wait for a free place in the generation line (LLM_MAX_CONCURRENCY).
5. Generate in streaming; each piece goes through the citation filter, which drops markers that
   point to no chunk.
6. Report the citations really used (document, pages, excerpt) and finish.

It has two halves on purpose: `prepare` does everything that can fail with a normal error (403,
422, 503) before the HTTP response starts; `stream` is what goes out as Server-Sent Events.
"""

import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from uuid import UUID

import structlog

from app.ai.concurrency import GenerationQueue
from app.ai.providers.llm import ChatMessage, LLMProvider
from app.modules.knowledge.application.prompt import NO_EVIDENCE_ANSWER, build_messages
from app.modules.knowledge.application.search_documents import SearchDocuments, SearchQuery
from app.modules.knowledge.domain.answer import (
    AnswerEvent,
    Citation,
    CitationsReady,
    Done,
    Queued,
    Token,
)
from app.modules.knowledge.domain.citations import MarkerFilter
from app.modules.knowledge.domain.context import ContextSource, build_context
from app.modules.knowledge.domain.search import SearchMode
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.permissions import Permission, ensure_permission
from app.shared.errors import ServiceUnavailableError, ValidationError

logger = structlog.get_logger("app.knowledge")

MAX_QUESTION_CHARS = 1000
CANDIDATES = 8  # chunks considered for the context (the budget decides how many go in)
EXCERPT_CHARS = 300


class EmptyQuestionError(ValidationError):
    code = "empty_question"
    message = "Escribí tu pregunta"


class ChatUnavailableError(ServiceUnavailableError):
    code = "chat_unavailable"
    message = "Las respuestas con IA no están disponibles en este momento"


@dataclass(frozen=True, slots=True)
class AnswerOptions:
    min_score: float  # RAG_MIN_SCORE
    context_tokens: int  # RAG_CONTEXT_TOKENS
    max_answer_tokens: int  # RAG_MAX_ANSWER_TOKENS


@dataclass(frozen=True, slots=True)
class AnswerQuery:
    actor: Membership
    question: str
    document_ids: Sequence[UUID] | None = None


@dataclass(frozen=True, slots=True)
class PreparedAnswer:
    """Everything decided before generating. No sources = answer "no encontré evidencia"."""

    organization_id: UUID
    question: str
    sources: list[ContextSource]
    messages: list[ChatMessage]
    best_similarity: float | None

    @property
    def has_evidence(self) -> bool:
        return bool(self.sources)


def excerpt(text: str, limit: int = EXCERPT_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def is_no_evidence(answer: str) -> bool:
    """The model was told to answer exactly NO_EVIDENCE_ANSWER; small models paraphrase a bit."""
    start = answer.strip().lower()[:120]
    return start.startswith(NO_EVIDENCE_ANSWER.lower()[:20])  # "no encontré evidenci"


class AnswerQuestion:
    def __init__(
        self,
        search: SearchDocuments,
        llm: LLMProvider | None,
        queue: GenerationQueue,
        options: AnswerOptions,
    ) -> None:
        self._search = search
        self._llm = llm
        self._queue = queue
        self._options = options

    async def prepare(self, query: AnswerQuery) -> PreparedAnswer:
        ensure_permission(query.actor.role, Permission.VIEW_DOCUMENTS)
        question = " ".join(query.question.split())[:MAX_QUESTION_CHARS]
        if not question:
            raise EmptyQuestionError()
        if self._llm is None:
            raise ChatUnavailableError()

        result = await self._search.execute(
            SearchQuery(
                query.actor,
                question,
                mode=SearchMode.HYBRID,
                limit=CANDIDATES,
                document_ids=query.document_ids,
            )
        )
        enough = bool(result.hits) and (
            # Without embeddings there is no similarity to judge: any word match will do.
            result.best_similarity is None or result.best_similarity >= self._options.min_score
        )
        sources = (
            build_context(
                [hit.match for hit in result.hits], budget_tokens=self._options.context_tokens
            )
            if enough
            else []
        )
        return PreparedAnswer(
            organization_id=query.actor.organization_id,
            question=question,
            sources=sources,
            messages=build_messages(question, sources) if sources else [],
            best_similarity=result.best_similarity,
        )

    async def stream(self, prepared: PreparedAnswer) -> AsyncIterator[AnswerEvent]:
        log = logger.bind(
            organization_id=str(prepared.organization_id),
            best_similarity=prepared.best_similarity,
            sources=len(prepared.sources),
        )
        if not prepared.has_evidence or self._llm is None:
            log.info("answer_without_evidence", called_llm=False)
            yield Token(NO_EVIDENCE_ANSWER)
            yield CitationsReady([])
            yield Done(no_evidence=True)
            return

        async with self._queue.ticket() as ticket:
            waited_from = time.perf_counter()
            async for position in self._queue.positions(ticket):
                if position > 0:
                    yield Queued(position)
            started = time.perf_counter()

            markers = MarkerFilter({source.marker for source in prepared.sources})
            answer: list[str] = []
            async for piece in self._llm.stream(
                prepared.messages, max_tokens=self._options.max_answer_tokens
            ):
                shown = markers.feed(piece)
                if shown:
                    answer.append(shown)
                    yield Token(shown)
            rest = markers.finish()
            if rest:
                answer.append(rest)
                yield Token(rest)

        no_evidence = is_no_evidence("".join(answer))
        by_marker = {source.marker: source for source in prepared.sources}
        citations = (
            []
            if no_evidence
            else [
                Citation(
                    marker=n,
                    document_id=by_marker[n].document_id,
                    document_title=by_marker[n].document_title,
                    page_start=by_marker[n].page_start,
                    page_end=by_marker[n].page_end,
                    excerpt=excerpt(by_marker[n].content),
                )
                for n in markers.used
            ]
        )
        if markers.invalid:
            log.warning("invalid_citations_dropped", markers=markers.invalid)
        log.info(
            "answer_generated",
            called_llm=True,
            model=self._llm.model,
            no_evidence=no_evidence,
            waited_ms=round((started - waited_from) * 1000),
            generation_ms=round((time.perf_counter() - started) * 1000),
            answer_chars=sum(len(a) for a in answer),
            # Each citation: document, pages and the exact chunks (stage 7 keeps them in the
            # logs; stage 8 stores them in the `citations` table).
            citations=[
                {
                    "marker": c.marker,
                    "document_id": str(c.document_id),
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "chunk_ids": [str(i) for i in by_marker[c.marker].chunk_ids],
                }
                for c in citations
            ],
        )
        yield CitationsReady(citations)
        yield Done(no_evidence=no_evidence)
