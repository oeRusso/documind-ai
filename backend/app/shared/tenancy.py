"""Port for the tenant context of the current transaction (ADR 0003).

Use cases call it when they *change* the context, e.g. right after creating an organization
(the new rows must belong to it). The request dependency sets it for everything else.
The implementation lives in app/infrastructure/database/tenant.py.
"""

from typing import Protocol
from uuid import UUID


class TenantContext(Protocol):
    async def set_user(self, user_id: UUID) -> None:
        """Who is acting. Lets them see their own memberships in every organization."""
        ...

    async def set_organization(self, organization_id: UUID) -> None:
        """The active organization. Only its rows are visible and writable from now on."""
        ...
