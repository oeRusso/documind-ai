"""Repository interface. `application` depends on this, never on the SQL implementation."""

from typing import Protocol
from uuid import UUID

from app.modules.organizations.domain.entities import Organization


class OrganizationRepository(Protocol):
    async def add(self, organization: Organization) -> None:
        """Persist a new organization. Raises OrganizationSlugTakenError on duplicate slug."""
        ...

    async def get_by_id(self, organization_id: UUID) -> Organization | None: ...

    async def get_by_slug(self, slug: str) -> Organization | None: ...
