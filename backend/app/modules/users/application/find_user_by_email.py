"""Use case: find a user by email (already normalized), or None."""

from app.modules.users.domain.entities import User, normalize_email
from app.modules.users.domain.repository import UserRepository


class FindUserByEmail:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def execute(self, email: str) -> User | None:
        return await self._repository.get_by_email(normalize_email(email))
