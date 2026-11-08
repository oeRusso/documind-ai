"""UserRepository implemented with SQLAlchemy (PostgreSQL)."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.domain.entities import User
from app.modules.users.domain.errors import EmailAlreadyRegisteredError
from app.modules.users.infrastructure.models import UserModel


def _to_entity(model: UserModel) -> User:
    return User(
        id=model.id,
        email=model.email,
        password_hash=model.password_hash,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlUserRepository:
    """Does not commit: the transaction belongs to the request (see get_session)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        self._session.add(
            UserModel(
                id=user.id,
                email=user.email,
                password_hash=user.password_hash,
                is_active=user.is_active,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
        )
        try:
            await self._session.flush()  # sends the INSERT now, so constraint errors surface here
        except IntegrityError as exc:
            raise EmailAlreadyRegisteredError() from exc

    async def get_by_id(self, user_id: UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return _to_entity(model) if model else None

    async def list_by_ids(self, user_ids: Collection[UUID]) -> list[User]:
        if not user_ids:
            return []
        result = await self._session.execute(
            select(UserModel).where(UserModel.id.in_(list(user_ids)))
        )
        return [_to_entity(model) for model in result.scalars()]

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(UserModel).where(UserModel.email == email))
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None
