"""POST /api/v1/chat: ask a question, get the answer streamed as Server-Sent Events (stage 7).

Events, in order (Parte 1, §6, "Contrato de respuesta"):
- `queued`    {"position": 2}            only while waiting for a free place (2 = two before you)
- `token`     {"text": "El preaviso"}    a piece of the answer
- `citations` {"citations": [...]}       the sources really cited
- `done`      {"no_evidence": false}     the end
- `error`     {"code", "message", "request_id"} instead of the rest if the model fails midway

Everything that can fail with a normal error (401, 403, 422, 429, 503) happens in dependencies,
before the stream opens: the client gets the usual JSON error, not a broken stream.
"""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from app.ai.concurrency import GenerationQueue
from app.ai.providers.llm import LLMServiceError
from app.core.dependencies import SessionDep, SettingsDep
from app.core.exceptions import ErrorResponse
from app.core.rate_limits import RateLimiterDep
from app.core.request_context import current_request_id
from app.modules.auth.presentation.dependencies import CurrentMemberDep
from app.modules.knowledge.application.answer_question import (
    MAX_QUESTION_CHARS,
    AnswerOptions,
    AnswerQuery,
    AnswerQuestion,
    PreparedAnswer,
)
from app.modules.knowledge.application.search_documents import SearchDocuments
from app.modules.knowledge.domain.answer import (
    AnswerEvent,
    CitationsReady,
    Done,
    Queued,
    Token,
)
from app.modules.knowledge.infrastructure.sql_search import SqlChunkSearch
from app.shared.rate_limit import RateLimit

logger = structlog.get_logger("app.knowledge")

router = APIRouter(prefix="/chat", tags=["chat"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    document_ids: list[UUID] | None = Field(
        default=None, max_length=50, description="Limitar la búsqueda a estos documentos"
    )


class CitationRead(BaseModel):
    marker: int
    document_id: UUID
    document_title: str
    page_start: int | None
    page_end: int | None
    excerpt: str


def provide_answer_question(
    request: Request, session: SessionDep, settings: SettingsDep
) -> AnswerQuestion:
    queue: GenerationQueue = request.app.state.generation_queue
    return AnswerQuestion(
        SearchDocuments(SqlChunkSearch(session), request.app.state.embeddings),
        request.app.state.llm,
        queue,
        AnswerOptions(
            min_score=settings.rag_min_score,
            context_tokens=settings.rag_context_tokens,
            max_answer_tokens=settings.rag_max_answer_tokens,
        ),
    )


AnswerQuestionDep = Annotated[AnswerQuestion, Depends(provide_answer_question)]


async def limit_chat_by_user(
    member: CurrentMemberDep, limiter: RateLimiterDep, settings: SettingsDep
) -> None:
    rule = RateLimit(settings.chat_limit_per_user_per_minute, timedelta(minutes=1))
    await limiter.hit(f"chat:user:{member.user_id}", rule)


async def prepare_answer(
    body: ChatRequest,
    member: CurrentMemberDep,
    use_case: AnswerQuestionDep,
    _: Annotated[None, Depends(limit_chat_by_user)],
) -> PreparedAnswer:
    return await use_case.prepare(AnswerQuery(member, body.question, body.document_ids))


def _to_sse(event: AnswerEvent) -> ServerSentEvent:
    match event:
        case Queued(position=position):
            return ServerSentEvent(event="queued", data={"position": position})
        case Token(text=text):
            return ServerSentEvent(event="token", data={"text": text})
        case CitationsReady(citations=citations):
            items = [CitationRead.model_validate(c, from_attributes=True) for c in citations]
            return ServerSentEvent(
                event="citations", data={"citations": [i.model_dump(mode="json") for i in items]}
            )
        case Done(no_evidence=no_evidence):
            return ServerSentEvent(event="done", data={"no_evidence": no_evidence})


@router.post("", response_class=EventSourceResponse, responses=_ERRORS)
async def chat(
    prepared: Annotated[PreparedAnswer, Depends(prepare_answer)],
    use_case: AnswerQuestionDep,
) -> AsyncIterator[ServerSentEvent]:
    """Responde una pregunta con los documentos de la organización activa, citándolos.

    La respuesta llega como Server-Sent Events: `queued` (posición en la cola), `token` (texto
    parcial), `citations` (fuentes citadas) y `done`. Si el modelo falla a mitad de camino llega
    `error` en lugar del resto.
    """
    request_id = current_request_id()
    try:
        async for event in use_case.stream(prepared):
            yield _to_sse(event)
    except LLMServiceError as exc:
        logger.error("answer_failed", error=str(exc))
        yield ServerSentEvent(
            event="error",
            data={
                "code": "llm_failed",
                "message": "No se pudo generar la respuesta. Probá de nuevo en un momento",
                "request_id": request_id,
            },
        )
