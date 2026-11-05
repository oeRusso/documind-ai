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


class ValidationError(DomainError):
    code = "invalid_data"
    message = "Datos inválidos"
