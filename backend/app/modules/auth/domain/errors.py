from app.shared.errors import UnauthorizedError


class InvalidTokenError(UnauthorizedError):
    code = "invalid_token"
    message = "La sesión no es válida o venció"


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"
    message = "Email o contraseña incorrectos"
    # The "login failed" audit event must survive the error (see DomainError.keep_changes).
    keep_changes = True
