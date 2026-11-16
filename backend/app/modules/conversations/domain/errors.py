"""Errors of the conversations module."""

from app.shared.errors import NotFoundError, ValidationError


class ConversationNotFoundError(NotFoundError):
    """Also for conversations of another person or organization: they do not exist from here."""

    code = "conversation_not_found"
    message = "Conversación no encontrada"


class MessageNotFoundError(NotFoundError):
    code = "message_not_found"
    message = "Mensaje no encontrado"


class FeedbackOnlyForAnswersError(ValidationError):
    code = "feedback_only_for_answers"
    message = "Solo se pueden valorar las respuestas"


class TooManyScopeDocumentsError(ValidationError):
    code = "too_many_scope_documents"
    message = "Elegí como mucho 50 documentos"
