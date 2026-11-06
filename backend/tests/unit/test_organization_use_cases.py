"""Use cases tested with in-memory fakes: no database, no FastAPI."""

from datetime import UTC, datetime
from itertools import count
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
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
OWNER_ID = UUID("0192f1c4-0000-7000-8000-0000000000d1")


class FakeTenantContext:
    def __init__(self) -> None:
        self.user_id: UUID | None = None
        self.organization_id: UUID | None = None

    async def set_user(self, user_id: UUID) -> None:
        self.user_id = user_id

    async def set_organization(self, organization_id: UUID) -> None:
        self.organization_id = organization_id


class InMemoryOrganizationRepository:
    """Satisfies the OrganizationRepository Protocol without inheriting from it."""

    def __init__(self, tenant: FakeTenantContext) -> None:
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


class InMemoryMembershipRepository:
    def __init__(self, tenant: FakeTenantContext) -> None:
        self.items: list[Membership] = []
        self.tenant = tenant

    async def add(self, membership: Membership) -> None:
        assert self.tenant.organization_id == membership.organization_id, "tenant not set"
        self.items.append(membership)

    async def get_by_user(self, organization_id: UUID, user_id: UUID) -> Membership | None:
        return next(
            (
                m
                for m in self.items
                if m.organization_id == organization_id and m.user_id == user_id
            ),
            None,
        )

    async def list_by_user(self, user_id: UUID) -> list[Membership]:
        return [m for m in self.items if m.user_id == user_id]


class Setup:
    def __init__(self) -> None:
        self.tenant = FakeTenantContext()
        self.organizations = InMemoryOrganizationRepository(self.tenant)
        self.memberships = InMemoryMembershipRepository(self.tenant)
        ids = count(1)
        self.create = CreateOrganization(
            self.organizations,
            self.memberships,
            self.tenant,
            id_factory=lambda: UUID(int=next(ids)),
            clock=lambda: NOW,
        )


@pytest.fixture
def setup() -> Setup:
    return Setup()


def command(name: str = "Acme", slug: str = "acme") -> CreateOrganizationCommand:
    return CreateOrganizationCommand(name=name, slug=slug, owner_id=OWNER_ID)


async def test_create_organization_persists_it(setup: Setup) -> None:
    organization = await setup.create.execute(command())

    assert organization.created_at == NOW
    assert setup.organizations.items[organization.id] == organization


async def test_creator_becomes_owner(setup: Setup) -> None:
    organization = await setup.create.execute(command())

    membership = await setup.memberships.get_by_user(organization.id, OWNER_ID)
    assert membership is not None
    assert membership.role is Role.OWNER


async def test_create_organization_enters_the_new_tenant(setup: Setup) -> None:
    organization = await setup.create.execute(command())

    assert setup.tenant.organization_id == organization.id


async def test_create_organization_rejects_duplicate_slug(setup: Setup) -> None:
    await setup.create.execute(command(slug="acme"))

    with pytest.raises(OrganizationSlugTakenError):
        await setup.create.execute(command(name="Otra Acme", slug="ACME"))


async def test_create_organization_uses_uuid_v7_by_default() -> None:
    tenant = FakeTenantContext()
    use_case = CreateOrganization(
        InMemoryOrganizationRepository(tenant), InMemoryMembershipRepository(tenant), tenant
    )

    organization = await use_case.execute(command())

    assert organization.id.version == 7


async def test_get_organization_returns_it(setup: Setup) -> None:
    created = await setup.create.execute(command())

    assert await GetOrganization(setup.organizations).execute(created.id) == created


async def test_get_organization_raises_when_missing(setup: Setup) -> None:
    with pytest.raises(OrganizationNotFoundError):
        await GetOrganization(setup.organizations).execute(UUID(int=99))
