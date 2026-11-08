from app.shared.errors import ConflictError, ValidationError


class InvalidEmailError(ValidationError):
    code = "invalid_email"
    message = "El email no es válido"


class WeakPasswordError(ValidationError):
    code = "weak_password"
    message = "La contraseña no cumple los requisitos"


class EmailAlreadyRegisteredError(ConflictError):
    code = "email_already_registered"
    message = "Ya existe una cuenta con ese email"
