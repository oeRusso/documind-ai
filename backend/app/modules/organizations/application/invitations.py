"""Use cases: invite someone by email, list and revoke invitations, accept one.

The link is the only place where the token exists: it is shown once to whoever invites
(and emailed, step 19). The database keeps only its SHA-256 hash.

The token goes after `#` in the link: browsers never send that part to the server, so the
token does not end up in access logs or in the Referer header.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode
from uuid import UUID

from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.organizations.domain.errors import (
    AlreadyMemberError,
    InvitationAlreadyPendingError,
    InvitationNotFoundError,
    PermissionDeniedError,
)
from app.modules.organizations.domain.invitation import Invitation, InvitationStatus
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.permissions import (
    Permission,
    can_invite_as,
    ensure_permission,
)
from app.modules.organizations.domain.repository import (
    InvitationRepository,
    MembershipRepository,
)
from app.modules.organizations.domain.roles import Role
from app.modules.users.application.find_user_by_email import FindUserByEmail
from app.modules.users.domain.entities import normalize_email
from app.shared.ids import new_id, utc_now
from app.shared.secure_tokens import generate_token, hash_token

ACCEPT_PATH = "/invitations/accept"


def invitation_link(app_origin: str, organization_id: UUID, token: str) -> str:
    fragment = urlencode({"organization": str(organization_id), "token": token})
    return f"{app_origin}{ACCEPT_PATH}#{fragment}"


@dataclass(frozen=True, slots=True)
class CreateInvitationCommand:
    actor: Membership
    email: str
    role: Role
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class CreatedInvitation:
    invitation: Invitation
    link: str  # contains the token: shown once, never stored


class CreateInvitation:
    def __init__(
        self,
        invitations: InvitationRepository,
        memberships: MembershipRepository,
        find_user: FindUserByEmail,
        record_audit_event: RecordAuditEvent,
        *,
        app_origin: str,
        id_factory: Callable[[], UUID] = new_id,
        clock: Callable[[], datetime] = utc_now,
        token_factory: Callable[[], str] = generate_token,
    ) -> None:
        self._invitations = invitations
        self._memberships = memberships
        self._find_user = find_user
        self._audit = record_audit_event
        self._app_origin = app_origin
        self._id_factory = id_factory
        self._clock = clock
        self._token_factory = token_factory

    async def execute(self, command: CreateInvitationCommand) -> CreatedInvitation:
        actor = command.actor
        ensure_permission(actor.role, Permission.INVITE_MEMBERS)
        if not can_invite_as(actor.role, command.role):  # an admin cannot invite admins
            raise PermissionDeniedError()
        email = normalize_email(command.email)
        now = self._clock()

        user = await self._find_user.execute(email)
        if user and await self._memberships.get_by_user(actor.organization_id, user.id):
            raise AlreadyMemberError()
        previous = await self._invitations.get_open_by_email(actor.organization_id, email)
        if previous is not None:
            if previous.status(now) is InvitationStatus.PENDING:
                raise InvitationAlreadyPendingError()
            previous.revoke(now)  # expired: make room for the new one
            await self._invitations.save_status(previous)

        token = self._token_factory()
        invitation = Invitation.create(
            id=self._id_factory(),
            organization_id=actor.organization_id,
            email=email,
            role=command.role,
            token_hash=hash_token(token),
            invited_by_id=actor.user_id,
            now=now,
        )
        await self._invitations.add(invitation)
        await self._audit.execute(
            RecordAuditEventCommand(
                action=AuditAction.INVITATION_CREATED,
                organization_id=actor.organization_id,
                user_id=actor.user_id,
                target=f"invitation:{invitation.id}",
                ip=command.ip,
                details={"email": email, "role": str(command.role)},
            )
        )
        link = invitation_link(self._app_origin, actor.organization_id, token)
        return CreatedInvitation(invitation=invitation, link=link)


class ListInvitations:
    def __init__(self, invitations: InvitationRepository) -> None:
        self._invitations = invitations

    async def execute(self, actor: Membership) -> list[Invitation]:
        ensure_permission(actor.role, Permission.INVITE_MEMBERS)
        return await self._invitations.list_open(actor.organization_id)


@dataclass(frozen=True, slots=True)
class RevokeInvitationCommand:
    actor: Membership
    invitation_id: UUID
    ip: str | None = None


class RevokeInvitation:
    def __init__(
        self,
        invitations: InvitationRepository,
        record_audit_event: RecordAuditEvent,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._invitations = invitations
        self._audit = record_audit_event
        self._clock = clock

    async def execute(self, command: RevokeInvitationCommand) -> None:
        actor = command.actor
        ensure_permission(actor.role, Permission.INVITE_MEMBERS)
        now = self._clock()
        invitation = await self._invitations.get_by_id(actor.organization_id, command.invitation_id)
        if invitation is None or invitation.status(now) in {
            InvitationStatus.ACCEPTED,
            InvitationStatus.REVOKED,
        }:
            raise InvitationNotFoundError()
        if not can_invite_as(actor.role, invitation.role):
            raise PermissionDeniedError()

        invitation.revoke(now)
        await self._invitations.save_status(invitation)
        await self._audit.execute(
            RecordAuditEventCommand(
                action=AuditAction.INVITATION_REVOKED,
                organization_id=actor.organization_id,
                user_id=actor.user_id,
                target=f"invitation:{invitation.id}",
                ip=command.ip,
                details={"email": invitation.email},
            )
        )
