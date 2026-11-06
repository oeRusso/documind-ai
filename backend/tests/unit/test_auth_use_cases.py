"""Register and Login with in-memory fakes (no database, no Argon2)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.auth.application.issue_session import IssueSession
from app.modules.auth.application.login import Login, LoginCommand
from app.modules.auth.application.register import Register, RegisterCommand
from app.modules.auth.domain.errors import InvalidCredentialsError
from app.modules.auth.infrastructure.jwt_codec import JwtAccessTokenCodec
from app.modules.organizations.application.create_organization import CreateOrganization
from app.modules.organizations.domain.errors import OrganizationSlugTakenError
from app.modules.organizations.domain.roles import Role
from app.modules.users.application.create_user import CreateUser
from app.modules.users.application.verify_credentials import VerifyCredentials
from app.modules.users.domain.errors import EmailAlreadyRegisteredError, WeakPasswordError
from app.shared.secure_tokens import hash_token
from tests.fakes import (
    FakePasswordHasher,
    FakeTenantContext,
    InMemoryAuditLogRepository,
    InMemoryMembershipRepository,
    InMemoryOrganizationRepository,
    InMemoryRefreshTokenRepository,
    InMemoryUserRepository,
)

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
SECRET = "unit-test-secret-0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
PASSWORD = "una clave bien larga"  # pragma: allowlist secret
WRONG_PASSWORD = "otra clave larga"  # pragma: allowlist secret
SHORT_PASSWORD = "corta"  # pragma: allowlist secret


class World:
    """All the fakes wired like the real app wires the SQL implementations."""

    def __init__(self) -> None:
        self.tenant = FakeTenantContext()
        self.users = InMemoryUserRepository()
        self.hasher = FakePasswordHasher()
        self.organizations = InMemoryOrganizationRepository(self.tenant)
        self.memberships = InMemoryMembershipRepository(self.tenant)
        self.audit = InMemoryAuditLogRepository()
        self.refresh_tokens = InMemoryRefreshTokenRepository()
        self.codec = JwtAccessTokenCodec(SECRET, timedelta(minutes=15), clock=lambda: NOW)
        issue = IssueSession(self.refresh_tokens, self.codec, timedelta(days=14), clock=lambda: NOW)
        record = RecordAuditEvent(self.audit, clock=lambda: NOW)
        self.register = Register(
            CreateUser(self.users, self.hasher, clock=lambda: NOW),
            CreateOrganization(
                self.organizations, self.memberships, self.tenant, clock=lambda: NOW
            ),
            issue,
            record,
            self.tenant,
        )
        self.login = Login(VerifyCredentials(self.users, self.hasher), issue, record)


@pytest.fixture
def world() -> World:
    return World()


def register_command(email: str = "ana@example.com", slug: str = "acme") -> RegisterCommand:
    return RegisterCommand(
        email=email,
        password=PASSWORD,
        organization_name="Acme",
        organization_slug=slug,
        ip="203.0.113.7",
    )


# --- Register ------------------------------------------------------------------------------


async def test_register_creates_user_organization_owner_and_session(world: World) -> None:
    result = await world.register.execute(register_command(email=" Ana@Example.com "))

    assert result.user.email == "ana@example.com"
    membership = await world.memberships.get_by_user(result.organization.id, result.user.id)
    assert membership is not None and membership.role is Role.OWNER
    assert world.codec.read(result.session.access_token.value).user_id == result.user.id
    assert result.session.refresh_expires_at == NOW + timedelta(days=14)


async def test_register_stores_only_the_hash_of_the_refresh_token(world: World) -> None:
    result = await world.register.execute(register_command())

    [stored] = world.refresh_tokens.items.values()
    assert stored.token_hash == hash_token(result.session.refresh_token)
    assert stored.token_hash != result.session.refresh_token


async def test_register_is_audited_inside_the_new_organization(world: World) -> None:
    result = await world.register.execute(register_command())

    assert world.audit.actions == ["user.registered", "organization.created"]
    assert {e.organization_id for e in world.audit.events} == {result.organization.id}
    assert {e.ip for e in world.audit.events} == {"203.0.113.7"}


async def test_register_with_a_taken_email_fails(world: World) -> None:
    await world.register.execute(register_command(email="ana@example.com", slug="one"))

    with pytest.raises(EmailAlreadyRegisteredError):
        await world.register.execute(register_command(email="ANA@example.com", slug="two"))


async def test_register_with_a_taken_slug_fails(world: World) -> None:
    await world.register.execute(register_command(email="ana@example.com"))

    with pytest.raises(OrganizationSlugTakenError):
        await world.register.execute(register_command(email="bob@example.com"))


async def test_weak_password_is_rejected_before_hashing(world: World) -> None:
    command = RegisterCommand(
        email="ana@example.com",
        password=SHORT_PASSWORD,
        organization_name="A",
        organization_slug="aa",
    )

    with pytest.raises(WeakPasswordError):
        await world.register.execute(command)
    assert world.hasher.hash_calls == 0


# --- Login ---------------------------------------------------------------------------------


async def test_login_with_correct_password_issues_a_new_session(world: World) -> None:
    registered = await world.register.execute(register_command())

    session = await world.login.execute(LoginCommand(email="ANA@example.com", password=PASSWORD))

    assert session.user_id == registered.user.id
    assert session.refresh_token != registered.session.refresh_token
    families = {t.family_id for t in world.refresh_tokens.items.values()}
    assert len(families) == 2  # every login starts its own family
    assert world.audit.actions[-1] == "auth.login_succeeded"


async def test_login_with_wrong_password_fails_and_is_audited(world: World) -> None:
    await world.register.execute(register_command())

    with pytest.raises(InvalidCredentialsError):
        await world.login.execute(
            LoginCommand(email="ana@example.com", password=WRONG_PASSWORD, ip="198.51.100.1")
        )

    failed = world.audit.events[-1]
    assert failed.action == "auth.login_failed"
    assert failed.details == {"email": "ana@example.com"}
    assert failed.ip == "198.51.100.1"
    assert failed.organization_id is None


async def test_unknown_email_fails_the_same_way_and_still_verifies_a_hash(world: World) -> None:
    with pytest.raises(InvalidCredentialsError) as error:
        await world.login.execute(LoginCommand(email="nadie@example.com", password=PASSWORD))

    # Same message as a wrong password, and Argon2 still ran: no hint that the email is unknown.
    assert error.value.message == "Email o contraseña incorrectos"
    assert world.hasher.verify_calls == 1


async def test_disabled_user_cannot_log_in(world: World) -> None:
    registered = await world.register.execute(register_command())
    world.users.items[registered.user.id].is_active = False

    with pytest.raises(InvalidCredentialsError):
        await world.login.execute(LoginCommand(email="ana@example.com", password=PASSWORD))


def test_failed_login_keeps_its_audit_event() -> None:
    # Tells get_session to commit the audit event even though the request fails.
    assert InvalidCredentialsError.keep_changes is True
