"""Wiring for auth, plus the two dependencies every protected endpoint uses:

- CurrentUserDep: who is calling (from the Bearer access token).
- CurrentMemberDep: who is calling *and* their membership in the organization of the
  X-Organization-Id header. Sets the tenant context, so RLS applies from then on (ADR 0003).
"""

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings
from app.core.dependencies import SessionDep, SettingsDep
from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
from app.modules.auth.application.issue_session import IssueSession
from app.modules.auth.application.login import Login
from app.modules.auth.application.logout import Logout
from app.modules.auth.application.refresh_session import RefreshSession
from app.modules.auth.application.register import Register
from app.modules.auth.domain.errors import InvalidTokenError
from app.modules.auth.infrastructure.jwt_codec import JwtAccessTokenCodec
from app.modules.auth.infrastructure.sql_repository import SqlRefreshTokenRepository
from app.modules.organizations.application.create_organization import CreateOrganization
from app.modules.organizations.application.resolve_membership import ResolveMembership
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.infrastructure.sql_repository import (
    SqlMembershipRepository,
    SqlOrganizationRepository,
)
from app.modules.users.application.create_user import CreateUser
from app.modules.users.application.get_user import GetActiveUser
from app.modules.users.application.verify_credentials import VerifyCredentials
from app.modules.users.domain.entities import User
from app.modules.users.infrastructure.argon2_hasher import Argon2PasswordHasher
from app.modules.users.infrastructure.sql_repository import SqlUserRepository
from app.shared.errors import UnauthorizedError

ORGANIZATION_HEADER = "X-Organization-Id"


def access_token_codec(settings: Settings) -> JwtAccessTokenCodec:
    return JwtAccessTokenCodec(
        settings.jwt_secret.get_secret_value(),
        timedelta(minutes=settings.access_token_minutes),
    )


# --- Use cases (one instance per request, sharing the request's session) -------------------


def _issue_session(session: SessionDep, settings: SettingsDep) -> IssueSession:
    return IssueSession(
        SqlRefreshTokenRepository(session),
        access_token_codec(settings),
        timedelta(days=settings.refresh_token_days),
    )


def _audit(session: SessionDep) -> RecordAuditEvent:
    return RecordAuditEvent(SqlAuditLogRepository(session))


def provide_register(session: SessionDep, settings: SettingsDep) -> Register:
    tenant = SqlTenantContext(session)
    return Register(
        CreateUser(SqlUserRepository(session), Argon2PasswordHasher()),
        CreateOrganization(
            SqlOrganizationRepository(session), SqlMembershipRepository(session), tenant
        ),
        _issue_session(session, settings),
        _audit(session),
        tenant,
    )


def provide_login(session: SessionDep, settings: SettingsDep) -> Login:
    return Login(
        VerifyCredentials(SqlUserRepository(session), Argon2PasswordHasher()),
        _issue_session(session, settings),
        _audit(session),
    )


def provide_refresh_session(session: SessionDep, settings: SettingsDep) -> RefreshSession:
    return RefreshSession(
        SqlRefreshTokenRepository(session),
        _issue_session(session, settings),
        GetActiveUser(SqlUserRepository(session)),
        _audit(session),
    )


def provide_logout(session: SessionDep) -> Logout:
    return Logout(SqlRefreshTokenRepository(session), _audit(session))


# --- Who is calling ------------------------------------------------------------------------

# auto_error=False: a missing header becomes our own 401 with the uniform error format.
_bearer = HTTPBearer(auto_error=False, description="Access token de `/auth/login`")


class NotAuthenticatedError(UnauthorizedError):
    code = "not_authenticated"
    message = "Tenés que iniciar sesión"


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    if credentials is None:
        raise NotAuthenticatedError()
    claims = access_token_codec(settings).read(credentials.credentials)
    user = await GetActiveUser(SqlUserRepository(session)).execute(claims.user_id)
    if user is None:  # deleted or disabled after the token was issued
        raise InvalidTokenError()
    await SqlTenantContext(session).set_user(user.id)
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_current_member(
    user: CurrentUserDep,
    session: SessionDep,
    organization_id: Annotated[
        UUID, Header(alias=ORGANIZATION_HEADER, description="Organización activa")
    ],
) -> Membership:
    # Layer 1 of the isolation: the backend checks the membership (404 if there is none)...
    membership = await ResolveMembership(SqlMembershipRepository(session)).execute(
        organization_id, user.id
    )
    # ...and layer 2: from here on PostgreSQL only shows this organization's rows.
    await SqlTenantContext(session).set_organization(organization_id)
    return membership


CurrentMemberDep = Annotated[Membership, Depends(get_current_member)]
