"""SqlRefreshTokenRepository: rotation and family revocation against PostgreSQL."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.issue_session import IssuedSession, IssueSession
from app.modules.auth.domain.refresh_tokens import RefreshToken
from app.modules.auth.infrastructure.jwt_codec import JwtAccessTokenCodec
from app.modules.auth.infrastructure.sql_repository import SqlRefreshTokenRepository
from app.shared.secure_tokens import hash_token
from tests.conftest import TEST_JWT_SECRET
from tests.integration.factories import create_user

LATER = datetime(2026, 11, 7, tzinfo=UTC)


async def stored(repository: SqlRefreshTokenRepository, session: IssuedSession) -> RefreshToken:
    token = await repository.get_by_hash_for_update(hash_token(session.refresh_token))
    assert token is not None
    return token


async def test_rotation_and_family_revocation(app_session: AsyncSession) -> None:
    user = await create_user(app_session)
    repository = SqlRefreshTokenRepository(app_session)
    issue = IssueSession(
        repository, JwtAccessTokenCodec(TEST_JWT_SECRET, timedelta(minutes=15)), timedelta(days=14)
    )
    first = await issue.start(user.id)
    family_id = (await stored(repository, first)).family_id
    second = await issue.continue_family(user.id, family_id)
    other_login = await issue.start(user.id)

    await repository.mark_replaced(first.refresh_token_id, second.refresh_token_id, LATER)
    revoked = await repository.revoke_family(family_id, LATER)

    old, new = await stored(repository, first), await stored(repository, second)
    assert revoked == 2
    assert old.replaced_by_id == second.refresh_token_id
    assert old.revoked_at == new.revoked_at == LATER
    assert (await stored(repository, other_login)).revoked_at is None
