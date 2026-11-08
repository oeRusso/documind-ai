"""Invitations with in-memory fakes: who can invite whom, duplicates, expiry, revocation."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest

from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.organizations.application.invitations import (
    CreatedInvitation,
    CreateInvitation,
    CreateInvitationCommand,
    ListInvitations,
    RevokeInvitation,
    RevokeInvitationCommand,
)
from app.modules.organizations.domain.errors import (
    AlreadyMemberError,
    InvitationAlreadyPendingError,
    InvitationNotFoundError,
    PermissionDeniedError,
)
from app.modules.organizations.domain.invitation import InvitationStatus
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from app.modules.users.application.find_user_by_email import FindUserByEmail
from app.modules.users.domain.entities import User
from app.modules.users.domain.errors import InvalidEmailError
from app.shared.ids import new_id
from app.shared.secure_tokens import hash_token
from tests.fakes import (
    FakeTenantContext,
    InMemoryAuditLogRepository,
    InMemoryInvitationRepository,
    InMemoryMembershipRepository,
    InMemoryUserRepository,
)

START = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
ORIGIN = "https://documind.example"


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class World:
    def __init__(self) -> None:
        self.clock = Clock()
        self.organization_id = new_id()
        self.tenant = FakeTenantContext()
        self.tenant.organization_id = self.organization_id  # what CurrentMemberDep does
        self.invitations = InMemoryInvitationRepository(self.tenant)
        self.memberships = InMemoryMembershipRepository(self.tenant)
        self.users = InMemoryUserRepository()
        self.audit = InMemoryAuditLogRepository()
        record = RecordAuditEvent(self.audit, clock=self.clock)
        self.create = CreateInvitation(
            self.invitations,
            self.memberships,
            FindUserByEmail(self.users),
            record,
            app_origin=ORIGIN,
            clock=self.clock,
        )
        self.list = ListInvitations(self.invitations)
        self.revoke = RevokeInvitation(self.invitations, record, clock=self.clock)
        self.owner = self.join(Role.OWNER, "owner@example.com")
        self.admin = self.join(Role.ADMIN, "admin@example.com")
        self.member = self.join(Role.MEMBER, "member@example.com")
        self.viewer = self.join(Role.VIEWER, "viewer@example.com")

    def join(self, role: Role, email: str) -> Membership:
        user = User.create(id=new_id(), email=email, password_hash="h", now=START)
        self.users.items[user.id] = user
        membership = Membership.create(
            id=new_id(), organization_id=self.organization_id, user_id=user.id, role=role, now=START
        )
        self.memberships.items.append(membership)
        return membership

    async def invite(
        self,
        email: str = "nueva@example.com",
        role: Role = Role.MEMBER,
        actor: Membership | None = None,
    ) -> CreatedInvitation:
        return await self.create.execute(CreateInvitationCommand(actor or self.owner, email, role))


@pytest.fixture
def world() -> World:
    return World()


def token_in(link: str) -> str:
    return parse_qs(urlsplit(link).fragment)["token"][0]


# --- Creating -------------------------------------------------------------------------------


async def test_invitation_is_pending_for_seven_days(world: World) -> None:
    created = await world.invite(" Nueva@Example.com ")

    invitation = created.invitation
    assert invitation.email == "nueva@example.com"
    assert invitation.role is Role.MEMBER
    assert invitation.invited_by_id == world.owner.user_id
    assert invitation.expires_at == START + timedelta(days=7)
    assert invitation.status(START) is InvitationStatus.PENDING


async def test_the_link_carries_organization_and_token_after_the_hash(world: World) -> None:
    created = await world.invite()

    link = urlsplit(created.link)
    assert f"{link.scheme}://{link.netloc}{link.path}" == f"{ORIGIN}/invitations/accept"
    assert link.query == ""  # nothing the server would log
    params = parse_qs(link.fragment)
    assert params["organization"] == [str(world.organization_id)]
    # Only the hash is stored.
    assert created.invitation.token_hash == hash_token(token_in(created.link))
    assert token_in(created.link) not in created.invitation.token_hash


@pytest.mark.parametrize(
    ("actor_name", "role", "allowed"),
    [
        ("owner", Role.ADMIN, True),
        ("owner", Role.VIEWER, True),
        ("admin", Role.MEMBER, True),
        ("admin", Role.VIEWER, True),
        ("admin", Role.ADMIN, False),  # an admin cannot create admins
        ("owner", Role.OWNER, False),  # nobody is invited as owner
        ("member", Role.VIEWER, False),
        ("viewer", Role.VIEWER, False),  # stage 2 criterion 3
    ],
)
async def test_who_can_invite_whom(
    world: World, actor_name: str, role: Role, allowed: bool
) -> None:
    actor = getattr(world, actor_name)

    if allowed:
        await world.invite(role=role, actor=actor)
        assert len(world.invitations.items) == 1
    else:
        with pytest.raises(PermissionDeniedError):
            await world.invite(role=role, actor=actor)
        assert world.invitations.items == []


async def test_inviting_a_member_again_is_a_conflict(world: World) -> None:
    with pytest.raises(AlreadyMemberError):
        await world.invite("MEMBER@example.com")


async def test_an_invalid_email_is_rejected(world: World) -> None:
    with pytest.raises(InvalidEmailError):
        await world.invite("no-es-un-email")


async def test_only_one_pending_invitation_per_email(world: World) -> None:
    await world.invite()

    with pytest.raises(InvitationAlreadyPendingError):
        await world.invite(role=Role.VIEWER)


async def test_an_expired_invitation_is_replaced_by_a_new_one(world: World) -> None:
    old = (await world.invite()).invitation
    world.clock.now = START + timedelta(days=8)

    new = (await world.invite()).invitation

    assert old.status(world.clock.now) is InvitationStatus.REVOKED
    assert new.status(world.clock.now) is InvitationStatus.PENDING


async def test_creation_is_audited_without_the_token(world: World) -> None:
    created = await world.invite()

    [event] = world.audit.events
    assert event.action == "invitation.created"
    assert event.organization_id == world.organization_id
    assert event.details == {"email": "nueva@example.com", "role": "member"}
    assert token_in(created.link) not in str(event)


# --- Listing and revoking -------------------------------------------------------------------


async def test_list_shows_open_invitations_only(world: World) -> None:
    kept = (await world.invite("a@example.com")).invitation
    gone = (await world.invite("b@example.com")).invitation
    await world.revoke.execute(RevokeInvitationCommand(world.owner, gone.id))

    assert await world.list.execute(world.admin) == [kept]


@pytest.mark.parametrize("actor_name", ["member", "viewer"])
async def test_members_and_viewers_cannot_see_or_revoke_invitations(
    world: World, actor_name: str
) -> None:
    invitation = (await world.invite()).invitation
    actor = getattr(world, actor_name)

    with pytest.raises(PermissionDeniedError):
        await world.list.execute(actor)
    with pytest.raises(PermissionDeniedError):
        await world.revoke.execute(RevokeInvitationCommand(actor, invitation.id))


async def test_admin_cannot_revoke_an_admin_invitation(world: World) -> None:
    invitation = (await world.invite(role=Role.ADMIN)).invitation

    with pytest.raises(PermissionDeniedError):
        await world.revoke.execute(RevokeInvitationCommand(world.admin, invitation.id))


async def test_revoking_twice_or_an_unknown_id_is_not_found(world: World) -> None:
    invitation = (await world.invite()).invitation
    await world.revoke.execute(RevokeInvitationCommand(world.owner, invitation.id))

    with pytest.raises(InvitationNotFoundError):
        await world.revoke.execute(RevokeInvitationCommand(world.owner, invitation.id))
    with pytest.raises(InvitationNotFoundError):
        await world.revoke.execute(RevokeInvitationCommand(world.owner, UUID(int=1)))
    assert world.audit.actions == ["invitation.created", "invitation.revoked"]
