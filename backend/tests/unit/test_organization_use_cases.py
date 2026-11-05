"""Use cases tested with an in-memory repository: no database, no FastAPI."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.organizations.application.create_organization import (
    CreateOrganization,
    CreateOrganizationCommand,
)
from app.modules.organizations.application.get_organization import GetOrganization
from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.errors import (
    OrganizationNotFoundError,
    OrganizationSlugTakenError,
)

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
ORG_ID = UUID("0192f1c4-0000-7000-8000-000000000001")


class InMemoryOrganizationRepository:
    """Satisfies the OrganizationRepository Protocol without inheriting from it."""

    def __init__(self) -> None:
        self.items: dict[UUID, Organization] = {}

    async def add(self, organization: Organization) -> None:
        self.items[organization.id] = organization

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        return self.items.get(organization_id)

    async def get_by_slug(self, slug: str) -> Organization | None:
        return next((org for org in self.items.values() if org.slug == slug), None)


@pytest.fixture
def repository() -> InMemoryOrganizationRepository:
    return InMemoryOrganizationRepository()


def make_create(repository: InMemoryOrganizationRepository) -> CreateOrganization:
    return CreateOrganization(repository, id_factory=lambda: ORG_ID, clock=lambda: NOW)


async def test_create_organization_persists_it(repository: InMemoryOrganizationRepository) -> None:
    organization = await make_create(repository).execute(
        CreateOrganizationCommand(name="Acme", slug="acme")
    )

    assert organization.id == ORG_ID
    assert organization.created_at == NOW
    assert repository.items[ORG_ID] == organization


async def test_create_organization_rejects_duplicate_slug(
    repository: InMemoryOrganizationRepository,
) -> None:
    await make_create(repository).execute(CreateOrganizationCommand(name="Acme", slug="acme"))

    with pytest.raises(OrganizationSlugTakenError):
        await CreateOrganization(repository).execute(
            CreateOrganizationCommand(name="Otra Acme", slug="ACME")
        )


async def test_create_organization_uses_uuid_v7_by_default(
    repository: InMemoryOrganizationRepository,
) -> None:
    organization = await CreateOrganization(repository).execute(
        CreateOrganizationCommand(name="Acme", slug="acme")
    )

    assert organization.id.version == 7


async def test_get_organization_returns_it(repository: InMemoryOrganizationRepository) -> None:
    created = await make_create(repository).execute(
        CreateOrganizationCommand(name="Acme", slug="acme")
    )

    assert await GetOrganization(repository).execute(ORG_ID) == created


async def test_get_organization_raises_when_missing(
    repository: InMemoryOrganizationRepository,
) -> None:
    with pytest.raises(OrganizationNotFoundError):
        await GetOrganization(repository).execute(ORG_ID)
