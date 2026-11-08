"""Member management rules, with in-memory fakes. Stage 2 criterion 3: a viewer gets 403 when
trying admin actions (here: PermissionDeniedError, which the API turns into 403)."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.organizations.application.manage_members import (
    ChangeMemberRole,
    ChangeMemberRoleCommand,
    ListMembers,
    RemoveMember,
    RemoveMemberCommand,
)
from app.modules.organizations.domain.errors import (
    LastOwnerError,
    MembershipNotFoundError,
    PermissionDeniedError,
)
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from app.modules.users.application.get_users_by_ids import GetUsersByIds
from app.modules.users.domain.entities import User
from app.shared.ids import new_id
from tests.fakes import (
    FakeTenantContext,
    InMemoryAuditLogRepository,
    InMemoryMembershipRepository,
    InMemoryUserRepository,
)

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 8, 13, 0, tzinfo=UTC)


class Org:
    """One organization with one member per role, plus a second organization."""

    def __init__(self) -> None:
        self.organization_id = new_id()
        self.other_organization_id = new_id()
        self.tenant = FakeTenantContext()
        self.memberships = InMemoryMembershipRepository(self.tenant)
        self.users = InMemoryUserRepository()
        self.audit = InMemoryAuditLogRepository()
        record = RecordAuditEvent(self.audit, clock=lambda: LATER)
        get_users = GetUsersByIds(self.users)
        self.list = ListMembers(self.memberships, get_users)
        self.change = ChangeMemberRole(self.memberships, record, get_users, clock=lambda: LATER)
        self.remove = RemoveMember(self.memberships, record, clock=lambda: LATER)

        self.owner = self.join(Role.OWNER, "owner@example.com")
        self.admin = self.join(Role.ADMIN, "admin@example.com")
        self.member = self.join(Role.MEMBER, "member@example.com")
        self.viewer = self.join(Role.VIEWER, "viewer@example.com")
        self.stranger = self.join(Role.MEMBER, "x@example.com", self.other_organization_id)

    def join(self, role: Role, email: str, organization_id: UUID | None = None) -> Membership:
        user = User.create(id=new_id(), email=email, password_hash="h", now=NOW)
        self.users.items[user.id] = user
        membership = Membership.create(
            id=new_id(),
            organization_id=organization_id or self.organization_id,
            user_id=user.id,
            role=role,
            now=NOW,
        )
        self.memberships.items.append(membership)
        return membership

    async def set_role(self, actor: Membership, target: Membership, role: Role) -> Membership:
        result = await self.change.execute(ChangeMemberRoleCommand(actor, target.id, role))
        return result.membership

    async def kick(self, actor: Membership, target: Membership) -> None:
        await self.remove.execute(RemoveMemberCommand(actor, target.id))

    def role_of(self, target: Membership) -> Role | None:
        found = [m for m in self.memberships.items if m.id == target.id]
        return found[0].role if found else None


@pytest.fixture
def org() -> Org:
    return Org()


# --- Listing --------------------------------------------------------------------------------


@pytest.mark.parametrize("role", list(Role))
async def test_every_role_can_list_the_members_of_its_organization(org: Org, role: Role) -> None:
    actor = next(m for m in org.memberships.items if m.role is role)

    members = await org.list.execute(actor)

    assert [(m.email, m.membership.role) for m in members] == [
        ("owner@example.com", Role.OWNER),
        ("admin@example.com", Role.ADMIN),
        ("member@example.com", Role.MEMBER),
        ("viewer@example.com", Role.VIEWER),
    ]  # and nobody from the other organization


# --- Criterion 3: no admin actions without the role ------------------------------------------


@pytest.mark.parametrize("actor_role", [Role.VIEWER, Role.MEMBER])
async def test_viewers_and_members_cannot_change_roles_or_remove(
    org: Org, actor_role: Role
) -> None:
    actor = org.viewer if actor_role is Role.VIEWER else org.member
    target = org.member if actor_role is Role.VIEWER else org.viewer

    with pytest.raises(PermissionDeniedError):
        await org.set_role(actor, target, Role.VIEWER)
    with pytest.raises(PermissionDeniedError):
        await org.kick(actor, target)
    assert org.role_of(target) is target.role
    assert org.audit.events == []


async def test_a_viewer_gets_403_before_learning_whether_the_id_exists(org: Org) -> None:
    unknown = Membership.create(
        id=new_id(),
        organization_id=org.organization_id,
        user_id=new_id(),
        role=Role.VIEWER,
        now=NOW,
    )

    with pytest.raises(PermissionDeniedError):
        await org.set_role(org.viewer, unknown, Role.MEMBER)


# --- Rank rules -----------------------------------------------------------------------------


async def test_admin_can_change_roles_below_admin(org: Org) -> None:
    updated = await org.set_role(org.admin, org.member, Role.VIEWER)

    assert updated.role is Role.VIEWER
    assert updated.updated_at == LATER
    assert org.role_of(org.member) is Role.VIEWER


@pytest.mark.parametrize(
    ("target_name", "new_role"),
    [
        ("member", Role.ADMIN),  # cannot grant their own rank
        ("member", Role.OWNER),  # nor above it
        ("owner", Role.MEMBER),  # cannot touch an owner
    ],
)
async def test_admin_cannot_grant_or_manage_at_or_above_their_rank(
    org: Org, target_name: str, new_role: Role
) -> None:
    target = getattr(org, target_name)

    with pytest.raises(PermissionDeniedError):
        await org.set_role(org.admin, target, new_role)


async def test_admin_cannot_remove_an_owner_nor_change_their_own_role(org: Org) -> None:
    with pytest.raises(PermissionDeniedError):
        await org.kick(org.admin, org.owner)
    with pytest.raises(PermissionDeniedError):
        await org.set_role(org.admin, org.admin, Role.VIEWER)


async def test_owner_can_make_someone_else_owner(org: Org) -> None:
    await org.set_role(org.owner, org.admin, Role.OWNER)

    assert org.role_of(org.admin) is Role.OWNER


# --- The last owner -------------------------------------------------------------------------


async def test_the_last_owner_cannot_be_demoted_or_removed(org: Org) -> None:
    with pytest.raises(LastOwnerError):
        await org.set_role(org.owner, org.owner, Role.ADMIN)
    with pytest.raises(LastOwnerError):
        await org.kick(org.owner, org.owner)
    assert org.role_of(org.owner) is Role.OWNER


async def test_with_two_owners_one_can_step_down(org: Org) -> None:
    await org.set_role(org.owner, org.admin, Role.OWNER)

    await org.set_role(org.owner, org.owner, Role.ADMIN)

    assert org.role_of(org.owner) is Role.ADMIN


# --- Other organizations and edge cases -----------------------------------------------------


async def test_a_membership_of_another_organization_is_not_found(org: Org) -> None:
    with pytest.raises(MembershipNotFoundError):
        await org.set_role(org.owner, org.stranger, Role.VIEWER)
    with pytest.raises(MembershipNotFoundError):
        await org.kick(org.owner, org.stranger)
    assert org.role_of(org.stranger) is Role.MEMBER


async def test_setting_the_same_role_changes_nothing(org: Org) -> None:
    await org.set_role(org.owner, org.member, Role.MEMBER)

    assert org.audit.events == []


# --- Audit ----------------------------------------------------------------------------------


async def test_role_change_is_audited(org: Org) -> None:
    await org.set_role(org.owner, org.member, Role.ADMIN)

    [event] = org.audit.events
    assert event.action == "membership.role_changed"
    assert event.organization_id == org.organization_id
    assert event.user_id == org.owner.user_id
    assert event.target == f"membership:{org.member.id}"
    assert event.details == {
        "member_user_id": str(org.member.user_id),
        "from_role": "member",
        "to_role": "admin",
    }


async def test_removal_is_audited_and_the_member_is_gone(org: Org) -> None:
    await org.kick(org.admin, org.viewer)

    assert org.role_of(org.viewer) is None
    [event] = org.audit.events
    assert event.action == "membership.removed"
    assert event.details == {"member_user_id": str(org.viewer.user_id), "role": "viewer"}
