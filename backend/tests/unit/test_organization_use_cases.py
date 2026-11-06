"""Use cases tested with in-memory fakes: no database, no FastAPI."""

from datetime import UTC, datetime
from itertools import count
from uuid import UUID

import pytest

from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.organizations.application.create_organization import (
    CreateOrganization,
    CreateOrganizationCommand,
)
from app.modules.organizations.application.get_organization import (
    GetOrganization,
    ListMyOrganizations,
)
from app.modules.organizations.domain.errors import (
    OrganizationNotFoundError,
    OrganizationSlugTakenError,
)
from app.modules.organizations.domain.roles import Role
from tests.fakes import (
    FakeTenantContext,
    InMemoryAuditLogRepository,
    InMemoryMembershipRepository,
    InMemoryOrganizationRepository,
)

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
OWNER_ID = UUID("0192f1c4-0000-7000-8000-0000000000d1")


class Setup:
    def __init__(self) -> None:
        self.tenant = FakeTenantContext()
        self.organizations = InMemoryOrganizationRepository(self.tenant)
        self.memberships = InMemoryMembershipRepository(self.tenant)
        self.audit = InMemoryAuditLogRepository()
        ids = count(1)
        self.create = CreateOrganization(
            self.organizations,
            self.memberships,
            self.tenant,
            RecordAuditEvent(self.audit),
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
        InMemoryOrganizationRepository(tenant),
        InMemoryMembershipRepository(tenant),
        tenant,
        RecordAuditEvent(InMemoryAuditLogRepository()),
    )

    organization = await use_case.execute(command())

    assert organization.id.version == 7


async def test_creation_is_audited(setup: Setup) -> None:
    organization = await setup.create.execute(command())

    [event] = setup.audit.events
    assert event.action == "organization.created"
    assert event.organization_id == organization.id
    assert event.user_id == OWNER_ID


async def test_member_gets_the_organization_with_their_role(setup: Setup) -> None:
    created = await setup.create.execute(command())

    found = await GetOrganization(setup.organizations, setup.memberships).execute(
        created.id, OWNER_ID
    )

    assert found.organization == created
    assert found.role is Role.OWNER


async def test_non_member_gets_404_even_if_the_organization_exists(setup: Setup) -> None:
    created = await setup.create.execute(command())

    with pytest.raises(OrganizationNotFoundError):
        await GetOrganization(setup.organizations, setup.memberships).execute(
            created.id, UUID(int=999)
        )


async def test_list_my_organizations(setup: Setup) -> None:
    first = await setup.create.execute(command(slug="first"))
    second = await setup.create.execute(command(slug="second"))

    mine = await ListMyOrganizations(setup.organizations, setup.memberships).execute(OWNER_ID)

    assert [(item.organization.id, item.role) for item in mine] == [
        (first.id, Role.OWNER),
        (second.id, Role.OWNER),
    ]
    assert (
        await ListMyOrganizations(setup.organizations, setup.memberships).execute(UUID(int=999))
        == []
    )
