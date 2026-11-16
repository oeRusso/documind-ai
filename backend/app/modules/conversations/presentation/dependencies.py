"""Wires the conversations use cases with their SQL implementations."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Request, Response

from app.core.dependencies import SessionDep
from app.modules.auth.presentation.dependencies import CurrentMemberDep
from app.modules.conversations.application.manage_conversations import (
    DeleteConversation,
    GetConversation,
    ListConversations,
    RateAnswer,
    StartConversation,
    UpdateConversation,
)
from app.modules.conversations.application.send_message import SendMessage
from app.modules.conversations.infrastructure.sql_repository import (
    SqlAnswerRecorder,
    SqlConversationRepository,
)
from app.modules.knowledge.presentation.chat_router import AnswerQuestionDep
from app.shared.demo import DEMO_USER_ID

DEMO_VISITOR_COOKIE = "demo_visitor"
DEMO_VISITOR_MAX_AGE = 7 * 24 * 3600  # the history is deleted every night anyway


def demo_visitor(request: Request, response: Response, member: CurrentMemberDep) -> UUID | None:
    """The browser that uses the shared demo account; None for every other account.

    A random id in an HttpOnly cookie (JavaScript cannot read it): it only scopes the demo
    history, it grants nothing. Missing or invalid -> a new one, so a forged value just starts
    an empty history. The cookie is set on the JSON endpoints (the page lists or starts a
    conversation before asking), not on the streamed answer.
    """
    if member.user_id != DEMO_USER_ID:
        return None
    try:
        return UUID(request.cookies[DEMO_VISITOR_COOKIE])
    except (KeyError, ValueError):
        visitor = uuid4()  # random (v4): it must not be guessable, unlike our ordered v7 ids
        response.set_cookie(
            DEMO_VISITOR_COOKIE,
            str(visitor),
            max_age=DEMO_VISITOR_MAX_AGE,
            path="/api/v1/conversations",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return visitor


DemoVisitorDep = Annotated[UUID | None, Depends(demo_visitor)]


def _repository(session: SessionDep, visitor: DemoVisitorDep) -> SqlConversationRepository:
    return SqlConversationRepository(session, demo_visitor_id=visitor)


RepositoryDep = Annotated[SqlConversationRepository, Depends(_repository)]


def provide_start(conversations: RepositoryDep) -> StartConversation:
    return StartConversation(conversations)


def provide_list(conversations: RepositoryDep) -> ListConversations:
    return ListConversations(conversations)


def provide_get(conversations: RepositoryDep) -> GetConversation:
    return GetConversation(conversations)


def provide_update(conversations: RepositoryDep) -> UpdateConversation:
    return UpdateConversation(conversations)


def provide_delete(conversations: RepositoryDep) -> DeleteConversation:
    return DeleteConversation(conversations)


def provide_rate(conversations: RepositoryDep) -> RateAnswer:
    return RateAnswer(conversations)


def provide_send_message(
    request: Request, conversations: RepositoryDep, answers: AnswerQuestionDep
) -> SendMessage:
    return SendMessage(
        conversations,
        answers,
        SqlAnswerRecorder(request.app.state.session_factory),
    )
