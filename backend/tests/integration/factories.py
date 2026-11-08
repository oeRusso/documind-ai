"""Build real rows through the real use cases and SQL repositories (app role, RLS on)."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
from app.modules.organizations.application.create_organization import (
    CreateOrganization,
    CreateOrganizationCommand,
)
from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.infrastructure.sql_repository import (
    SqlMembershipRepository,
    SqlOrganizationRepository,
)
from app.modules.users.domain.entities import User
from app.modules.users.infrastructure.sql_repository import SqlUserRepository
from app.shared.ids import new_id

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


async def create_user(session: AsyncSession, email: str = "ana@example.com") -> User:
    user = User.create(id=new_id(), email=email, password_hash="$argon2id$fake", now=NOW)
    await SqlUserRepository(session).add(user)
    return user


async def create_organization(
    session: AsyncSession, owner: User, slug: str = "acme"
) -> Organization:
    """Leaves the session's tenant context inside the new organization."""
    return await CreateOrganization(
        SqlOrganizationRepository(session),
        SqlMembershipRepository(session),
        SqlTenantContext(session),
        RecordAuditEvent(SqlAuditLogRepository(session)),
    ).execute(CreateOrganizationCommand(name=slug.title(), slug=slug, owner_id=owner.id))
