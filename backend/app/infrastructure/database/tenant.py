"""Tenant context for PostgreSQL Row Level Security (ADR 0003).

set_config(name, value, true) works like `SET LOCAL`: the value lasts until the transaction
ends, so it never leaks to the next request that reuses the pooled connection.
`SET LOCAL` itself cannot be used here because it does not accept bind parameters.
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CURRENT_USER = "app.current_user"
CURRENT_ORG = "app.current_org"

_SET_LOCAL = text("SELECT set_config(:name, :value, true)")


class SqlTenantContext:
    """Implements app.shared.tenancy.TenantContext on the request's session (same transaction)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_user(self, user_id: UUID) -> None:
        await self._session.execute(_SET_LOCAL, {"name": CURRENT_USER, "value": str(user_id)})

    async def set_organization(self, organization_id: UUID) -> None:
        await self._session.execute(
            _SET_LOCAL, {"name": CURRENT_ORG, "value": str(organization_id)}
        )
