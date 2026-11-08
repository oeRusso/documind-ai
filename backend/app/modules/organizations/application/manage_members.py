"""Use cases: list the members of the active organization, change a role, remove someone.

Every use case receives the caller's `Membership` (resolved by CurrentMemberDep, so the caller
does belong to the organization) and checks, in this order:
1. The role allows the action at all -> 403 (a viewer trying admin actions: stage 2 criterion 3).
2. The target exists *in this organization* -> 404 otherwise, also for another organization's id.
3. Rank rules: nobody manages someone of their own rank or above, except owners -> 403.
4. The organization keeps at least one owner -> 409.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.organizations.domain.errors import MembershipNotFoundError, PermissionDeniedError
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.permissions import (
    Permission,
    can_grant,
    can_manage,
    ensure_an_owner_remains,
    ensure_permission,
)
from app.modules.organizations.domain.repository import MembershipRepository
from app.modules.organizations.domain.roles import Role
from app.modules.users.application.get_users_by_ids import GetUsersByIds
from app.shared.ids import utc_now


@dataclass(frozen=True, slots=True)
class MemberView:
    membership: Membership
    email: str


class ListMembers:
    def __init__(self, memberships: MembershipRepository, get_users: GetUsersByIds) -> None:
        self._memberships = memberships
        self._get_users = get_users

    async def execute(self, actor: Membership) -> list[MemberView]:
        ensure_permission(actor.role, Permission.VIEW_MEMBERS)
        members = await self._memberships.list_for_organization(actor.organization_id)
        users = await self._get_users.execute([m.user_id for m in members])
        return [MemberView(m, users[m.user_id].email) for m in members if m.user_id in users]


@dataclass(frozen=True, slots=True)
class ChangeMemberRoleCommand:
    actor: Membership
    membership_id: UUID
    role: Role
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class RemoveMemberCommand:
    actor: Membership
    membership_id: UUID
    ip: str | None = None


class _MemberManagement:
    def __init__(
        self,
        memberships: MembershipRepository,
        record_audit_event: RecordAuditEvent,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._memberships = memberships
        self._audit = record_audit_event
        self._clock = clock

    async def _find_target(self, actor: Membership, membership_id: UUID) -> tuple[Membership, int]:
        """The target membership and the number of owners (their rows locked from here on)."""
        ensure_permission(actor.role, Permission.MANAGE_MEMBERS)
        # Lock first, read after: the target is read with the owners' rows already locked,
        # so its role cannot change under us (see count_owners_for_update).
        owner_count = await self._memberships.count_owners_for_update(actor.organization_id)
        target = await self._memberships.get_by_id(actor.organization_id, membership_id)
        if target is None:
            raise MembershipNotFoundError()
        if not can_manage(actor.role, target.role):
            raise PermissionDeniedError()
        return target, owner_count

    async def _record(
        self,
        action: AuditAction,
        actor: Membership,
        target: Membership,
        ip: str | None,
        **details: str,
    ) -> None:
        await self._audit.execute(
            RecordAuditEventCommand(
                action=action,
                organization_id=actor.organization_id,
                user_id=actor.user_id,
                target=f"membership:{target.id}",
                ip=ip,
                details={"member_user_id": str(target.user_id), **details},
            )
        )


class ChangeMemberRole(_MemberManagement):
    def __init__(
        self,
        memberships: MembershipRepository,
        record_audit_event: RecordAuditEvent,
        get_users: GetUsersByIds,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(memberships, record_audit_event, clock=clock)
        self._get_users = get_users

    async def execute(self, command: ChangeMemberRoleCommand) -> MemberView:
        target = await self._change(command)
        users = await self._get_users.execute([target.user_id])
        return MemberView(target, users[target.user_id].email)

    async def _change(self, command: ChangeMemberRoleCommand) -> Membership:
        actor = command.actor
        target, owner_count = await self._find_target(actor, command.membership_id)
        if not can_grant(actor.role, command.role):
            raise PermissionDeniedError()
        if target.role is command.role:
            return target  # nothing to change, nothing to audit
        ensure_an_owner_remains(owner_count=owner_count, target=target.role, new_role=command.role)

        previous = target.role
        now = self._clock()
        await self._memberships.update_role(actor.organization_id, target.id, command.role, now)
        target.role = command.role
        target.updated_at = now
        await self._record(
            AuditAction.MEMBER_ROLE_CHANGED,
            actor,
            target,
            command.ip,
            from_role=str(previous),
            to_role=str(command.role),
        )
        return target


class RemoveMember(_MemberManagement):
    async def execute(self, command: RemoveMemberCommand) -> None:
        actor = command.actor
        target, owner_count = await self._find_target(actor, command.membership_id)
        ensure_an_owner_remains(owner_count=owner_count, target=target.role, new_role=None)

        await self._memberships.remove(actor.organization_id, target.id)
        await self._record(
            AuditAction.MEMBER_REMOVED, actor, target, command.ip, role=str(target.role)
        )
