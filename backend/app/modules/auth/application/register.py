"""Use case: sign up. Creates the user and a session, plus either:

- a new organization, with the user as owner (the usual sign-up), or
- a membership in the organization of an invitation (someone invited them and they have no
  account yet). The invitation's email must match: the link proves access to that inbox.
"""

from dataclasses import dataclass
from uuid import UUID

from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.auth.application.issue_session import IssuedSession, IssueSession
from app.modules.organizations.application.create_organization import (
    CreateOrganization,
    CreateOrganizationCommand,
)
from app.modules.organizations.application.invitations import (
    AcceptInvitation,
    AcceptInvitationCommand,
)
from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.errors import InvalidOrganizationError
from app.modules.users.application.create_user import CreateUser, CreateUserCommand
from app.modules.users.domain.entities import User
from app.shared.tenancy import TenantContext


@dataclass(frozen=True, slots=True)
class InvitationToken:
    organization_id: UUID
    token: str


@dataclass(frozen=True, slots=True)
class RegisterCommand:
    email: str
    password: str
    # Exactly one of: a new organization (name and slug), or an invitation.
    organization_name: str | None = None
    organization_slug: str | None = None
    invitation: InvitationToken | None = None
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class RegisterResult:
    user: User
    organization: Organization
    session: IssuedSession


class Register:
    def __init__(
        self,
        create_user: CreateUser,
        create_organization: CreateOrganization,
        issue_session: IssueSession,
        record_audit_event: RecordAuditEvent,
        tenant: TenantContext,
        accept_invitation: AcceptInvitation,
    ) -> None:
        self._create_user = create_user
        self._create_organization = create_organization
        self._issue_session = issue_session
        self._audit = record_audit_event
        self._tenant = tenant
        self._accept_invitation = accept_invitation

    async def execute(self, command: RegisterCommand) -> RegisterResult:
        # Everything runs in one transaction: if any step fails, nothing is kept.
        user = await self._create_user.execute(
            CreateUserCommand(email=command.email, password=command.password)
        )
        await self._tenant.set_user(user.id)
        organization = await self._join_or_create_organization(command, user)
        await self._audit.execute(
            RecordAuditEventCommand(
                action=AuditAction.USER_REGISTERED,
                organization_id=organization.id,
                user_id=user.id,
                target=f"user:{user.id}",
                ip=command.ip,
            )
        )
        session = await self._issue_session.start(user.id)
        return RegisterResult(user=user, organization=organization, session=session)

    async def _join_or_create_organization(
        self, command: RegisterCommand, user: User
    ) -> Organization:
        if command.invitation is not None:
            joined = await self._accept_invitation.execute(
                AcceptInvitationCommand(
                    user_id=user.id,
                    user_email=user.email,
                    organization_id=command.invitation.organization_id,
                    token=command.invitation.token,
                    ip=command.ip,
                )
            )
            return joined.organization
        if command.organization_name is None or command.organization_slug is None:
            raise InvalidOrganizationError("Falta la organización o la invitación")
        return await self._create_organization.execute(
            CreateOrganizationCommand(
                name=command.organization_name,
                slug=command.organization_slug,
                owner_id=user.id,
                ip=command.ip,
            )
        )
