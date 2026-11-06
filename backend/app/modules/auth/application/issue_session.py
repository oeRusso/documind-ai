"""Issue a session: a short access token plus a refresh token (ADR 0004).

Not a use case on its own: Register, Login and RefreshSession use it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.modules.auth.domain.refresh_tokens import RefreshToken, RefreshTokenRepository
from app.modules.auth.domain.tokens import AccessToken, AccessTokenCodec
from app.shared.ids import new_id, utc_now
from app.shared.secure_tokens import generate_token, hash_token


@dataclass(frozen=True, slots=True)
class IssuedSession:
    user_id: UUID
    access_token: AccessToken
    # The raw refresh token: goes into the HttpOnly cookie and is never stored.
    refresh_token: str
    refresh_expires_at: datetime
    refresh_token_id: UUID


class IssueSession:
    def __init__(
        self,
        refresh_tokens: RefreshTokenRepository,
        access_tokens: AccessTokenCodec,
        refresh_lifetime: timedelta,
        *,
        id_factory: Callable[[], UUID] = new_id,
        clock: Callable[[], datetime] = utc_now,
        token_factory: Callable[[], str] = generate_token,
    ) -> None:
        self._refresh_tokens = refresh_tokens
        self._access_tokens = access_tokens
        self._refresh_lifetime = refresh_lifetime
        self._id_factory = id_factory
        self._clock = clock
        self._token_factory = token_factory

    async def start(self, user_id: UUID) -> IssuedSession:
        """A brand-new session (login, registration): a new token family."""
        return await self.continue_family(user_id, family_id=self._id_factory())

    async def continue_family(self, user_id: UUID, family_id: UUID) -> IssuedSession:
        """The next token of an existing session (refresh)."""
        now = self._clock()
        raw = self._token_factory()
        token = RefreshToken(
            id=self._id_factory(),
            user_id=user_id,
            family_id=family_id,
            token_hash=hash_token(raw),
            expires_at=now + self._refresh_lifetime,
            created_at=now,
        )
        await self._refresh_tokens.add(token)
        return IssuedSession(
            user_id=user_id,
            access_token=self._access_tokens.issue(user_id),
            refresh_token=raw,
            refresh_expires_at=token.expires_at,
            refresh_token_id=token.id,
        )
