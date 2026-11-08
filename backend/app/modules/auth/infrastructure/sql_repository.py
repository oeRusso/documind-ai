"""RefreshTokenRepository implemented with SQLAlchemy. Identity table: no RLS (ADR 0003)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.domain.refresh_tokens import RefreshToken
from app.modules.auth.infrastructure.models import RefreshTokenModel


def _to_entity(model: RefreshTokenModel) -> RefreshToken:
    return RefreshToken(
        id=model.id,
        user_id=model.user_id,
        family_id=model.family_id,
        token_hash=model.token_hash,
        expires_at=model.expires_at,
        created_at=model.created_at,
        revoked_at=model.revoked_at,
        replaced_by_id=model.replaced_by_id,
    )


class SqlRefreshTokenRepository:
    """Does not commit: the transaction belongs to the request (see get_session)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: RefreshToken) -> None:
        self._session.add(
            RefreshTokenModel(
                id=token.id,
                user_id=token.user_id,
                family_id=token.family_id,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
                revoked_at=token.revoked_at,
                replaced_by_id=token.replaced_by_id,
                created_at=token.created_at,
                updated_at=token.created_at,
            )
        )
        await self._session.flush()

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshTokenModel)
            .where(RefreshTokenModel.token_hash == token_hash)
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def mark_replaced(self, token_id: UUID, replaced_by_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.id == token_id)
            .values(replaced_by_id=replaced_by_id, updated_at=now)
        )

    async def revoke_family(self, family_id: UUID, now: datetime) -> int:
        result = await self._session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.family_id == family_id,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=now, updated_at=now)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]
