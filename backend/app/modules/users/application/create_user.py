"""Use case: create a user with a hashed password. Called by auth (registration, invitations)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.users.domain.entities import User, normalize_email, validate_password
from app.modules.users.domain.passwords import PasswordHasher
from app.modules.users.domain.repository import UserRepository
from app.shared.ids import new_id, utc_now


@dataclass(frozen=True, slots=True)
class CreateUserCommand:
    email: str
    password: str


class CreateUser:
    def __init__(
        self,
        repository: UserRepository,
        hasher: PasswordHasher,
        *,
        id_factory: Callable[[], UUID] = new_id,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._hasher = hasher
        self._id_factory = id_factory
        self._clock = clock

    async def execute(self, command: CreateUserCommand) -> User:
        # Cheap checks first: never spend ~100 ms of Argon2 on a request that will fail anyway.
        email = normalize_email(command.email)
        validate_password(command.password)
        user = User.create(
            id=self._id_factory(),
            email=email,
            password_hash=await self._hasher.hash(command.password),
            now=self._clock(),
        )
        await self._repository.add(user)
        return user
