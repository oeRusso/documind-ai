"""Use case: get one organization by id."""

from uuid import UUID

from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.errors import OrganizationNotFoundError
from app.modules.organizations.domain.repository import OrganizationRepository


class GetOrganization:
    def __init__(self, repository: OrganizationRepository) -> None:
        self._repository = repository

    async def execute(self, organization_id: UUID) -> Organization:
        organization = await self._repository.get_by_id(organization_id)
        if organization is None:
            raise OrganizationNotFoundError()
        return organization
