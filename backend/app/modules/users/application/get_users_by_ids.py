"""Use case: look up several users at once. Other modules use it to show who is who
(e.g. the email of each member of an organization) without touching the users table."""

from collections.abc import Collection
from uuid import UUID

from app.modules.users.domain.entities import User
from app.modules.users.domain.repository import UserRepository


class GetUsersByIds:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def execute(self, user_ids: Collection[UUID]) -> dict[UUID, User]:
        users = await self._repository.list_by_ids(set(user_ids))
        return {user.id: user for user in users}
