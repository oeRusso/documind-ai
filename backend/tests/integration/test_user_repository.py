"""SqlUserRepository with the `app` role. `users` has no RLS (ADR 0003)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.domain.entities import User
from app.modules.users.domain.errors import EmailAlreadyRegisteredError
from app.modules.users.infrastructure.sql_repository import SqlUserRepository
from app.shared.ids import new_id

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def make_user(email: str = "ana@example.com") -> User:
    return User.create(id=new_id(), email=email, password_hash="$argon2id$fake", now=NOW)


async def test_add_then_get_by_email_and_id(app_session: AsyncSession) -> None:
    repository = SqlUserRepository(app_session)
    user = make_user()

    await repository.add(user)

    assert await repository.get_by_email("ana@example.com") == user
    assert await repository.get_by_id(user.id) == user
    assert await repository.get_by_email("nadie@example.com") is None


async def test_duplicate_email_is_a_conflict(app_session: AsyncSession) -> None:
    repository = SqlUserRepository(app_session)
    await repository.add(make_user("ana@example.com"))

    with pytest.raises(EmailAlreadyRegisteredError):
        await repository.add(make_user("ANA@example.com"))
