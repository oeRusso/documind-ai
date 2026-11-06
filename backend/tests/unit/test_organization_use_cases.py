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

    def __init__(self, tenant: "FakeTenantContext") -> None:
        self.items: dict[UUID, Organization] = {}
        self.tenant = tenant

    async def add(self, organization: Organization) -> None:
        # Mimics the database: UNIQUE slug, and RLS only accepts rows of the active organization.
        if any(org.slug == organization.slug for org in self.items.values()):
            raise OrganizationSlugTakenError()
        assert self.tenant.organization_id == organization.id, "tenant context not set"
        self.items[organization.id] = organization

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        return self.items.get(organization_id)


class FakeTenantContext:
    def __init__(self) -> None:
        self.user_id: UUID | None = None
        self.organization_id: UUID | None = None

    async def set_user(self, user_id: UUID) -> None:
        self.user_id = user_id

    async def set_organization(self, organization_id: UUID) -> None:
        self.organization_id = organization_id


@pytest.fixture
def tenant() -> FakeTenantContext:
    return FakeTenantContext()


@pytest.fixture
def repository(tenant: FakeTenantContext) -> InMemoryOrganizationRepository:
    return InMemoryOrganizationRepository(tenant)


def make_create(repository: InMemoryOrganizationRepository) -> CreateOrganization:
    return CreateOrganization(
        repository, repository.tenant, id_factory=lambda: ORG_ID, clock=lambda: NOW
    )


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
        await CreateOrganization(repository, repository.tenant).execute(
            CreateOrganizationCommand(name="Otra Acme", slug="ACME")
        )


async def test_create_organization_uses_uuid_v7_by_default(
    repository: InMemoryOrganizationRepository,
) -> None:
    organization = await CreateOrganization(repository, repository.tenant).execute(
        CreateOrganizationCommand(name="Acme", slug="acme")
    )

    assert organization.id.version == 7


async def test_create_organization_enters_the_new_tenant(
    repository: InMemoryOrganizationRepository, tenant: FakeTenantContext
) -> None:
    await make_create(repository).execute(CreateOrganizationCommand(name="Acme", slug="acme"))

    assert tenant.organization_id == ORG_ID


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
