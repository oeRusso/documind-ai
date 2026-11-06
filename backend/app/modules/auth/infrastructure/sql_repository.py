"""RefreshTokenRepository implemented with SQLAlchemy. Identity table: no RLS (ADR 0003)."""

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
