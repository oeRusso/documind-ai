"""Business errors shared by every module.

They are plain Python (no HTTP, no FastAPI): `domain` and `application` raise them, and
`app/core/exceptions.py` translates them to HTTP responses with the uniform error format.
"""


class DomainError(Exception):
    """Base class. Subclasses override `code` and `message` (UI text, in Spanish)."""

    code: str = "domain_error"
    message: str = "La operación no es válida"

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
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
