"""SqlMembershipRepository with the `app` role and RLS."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.organizations.domain.roles import Role
from app.modules.organizations.infrastructure.sql_repository import SqlMembershipRepository
from tests.integration.factories import create_organization, create_user


async def test_owner_membership_is_created_with_the_organization(
    app_session: AsyncSession,
) -> None:
    ana = await create_user(app_session)
    organization = await create_organization(app_session, ana)

    membership = await SqlMembershipRepository(app_session).get_by_user(organization.id, ana.id)

    assert membership is not None
    assert membership.role is Role.OWNER


async def test_user_lists_their_organizations_before_choosing_one(
    app_session: AsyncSession,
) -> None:
    ana = await create_user(app_session)
    first = await create_organization(app_session, ana, slug="first")
    second = await create_organization(app_session, ana, slug="second")
    bob = await create_user(app_session, "bob@example.com")
    await create_organization(app_session, bob, slug="bobs")

    # A new request for ana: user known, no organization chosen. The context is per
    # transaction, so a savepoint is not enough; set it as the API will (step 14).
    await app_session.execute(text("SELECT set_config('app.current_org', '', true)"))
    await SqlTenantContext(app_session).set_user(ana.id)

    memberships = await SqlMembershipRepository(app_session).list_by_user(ana.id)

    assert [m.organization_id for m in memberships] == [first.id, second.id]
