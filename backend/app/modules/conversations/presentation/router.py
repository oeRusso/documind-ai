"""Conversations of the person in the active organization (stage 8).

- POST   /conversations                          start one (optional scope: some documents)
- GET    /conversations                          mine, newest first (cursor)
- GET    /conversations/{id}                     with its messages and saved citations
- PATCH  /conversations/{id}                     rename / change the scope
- DELETE /conversations/{id}
- POST   /conversations/{id}/messages            ask: Server-Sent Events, like POST /chat, plus a
                                                 first `message` event with the saved ids
- PUT    /conversations/{id}/messages/{mid}/feedback   útil / no útil

Another person's conversation, or one of another organization, is 404.
"""

from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.ai.providers.llm import LLMServiceError
from app.core.dependencies import SessionDep
from app.core.exceptions import ErrorResponse
from app.core.pagination import Page
from app.core.request_context import current_request_id
from app.modules.auth.presentation.dependencies import CurrentMemberDep
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
    ConversationEvent,
    MessageStarted,
    PreparedMessage,
    SendMessage,
    SendMessageCommand,
)
from app.modules.conversations.presentation.dependencies import (
    provide_delete,
    provide_get,
    provide_list,
    provide_rate,
    provide_send_message,
    provide_start,
    provide_update,
)
from app.modules.conversations.presentation.schemas import (
    ConversationCreate,
    ConversationDetailRead,
    ConversationRead,
    ConversationUpdate,
    FeedbackUpdate,
    MessageCreate,
    MessageRead,
)
from app.modules.knowledge.presentation.chat_router import answer_event_to_sse, limit_chat_by_user

logger = structlog.get_logger("app.conversations")

router = APIRouter(prefix="/conversations", tags=["conversations"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}
_ASK_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


@router.post("", status_code=status.HTTP_201_CREATED, responses=_ERRORS)
async def start_conversation(
    body: ConversationCreate,
    member: CurrentMemberDep,
    use_case: Annotated[StartConversation, Depends(provide_start)],
) -> ConversationRead:
    """Empieza una conversación. Sin `document_ids` pregunta sobre todos los documentos."""
    return ConversationRead.build(await use_case.execute(member, document_ids=body.document_ids))


@router.get("", responses=_ERRORS)
async def list_conversations(
    member: CurrentMemberDep,
    use_case: Annotated[ListConversations, Depends(provide_list)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[UUID | None, Query(description="`next_cursor` de la página anterior")] = None,
) -> Page[ConversationRead]:
    """Tus conversaciones en la organización activa, de la más nueva a la más vieja."""
    page = await use_case.execute(member, limit=limit, before_id=cursor)
    return Page(
        items=[ConversationRead.build(c) for c in page.items],
        next_cursor=str(page.next_before_id) if page.next_before_id else None,
    )


@router.get("/{conversation_id}", responses=_ERRORS)
async def get_conversation(
    conversation_id: UUID,
    member: CurrentMemberDep,
    use_case: Annotated[GetConversation, Depends(provide_get)],
) -> ConversationDetailRead:
    """Una conversación con sus mensajes (el más viejo primero) y las citas de cada respuesta."""
    detail = await use_case.execute(member, conversation_id)
    return ConversationDetailRead(
        **ConversationRead.build(detail.conversation).model_dump(),
        messages=[MessageRead.build(m) for m in detail.messages],
    )


@router.patch("/{conversation_id}", responses=_ERRORS)
async def update_conversation(
    conversation_id: UUID,
    body: ConversationUpdate,
    member: CurrentMemberDep,
    use_case: Annotated[UpdateConversation, Depends(provide_update)],
) -> ConversationRead:
    """Cambia el título o el alcance (los documentos sobre los que se pregunta)."""
    updated = await use_case.execute(
        UpdateConversationCommand(
            member,
            conversation_id,
            title=body.title,
            document_ids=body.document_ids,
            change_scope="document_ids" in body.model_fields_set,
        )
    )
    return ConversationRead.build(updated)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_conversation(
    conversation_id: UUID,
    member: CurrentMemberDep,
    use_case: Annotated[DeleteConversation, Depends(provide_delete)],
) -> Response:
    """Borra la conversación con sus mensajes. No se puede deshacer."""
    await use_case.execute(member, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


SendMessageDep = Annotated[SendMessage, Depends(provide_send_message)]


async def prepare_message(
    conversation_id: UUID,
    body: MessageCreate,
    member: CurrentMemberDep,
    use_case: SendMessageDep,
    session: SessionDep,
    _: Annotated[None, Depends(limit_chat_by_user)],
) -> PreparedMessage:
    prepared = await use_case.prepare(SendMessageCommand(member, conversation_id, body.question))
    # Commit NOW, not when the request ends: FastAPI starts the SSE generator in its own task
    # before closing the request's dependencies, so the answer could finish (and be saved by
    # AnswerRecorder in another transaction) before the question rows were visible.
    await session.commit()
    return prepared


def _to_sse(event: ConversationEvent) -> ServerSentEvent:
    if isinstance(event, MessageStarted):
        return ServerSentEvent(
            event="message",
            data={
                "conversation_id": str(event.conversation_id),
                "question_id": str(event.question_id),
                "answer_id": str(event.answer_id),
            },
        )
    return answer_event_to_sse(event)


@router.post(
    "/{conversation_id}/messages", response_class=EventSourceResponse, responses=_ASK_ERRORS
)
async def send_message(
    prepared: Annotated[PreparedMessage, Depends(prepare_message)],
    use_case: SendMessageDep,
) -> AsyncIterator[ServerSentEvent]:
    """Pregunta dentro de la conversación. La pregunta anterior da contexto a la búsqueda.

    Server-Sent Events: `message` (ids guardados), `queued`, `token`, `citations`, `done`, o
    `error` si el modelo falla. La pregunta y la respuesta quedan guardadas, también si se corta.
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


@router.put(
    "/{conversation_id}/messages/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
)
async def rate_answer(
    conversation_id: UUID,
    message_id: UUID,
    body: FeedbackUpdate,
    member: CurrentMemberDep,
    use_case: Annotated[RateAnswer, Depends(provide_rate)],
) -> Response:
    """Marca una respuesta como útil o no útil (null la quita). Las no útiles se revisan para
    sumarlas al dataset de evaluación."""
    await use_case.execute(RateAnswerCommand(member, conversation_id, message_id, body.feedback))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
