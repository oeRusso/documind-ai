"""Use case: sign up. Creates the user, their first organization (as owner) and a session."""

from dataclasses import dataclass

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
from app.modules.organizations.domain.entities import Organization
from app.modules.users.application.create_user import CreateUser, CreateUserCommand
from app.modules.users.domain.entities import User
from app.shared.tenancy import TenantContext


@dataclass(frozen=True, slots=True)
class RegisterCommand:
    email: str
    password: str
    organization_name: str
    organization_slug: str
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
    ) -> None:
        self._create_user = create_user
        self._create_organization = create_organization
        self._issue_session = issue_session
        self._audit = record_audit_event
        self._tenant = tenant

    async def execute(self, command: RegisterCommand) -> RegisterResult:
        # Everything runs in one transaction: if any step fails, nothing is kept.
        user = await self._create_user.execute(
            CreateUserCommand(email=command.email, password=command.password)
        )
        await self._tenant.set_user(user.id)
        organization = await self._create_organization.execute(
            CreateOrganizationCommand(
                name=command.organization_name,
                slug=command.organization_slug,
                owner_id=user.id,
            )
        )
        for action, target in (
            (AuditAction.USER_REGISTERED, f"user:{user.id}"),
            (AuditAction.ORGANIZATION_CREATED, f"organization:{organization.id}"),
        ):
            await self._audit.execute(
                RecordAuditEventCommand(
                    action=action,
                    organization_id=organization.id,
                    user_id=user.id,
                    target=target,
                    ip=command.ip,
                )
            )
        session = await self._issue_session.start(user.id)
        return RegisterResult(user=user, organization=organization, session=session)
