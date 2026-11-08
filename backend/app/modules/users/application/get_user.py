"""Use case: get an active user by id (sessions check the user still exists and is active)."""

from uuid import UUID

from app.modules.users.domain.entities import User
from app.modules.users.domain.repository import UserRepository


class GetActiveUser:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def execute(self, user_id: UUID) -> User | None:
        user = await self._repository.get_by_id(user_id)
        return user if user is not None and user.is_active else None
