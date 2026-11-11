"""Business errors shared by every module.

They are plain Python (no HTTP, no FastAPI): `domain` and `application` raise them, and
`app/core/exceptions.py` translates them to HTTP responses with the uniform error format.
"""

from typing import Any, ClassVar


class DomainError(Exception):
    """Base class. Subclasses override `code` and `message` (UI text, in Spanish)."""

    code: str = "domain_error"
    message: str = "La operación no es válida"
    # Normally an error rolls the request's transaction back. A few security errors set this
    # to True: what was written before raising (an audit event, a revoked session) is
    # committed anyway, and then the error response is sent. See get_session.
    keep_changes: ClassVar[bool] = False

    def __init__(
        self, message: str | None = None, *, details: list[dict[str, Any]] | None = None
    ) -> None:
        if message is not None:
            self.message = message
        # Extra machine-readable data for the client (e.g. the id of an existing duplicate).
        self.details = details
        super().__init__(self.message)


class NotFoundError(DomainError):
    code = "not_found"
    message = "Recurso no encontrado"


class ConflictError(DomainError):
    code = "conflict"
    message = "El recurso ya existe"


class UnauthorizedError(DomainError):
    """Not authenticated (no session, or an invalid or expired one). HTTP 401."""

    code = "unauthorized"
    message = "Tenés que iniciar sesión"


class ForbiddenError(DomainError):
    """Authenticated, but the role inside *this* organization does not allow it. HTTP 403.

    Resources of another organization are NOT this: they are NotFoundError (404).
    """

    code = "forbidden"
    message = "No tenés permiso para hacer esto"


class ValidationError(DomainError):
    code = "invalid_data"
    message = "Datos inválidos"


class PayloadTooLargeError(DomainError):
    """The request body or the uploaded file is bigger than allowed. HTTP 413."""

    code = "payload_too_large"
    message = "El archivo es demasiado grande"


class UnsupportedMediaTypeError(DomainError):
    """The content is not of an accepted type (checked by its bytes, not its name). HTTP 415."""

    code = "unsupported_media_type"
    message = "Tipo de archivo no permitido"


class TooManyRequestsError(DomainError):
    """Too many attempts in a short time. HTTP 429 with a Retry-After header."""

    code = "rate_limited"
    message = "Demasiados intentos. Esperá un momento y probá de nuevo"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__()
        self.retry_after_seconds = retry_after_seconds


class ServiceUnavailableError(DomainError):
    """A dependency the request needs is not configured or is down. HTTP 503."""

    code = "service_unavailable"
    message = "El servicio no está disponible en este momento"
