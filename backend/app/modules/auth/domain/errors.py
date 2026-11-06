from app.shared.errors import UnauthorizedError


class InvalidTokenError(UnauthorizedError):
    code = "invalid_token"
    message = "La sesión no es válida o venció"
