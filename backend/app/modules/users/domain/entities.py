"""User entity and the rules for emails and passwords. Pure Python."""

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.users.domain.errors import InvalidEmailError, WeakPasswordError

EMAIL_MAX_LENGTH = 254
# Deliberately simple: something@something.tld, no spaces. Real validation is the invitation
# link reaching the inbox; strict regexes reject valid addresses.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# NIST SP 800-63B: length matters, composition rules ("one symbol, one digit") do not.
PASSWORD_MIN_LENGTH = 10
# Upper bound so nobody can make the server hash a 1 MB "password".
PASSWORD_MAX_LENGTH = 128


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > EMAIL_MAX_LENGTH or not _EMAIL_PATTERN.fullmatch(email):
        raise InvalidEmailError()
    return email


def validate_password(password: str) -> None:
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise WeakPasswordError(
            f"La contraseña debe tener entre {PASSWORD_MIN_LENGTH} "
            f"y {PASSWORD_MAX_LENGTH} caracteres"
        )
    if password.strip() == "":
        raise WeakPasswordError("La contraseña no puede ser solo espacios")


@dataclass(slots=True)
class User:
    id: UUID
    email: str
    password_hash: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, *, id: UUID, email: str, password_hash: str, now: datetime) -> "User":
        return cls(
            id=id,
            email=normalize_email(email),
            password_hash=password_hash,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
