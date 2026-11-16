from app.shared.errors import ForbiddenError, UnauthorizedError


class RegistrationClosedError(ForbiddenError):
    """REGISTRATION_OPEN=false: only people invited by an organization can create an account."""

    code = "registration_closed"
    message = "El registro está cerrado: entrá con una invitación o probá la demo"


class InvalidTokenError(UnauthorizedError):
    code = "invalid_token"
    message = "La sesión no es válida o venció"


class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"
    message = "Email o contraseña incorrectos"
    # The "login failed" audit event must survive the error (see DomainError.keep_changes).
    keep_changes = True


class RefreshTokenReuseError(UnauthorizedError):
    """A refresh token that was already exchanged came back: someone may have copied it."""

    code = "session_revoked"
    message = "Por seguridad cerramos tu sesión. Iniciá sesión de nuevo."
    # The family revocation and its audit event must survive the error response.
    keep_changes = True
