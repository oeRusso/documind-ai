import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest

from app.modules.auth.domain.errors import InvalidTokenError
from app.modules.auth.infrastructure.jwt_codec import JwtAccessTokenCodec
from app.shared.secure_tokens import generate_token, hash_token

SECRET = "unit-test-secret-0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
USER_ID = UUID("0192f1c4-0000-7000-8000-0000000000c1")


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def make_codec(clock: Clock, secret: str = SECRET) -> JwtAccessTokenCodec:
    return JwtAccessTokenCodec(secret, timedelta(minutes=15), clock=clock)


def test_issued_token_can_be_read_back() -> None:
    codec = make_codec(Clock(NOW))

    token = codec.issue(USER_ID)
    claims = codec.read(token.value)

    assert claims.user_id == USER_ID
    assert claims.expires_at == token.expires_at == NOW + timedelta(minutes=15)


def test_token_ids_are_unique() -> None:
    codec = make_codec(Clock(NOW))

    assert (
        codec.read(codec.issue(USER_ID).value).token_id
        != codec.read(codec.issue(USER_ID).value).token_id
    )


def test_token_expires_after_its_lifetime() -> None:
    clock = Clock(NOW)
    codec = make_codec(clock)
    token = codec.issue(USER_ID).value

    clock.now = NOW + timedelta(minutes=14, seconds=59)
    codec.read(token)  # still valid

    clock.now = NOW + timedelta(minutes=15)
    with pytest.raises(InvalidTokenError):
        codec.read(token)


def test_token_signed_with_another_secret_is_rejected() -> None:
    forged = make_codec(Clock(NOW), secret="another-secret-0123456789abcdef0123456789").issue(
        USER_ID
    )

    with pytest.raises(InvalidTokenError):
        make_codec(Clock(NOW)).read(forged.value)


def test_unsigned_alg_none_token_is_rejected() -> None:
    def b64(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    claims = {"sub": str(USER_ID), "type": "access", "iat": 0, "exp": 9999999999, "jti": "x"}
    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."

    with pytest.raises(InvalidTokenError):
        make_codec(Clock(NOW)).read(unsigned)


def test_token_of_another_type_is_rejected() -> None:
    payload = {
        "sub": str(USER_ID),
        "type": "refresh",
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        "jti": str(USER_ID),
    }

    with pytest.raises(InvalidTokenError):
        make_codec(Clock(NOW)).read(jwt.encode(payload, SECRET, algorithm="HS256"))


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer xyz"])
def test_garbage_is_rejected(garbage: str) -> None:
    with pytest.raises(InvalidTokenError):
        make_codec(Clock(NOW)).read(garbage)


def test_access_token_does_not_carry_organization_or_role() -> None:
    token = make_codec(Clock(NOW)).issue(USER_ID).value

    payload = jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False})

    assert set(payload) == {"sub", "type", "iat", "exp", "jti"}


def test_opaque_tokens_are_random_and_hashed() -> None:
    first, second = generate_token(), generate_token()

    assert first != second
    assert len(first) >= 43
    assert len(hash_token(first)) == 64
    assert hash_token(first) == hash_token(first)
    assert first not in hash_token(first)
