"""Use case: create an organization, with its creator as owner."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.repository import (
    MembershipRepository,
    OrganizationRepository,
)
from app.modules.organizations.domain.roles import Role
from app.shared.ids import new_id, utc_now
from app.shared.tenancy import TenantContext


@dataclass(frozen=True, slots=True)
class CreateOrganizationCommand:
    name: str
    slug: str
    owner_id: UUID


class CreateOrganization:
    def __init__(
        self,
        organizations: OrganizationRepository,
        memberships: MembershipRepository,
        tenant: TenantContext,
        *,
        id_factory: Callable[[], UUID] = new_id,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._organizations = organizations
        self._memberships = memberships
        self._tenant = tenant
        self._id_factory = id_factory
        self._clock = clock

    async def execute(self, command: CreateOrganizationCommand) -> Organization:
        now = self._clock()
        organization = Organization.create(
            id=self._id_factory(), name=command.name, slug=command.slug, now=now
        )
        # From here on the transaction acts inside the new organization: RLS only accepts
        # rows of the active organization (ADR 0003). A duplicate slug is caught by the
        # UNIQUE constraint, which sees every organization (RLS would hide them from a SELECT).
        await self._tenant.set_organization(organization.id)
        await self._organizations.add(organization)
        # An organization never exists without an owner.
        await self._memberships.add(
            Membership.create(
                id=self._id_factory(),
                organization_id=organization.id,
                user_id=command.owner_id,
                role=Role.OWNER,
                now=now,
            )
        )
        return organization
