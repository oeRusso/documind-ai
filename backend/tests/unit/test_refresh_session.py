"""Refresh token rotation, reuse detection and logout (ADR 0004). Stage 2 criterion:
"reusing an already rotated refresh token invalidates the session"."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.auth.application.issue_session import IssuedSession, IssueSession
from app.modules.auth.application.logout import Logout, LogoutCommand
from app.modules.auth.application.refresh_session import RefreshSession, RefreshSessionCommand
from app.modules.auth.domain.errors import InvalidTokenError, RefreshTokenReuseError
from app.modules.auth.domain.refresh_tokens import RefreshToken
from app.modules.auth.infrastructure.jwt_codec import JwtAccessTokenCodec
from app.modules.users.application.get_user import GetActiveUser
from app.modules.users.domain.entities import User
from app.shared.ids import new_id
from app.shared.secure_tokens import hash_token
from tests.fakes import (
    InMemoryAuditLogRepository,
    InMemoryRefreshTokenRepository,
    InMemoryUserRepository,
)

START = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
SECRET = "unit-test-secret-0123456789abcdef0123456789abcdef"  # pragma: allowlist secret


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class World:
    def __init__(self) -> None:
        self.clock = Clock()
        self.users = InMemoryUserRepository()
        self.tokens = InMemoryRefreshTokenRepository()
        self.audit = InMemoryAuditLogRepository()
        self.issue = IssueSession(
            self.tokens,
            JwtAccessTokenCodec(SECRET, timedelta(minutes=15), clock=self.clock),
            timedelta(days=14),
            clock=self.clock,
        )
        record = RecordAuditEvent(self.audit, clock=self.clock)
        self.refresh = RefreshSession(
            self.tokens, self.issue, GetActiveUser(self.users), record, clock=self.clock
        )
        self.logout = Logout(self.tokens, record, clock=self.clock)
        self.user = User.create(id=new_id(), email="ana@example.com", password_hash="h", now=START)
        self.users.items[self.user.id] = self.user

    async def login(self) -> IssuedSession:
        return await self.issue.start(self.user.id)

    async def use(self, session: IssuedSession) -> IssuedSession:
        return await self.refresh.execute(RefreshSessionCommand(session.refresh_token))

    def stored(self, session: IssuedSession) -> RefreshToken:
        return self.tokens.items[session.refresh_token_id]


@pytest.fixture
def world() -> World:
    return World()


# --- Rotation ------------------------------------------------------------------------------


async def test_refresh_returns_new_tokens_in_the_same_family(world: World) -> None:
    first = await world.login()

    second = await world.use(first)

    assert second.refresh_token != first.refresh_token
    assert second.access_token.value != first.access_token.value
    assert world.stored(second).family_id == world.stored(first).family_id
    assert world.stored(first).replaced_by_id == second.refresh_token_id


async def test_rotation_can_go_on_while_each_token_is_used_once(world: World) -> None:
    session = await world.login()
    for _ in range(5):
        session = await world.use(session)

    assert world.stored(session).revoked_at is None


# --- Reuse (stage 2 criterion) -------------------------------------------------------------


async def test_reusing_a_rotated_token_revokes_the_whole_family(world: World) -> None:
    first = await world.login()
    second = await world.use(first)

    with pytest.raises(RefreshTokenReuseError):
        await world.use(first)  # someone replays the old token

    family = world.tokens.family(world.stored(first).family_id)
    assert all(token.revoked_at is not None for token in family)
    # ...so the legitimate newest token stops working too: the session is over.
    with pytest.raises(InvalidTokenError):
        await world.use(second)


async def test_reuse_is_audited_and_kept_after_the_error(world: World) -> None:
    first = await world.login()
    await world.use(first)

    with pytest.raises(RefreshTokenReuseError):
        await world.refresh.execute(RefreshSessionCommand(first.refresh_token, ip="198.51.100.9"))

    event = world.audit.events[-1]
    assert event.action == "auth.refresh_reuse_detected"
    assert event.user_id == world.user.id
    assert event.ip == "198.51.100.9"
    assert event.details == {"revoked_tokens": 2}
    assert RefreshTokenReuseError.keep_changes is True


async def test_other_sessions_of_the_same_user_survive_a_reuse(world: World) -> None:
    laptop = await world.login()
    phone = await world.login()
    await world.use(laptop)

    with pytest.raises(RefreshTokenReuseError):
        await world.use(laptop)

    assert (await world.use(phone)).user_id == world.user.id


# --- Invalid tokens ------------------------------------------------------------------------


async def test_unknown_token_is_rejected(world: World) -> None:
    with pytest.raises(InvalidTokenError):
        await world.refresh.execute(RefreshSessionCommand("not-a-real-token"))


async def test_expired_token_is_rejected(world: World) -> None:
    session = await world.login()
    world.clock.now = START + timedelta(days=14)

    with pytest.raises(InvalidTokenError):
        await world.use(session)


async def test_token_of_a_disabled_user_is_rejected_and_revoked(world: World) -> None:
    session = await world.login()
    world.user.is_active = False

    with pytest.raises(InvalidTokenError):
        await world.use(session)
    assert world.stored(session).revoked_at is not None


async def test_lookup_uses_the_hash_never_the_raw_token(world: World) -> None:
    session = await world.login()

    assert world.stored(session).token_hash == hash_token(session.refresh_token)
    assert all(t.token_hash != session.refresh_token for t in world.tokens.items.values())


# --- Logout --------------------------------------------------------------------------------


async def test_logout_revokes_the_session(world: World) -> None:
    session = await world.login()

    await world.logout.execute(LogoutCommand(session.refresh_token))

    with pytest.raises(InvalidTokenError):
        await world.use(session)
    assert world.audit.actions[-1] == "auth.logout"


async def test_logout_twice_or_with_unknown_token_is_not_an_error(world: World) -> None:
    session = await world.login()

    await world.logout.execute(LogoutCommand(session.refresh_token))
    await world.logout.execute(LogoutCommand(session.refresh_token))
    await world.logout.execute(LogoutCommand("unknown"))
