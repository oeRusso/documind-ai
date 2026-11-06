"""Use cases: read organizations the caller belongs to."""

from dataclasses import dataclass
from uuid import UUID

from app.modules.organizations.application.resolve_membership import ResolveMembership
from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.errors import OrganizationNotFoundError
from app.modules.organizations.domain.repository import (
    MembershipRepository,
    OrganizationRepository,
)
from app.modules.organizations.domain.roles import Role


@dataclass(frozen=True, slots=True)
class OrganizationWithRole:
    organization: Organization
    role: Role


class GetOrganization:
    def __init__(
        self, organizations: OrganizationRepository, memberships: MembershipRepository
    ) -> None:
        self._organizations = organizations
        self._memberships = memberships

    async def execute(self, organization_id: UUID, user_id: UUID) -> OrganizationWithRole:
        # Layer 1: the backend checks membership. Non-members get the same 404 as a missing id.
        membership = await ResolveMembership(self._memberships).execute(organization_id, user_id)
        organization = await self._organizations.get_by_id(organization_id)
        if organization is None:
            raise OrganizationNotFoundError()
        return OrganizationWithRole(organization=organization, role=membership.role)


class ListMyOrganizations:
    """The organization selector: every organization the user belongs to, with their role."""

    def __init__(
        self, organizations: OrganizationRepository, memberships: MembershipRepository
    ) -> None:
        self._organizations = organizations
        self._memberships = memberships

    async def execute(self, user_id: UUID) -> list[OrganizationWithRole]:
        result = []
        # One query per organization: fine for the handful of organizations a person is in.
        for membership in await self._memberships.list_by_user(user_id):
            organization = await self._organizations.get_by_id(membership.organization_id)
            if organization is not None:
                result.append(OrganizationWithRole(organization=organization, role=membership.role))
        return result
