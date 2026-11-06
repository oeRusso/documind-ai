from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.users.domain.entities import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    User,
    normalize_email,
    validate_password,
)
from app.modules.users.domain.errors import InvalidEmailError, WeakPasswordError
from app.modules.users.infrastructure.argon2_hasher import Argon2PasswordHasher

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("ana@example.com", "ana@example.com"), ("  Ana@Example.COM ", "ana@example.com")],
)
def test_email_is_normalized(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "ana", "ana@", "@example.com", "ana@example", "a b@example.com", "a@b@c.com"]
)
def test_invalid_emails_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidEmailError):
        normalize_email(raw)


def test_too_long_email_is_rejected() -> None:
    with pytest.raises(InvalidEmailError):
        normalize_email("a" * 250 + "@x.com")


@pytest.mark.parametrize(
    "password",
    ["x" * (PASSWORD_MIN_LENGTH - 1), "x" * (PASSWORD_MAX_LENGTH + 1), " " * PASSWORD_MIN_LENGTH],
)
def test_weak_passwords_are_rejected(password: str) -> None:
    with pytest.raises(WeakPasswordError):
        validate_password(password)


def test_long_passphrase_without_symbols_is_fine() -> None:
    validate_password("caballo correcto bateria grapa")


def test_new_user_is_active_with_normalized_email() -> None:
    user = User.create(id=UUID(int=1), email=" Ana@Example.com", password_hash="h", now=NOW)

    assert user.email == "ana@example.com"
    assert user.is_active is True
    assert user.created_at == user.updated_at == NOW


async def test_argon2id_hash_and_verify() -> None:
    hasher = Argon2PasswordHasher()

    password_hash = await hasher.hash("una contraseña larga")

    assert password_hash.startswith("$argon2id$")
    assert "una contraseña larga" not in password_hash
    assert await hasher.verify(password_hash, "una contraseña larga") is True
    assert await hasher.verify(password_hash, "otra contraseña") is False


async def test_same_password_gets_a_different_hash_each_time() -> None:
    hasher = Argon2PasswordHasher()

    # Random salt: two users with the same password do not share a hash.
    assert await hasher.hash("misma clave 123") != await hasher.hash("misma clave 123")


async def test_verify_with_a_malformed_hash_is_false_not_an_error() -> None:
    assert await Argon2PasswordHasher().verify("not-a-hash", "whatever123") is False
