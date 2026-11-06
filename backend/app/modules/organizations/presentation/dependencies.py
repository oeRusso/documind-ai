"""Wiring: which concrete implementation each organizations use case receives."""

from app.core.dependencies import SessionDep
from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
from app.modules.organizations.application.create_organization import CreateOrganization
from app.modules.organizations.application.get_organization import (
    GetOrganization,
    ListMyOrganizations,
)
from app.modules.organizations.infrastructure.sql_repository import (
    SqlMembershipRepository,
    SqlOrganizationRepository,
)


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
