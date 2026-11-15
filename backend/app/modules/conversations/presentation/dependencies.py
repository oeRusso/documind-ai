"""Wires the conversations use cases with their SQL implementations."""

from fastapi import Request

from app.core.dependencies import SessionDep
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


def provide_start(session: SessionDep) -> StartConversation:
    return StartConversation(SqlConversationRepository(session))


def provide_list(session: SessionDep) -> ListConversations:
    return ListConversations(SqlConversationRepository(session))


def provide_get(session: SessionDep) -> GetConversation:
    return GetConversation(SqlConversationRepository(session))


def provide_update(session: SessionDep) -> UpdateConversation:
    return UpdateConversation(SqlConversationRepository(session))


def provide_delete(session: SessionDep) -> DeleteConversation:
    return DeleteConversation(SqlConversationRepository(session))


def provide_rate(session: SessionDep) -> RateAnswer:
    return RateAnswer(SqlConversationRepository(session))


def provide_send_message(
    request: Request, session: SessionDep, answers: AnswerQuestionDep
) -> SendMessage:
    return SendMessage(
        SqlConversationRepository(session),
        answers,
        SqlAnswerRecorder(request.app.state.session_factory),
    )
