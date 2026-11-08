"""Register and Login end to end below HTTP: real SQL repositories, real Argon2id, RLS on."""

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
from app.modules.auth.application.issue_session import IssueSession
from app.modules.auth.application.login import Login, LoginCommand
from app.modules.auth.application.register import Register, RegisterCommand
from app.modules.auth.domain.errors import InvalidCredentialsError
from app.modules.auth.infrastructure.jwt_codec import JwtAccessTokenCodec
from app.modules.auth.infrastructure.sql_repository import SqlRefreshTokenRepository
from app.modules.organizations.application.create_organization import CreateOrganization
from app.modules.organizations.application.invitations import AcceptInvitation
from app.modules.organizations.domain.roles import Role
from app.modules.organizations.infrastructure.sql_repository import (
    SqlInvitationRepository,
    SqlMembershipRepository,
    SqlOrganizationRepository,
)
from app.modules.users.application.create_user import CreateUser
from app.modules.users.application.verify_credentials import VerifyCredentials
from app.modules.users.infrastructure.argon2_hasher import Argon2PasswordHasher
from app.modules.users.infrastructure.sql_repository import SqlUserRepository
from tests.conftest import TEST_JWT_SECRET

PASSWORD = "una clave bien larga"  # pragma: allowlist secret
WRONG_PASSWORD = "no es la clave"  # pragma: allowlist secret


def wire(session: AsyncSession) -> tuple[Register, Login]:
    tenant = SqlTenantContext(session)
    users = SqlUserRepository(session)
    hasher = Argon2PasswordHasher()
    issue = IssueSession(
        SqlRefreshTokenRepository(session),
        JwtAccessTokenCodec(TEST_JWT_SECRET, timedelta(minutes=15)),
        timedelta(days=14),
    )
    audit = RecordAuditEvent(SqlAuditLogRepository(session))
    register = Register(
        CreateUser(users, hasher),
        CreateOrganization(
            SqlOrganizationRepository(session), SqlMembershipRepository(session), tenant, audit
        ),
        issue,
        audit,
        tenant,
        AcceptInvitation(
            SqlInvitationRepository(session),
            SqlMembershipRepository(session),
            SqlOrganizationRepository(session),
            tenant,
            audit,
        ),
    )
    return register, Login(VerifyCredentials(users, hasher), issue, audit)


async def test_register_then_login(app_session: AsyncSession) -> None:
    register, login = wire(app_session)

    registered = await register.execute(
        RegisterCommand(
            email="ana@example.com",
            password=PASSWORD,
            organization_name="Acme",
            organization_slug="acme",
            ip="203.0.113.7",
        )
    )
    session = await login.execute(LoginCommand(email="ana@example.com", password=PASSWORD))

    assert session.user_id == registered.user.id
    assert registered.user.password_hash.startswith("$argon2id$")
    membership = await SqlMembershipRepository(app_session).get_by_user(
        registered.organization.id, registered.user.id
    )
    assert membership is not None and membership.role is Role.OWNER


async def test_wrong_password_is_rejected(app_session: AsyncSession) -> None:
    register, login = wire(app_session)
    await register.execute(
        RegisterCommand(
            email="ana@example.com",
            password=PASSWORD,
            organization_name="Acme",
            organization_slug="acme",
        )
    )

    with pytest.raises(InvalidCredentialsError):
        await login.execute(LoginCommand(email="ana@example.com", password=WRONG_PASSWORD))
