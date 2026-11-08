"""Wiring: which concrete implementation each organizations use case receives."""

from app.core.dependencies import SessionDep, SettingsDep
from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
from app.modules.organizations.application.create_organization import CreateOrganization
from app.modules.organizations.application.get_organization import (
    GetOrganization,
    ListMyOrganizations,
)
from app.modules.organizations.application.invitations import (
    CreateInvitation,
    ListInvitations,
    RevokeInvitation,
)
from app.modules.organizations.application.manage_members import (
    ChangeMemberRole,
    ListMembers,
    RemoveMember,
)
from app.modules.organizations.infrastructure.sql_repository import (
    SqlInvitationRepository,
    SqlMembershipRepository,
    SqlOrganizationRepository,
)
from app.modules.users.application.find_user_by_email import FindUserByEmail
from app.modules.users.application.get_users_by_ids import GetUsersByIds
from app.modules.users.infrastructure.sql_repository import SqlUserRepository


def provide_create_organization(session: SessionDep) -> CreateOrganization:
    return CreateOrganization(
        SqlOrganizationRepository(session),
        SqlMembershipRepository(session),
        SqlTenantContext(session),
        RecordAuditEvent(SqlAuditLogRepository(session)),
    )


def provide_get_organization(session: SessionDep) -> GetOrganization:
    return GetOrganization(SqlOrganizationRepository(session), SqlMembershipRepository(session))


def provide_list_my_organizations(session: SessionDep) -> ListMyOrganizations:
    return ListMyOrganizations(SqlOrganizationRepository(session), SqlMembershipRepository(session))


def provide_list_members(session: SessionDep) -> ListMembers:
    return ListMembers(SqlMembershipRepository(session), GetUsersByIds(SqlUserRepository(session)))


def provide_change_member_role(session: SessionDep) -> ChangeMemberRole:
    return ChangeMemberRole(
        SqlMembershipRepository(session),
        RecordAuditEvent(SqlAuditLogRepository(session)),
        GetUsersByIds(SqlUserRepository(session)),
    )


def provide_remove_member(session: SessionDep) -> RemoveMember:
    return RemoveMember(
        SqlMembershipRepository(session), RecordAuditEvent(SqlAuditLogRepository(session))
    )


def provide_create_invitation(session: SessionDep, settings: SettingsDep) -> CreateInvitation:
    return CreateInvitation(
        SqlInvitationRepository(session),
        SqlMembershipRepository(session),
        FindUserByEmail(SqlUserRepository(session)),
        RecordAuditEvent(SqlAuditLogRepository(session)),
        app_origin=settings.app_origin,
    )


def provide_list_invitations(session: SessionDep) -> ListInvitations:
    return ListInvitations(SqlInvitationRepository(session))


def provide_revoke_invitation(session: SessionDep) -> RevokeInvitation:
    return RevokeInvitation(
        SqlInvitationRepository(session), RecordAuditEvent(SqlAuditLogRepository(session))
    )
