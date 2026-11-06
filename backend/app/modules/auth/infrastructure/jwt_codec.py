"""AccessTokenCodec with signed JWTs (PyJWT, HS256). See ADR 0004.

The token only says *who* the user is. Organization and role are read from the database on
every request, so a removed member loses access immediately (ADR 0003).
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.modules.auth.domain.errors import InvalidTokenError
from app.modules.auth.domain.tokens import AccessToken, AccessTokenClaims
from app.shared.ids import new_id, utc_now

ALGORITHM = "HS256"
TOKEN_TYPE = "access"  # noqa: S105 - a claim value, not a secret
_REQUIRED_CLAIMS = ["sub", "type", "iat", "exp", "jti"]


class JwtAccessTokenCodec:
    def __init__(
        self,
        secret: str,
        lifetime: timedelta,
        *,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[], UUID] = new_id,
    ) -> None:
        self._secret = secret
        self._lifetime = lifetime
        self._clock = clock
        self._id_factory = id_factory

    def issue(self, user_id: UUID) -> AccessToken:
        # JWT times are whole seconds; drop microseconds so expires_at matches the token.
        now = self._clock().replace(microsecond=0)
        expires_at = now + self._lifetime
        payload = {
            "sub": str(user_id),
            "type": TOKEN_TYPE,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": str(self._id_factory()),
        }
        return AccessToken(
            value=jwt.encode(payload, self._secret, algorithm=ALGORITHM), expires_at=expires_at
        )

    def read(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                # A fixed list: a token that says "alg: none" (or any other) is rejected.
                algorithms=[ALGORITHM],
                # Expiry is checked below against the injected clock, so tests control time.
                options={"require": _REQUIRED_CLAIMS, "verify_exp": False},
            )
            user_id = UUID(payload["sub"])
            token_id = UUID(payload["jti"])
            expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise InvalidTokenError() from exc

        if payload["type"] != TOKEN_TYPE or expires_at <= self._clock():
            raise InvalidTokenError()
        return AccessTokenClaims(user_id=user_id, token_id=token_id, expires_at=expires_at)
