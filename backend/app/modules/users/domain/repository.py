"""Repository interface. `users` is an identity table: no organization_id (ADR 0003)."""

from typing import Protocol
from uuid import UUID

from app.modules.users.domain.entities import User


class UserRepository(Protocol):
    async def add(self, user: User) -> None:
        """Persist a new user. Raises EmailAlreadyRegisteredError on duplicate email."""
        ...

    async def get_by_id(self, user_id: UUID) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None:
        """`email` must already be normalized (see normalize_email)."""
        ...
