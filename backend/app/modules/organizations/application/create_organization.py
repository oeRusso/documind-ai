"""Use case: create an organization."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.errors import OrganizationSlugTakenError
from app.modules.organizations.domain.repository import OrganizationRepository
from app.shared.ids import new_id, utc_now


@dataclass(frozen=True, slots=True)
class CreateOrganizationCommand:
    name: str
    slug: str


class CreateOrganization:
    def __init__(
        self,
        repository: OrganizationRepository,
        *,
        id_factory: Callable[[], UUID] = new_id,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._clock = clock

    async def execute(self, command: CreateOrganizationCommand) -> Organization:
        organization = Organization.create(
            id=self._id_factory(),
            name=command.name,
            slug=command.slug,
            now=self._clock(),
        )
        # Friendly early check; the UNIQUE constraint in the database is the real guarantee.
        if await self._repository.get_by_slug(organization.slug) is not None:
            raise OrganizationSlugTakenError()
        await self._repository.add(organization)
        return organization
