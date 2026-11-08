"""Members of an organization over HTTP (stage 2, step 16). Criterion 3: a viewer gets 403
when trying admin actions."""

from uuid import UUID

import httpx
import pytest
from sqlalchemy import NullPool, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.infrastructure.database.tenant import CURRENT_ORG
from app.modules.organizations.infrastructure.sql_repository import SqlMembershipRepository
from tests.db import migrator_test_url
from tests.integration.api_helpers import Acme, first_organization_id, register


async def members(client: httpx.AsyncClient, acme: Acme) -> dict[str, dict[str, str]]:
    response = await client.get("/api/v1/members", headers=acme.headers(acme.owner))
    assert response.status_code == 200, response.text
    return {item["email"]: item for item in response.json()["items"]}


async def test_list_members_of_the_active_organization(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    response = await client.get("/api/v1/members", headers=acme.headers(acme.viewer))

    assert response.status_code == 200
    page = response.json()
    assert page["next_cursor"] is None
    assert [(m["email"], m["role"]) for m in page["items"]] == [
        ("ana@example.com", "owner"),
        ("carla@example.com", "admin"),
        ("bob@example.com", "viewer"),
    ]


async def test_members_need_an_organization_you_belong_to(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    outsider = await register(client, "eve@example.com", slug="eves")

    no_header = await client.get("/api/v1/members", headers=outsider.auth)
    not_mine = await client.get("/api/v1/members", headers=acme.headers(outsider))

    assert no_header.status_code == 422
    assert not_mine.status_code == 404
    assert not_mine.json()["error"]["code"] == "organization_not_found"


# --- Criterion 3 ----------------------------------------------------------------------------


async def test_a_viewer_gets_403_on_admin_actions(client: httpx.AsyncClient, acme: Acme) -> None:
    carla = (await members(client, acme))["carla@example.com"]

    patch = await client.patch(
        f"/api/v1/members/{carla['id']}", json={"role": "viewer"}, headers=acme.headers(acme.viewer)
    )
    delete = await client.delete(
        f"/api/v1/members/{carla['id']}", headers=acme.headers(acme.viewer)
    )

    assert (patch.status_code, delete.status_code) == (403, 403)
    assert patch.json()["error"]["code"] == "forbidden"
    assert (await members(client, acme))["carla@example.com"]["role"] == "admin"


# --- Managing -------------------------------------------------------------------------------


async def test_admin_changes_a_viewer_into_member(client: httpx.AsyncClient, acme: Acme) -> None:
    bob = (await members(client, acme))["bob@example.com"]

    response = await client.patch(
        f"/api/v1/members/{bob['id']}", json={"role": "member"}, headers=acme.headers(acme.admin)
    )

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "bob@example.com"
    assert response.json()["role"] == "member"
    assert (await members(client, acme))["bob@example.com"]["role"] == "member"


async def test_admin_cannot_promote_to_admin_nor_touch_the_owner(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    current = await members(client, acme)
    bob, ana = current["bob@example.com"], current["ana@example.com"]
    headers = acme.headers(acme.admin)

    promote = await client.patch(
        f"/api/v1/members/{bob['id']}", json={"role": "admin"}, headers=headers
    )
    demote_owner = await client.patch(
        f"/api/v1/members/{ana['id']}", json={"role": "viewer"}, headers=headers
    )

    assert (promote.status_code, demote_owner.status_code) == (403, 403)


async def test_the_last_owner_cannot_leave_the_organization_without_owner(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    ana = (await members(client, acme))["ana@example.com"]
    headers = acme.headers(acme.owner)

    demote = await client.patch(
        f"/api/v1/members/{ana['id']}", json={"role": "admin"}, headers=headers
    )
    remove = await client.delete(f"/api/v1/members/{ana['id']}", headers=headers)

    assert (demote.status_code, remove.status_code) == (409, 409)
    assert demote.json()["error"]["code"] == "last_owner"


async def test_a_removed_member_loses_access(client: httpx.AsyncClient, acme: Acme) -> None:
    bob = (await members(client, acme))["bob@example.com"]

    response = await client.delete(f"/api/v1/members/{bob['id']}", headers=acme.headers(acme.owner))

    assert response.status_code == 204
    after = await client.get("/api/v1/members", headers=acme.headers(acme.viewer))
    assert after.status_code == 404
    assert "bob@example.com" not in await members(client, acme)


async def test_a_membership_of_another_organization_is_404(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    # bob's owner membership in his own organization, used with acme as the active one.
    bobs_org = await first_organization_id(client, acme.viewer)
    bobs_members = await client.get(
        "/api/v1/members", headers={**acme.viewer.auth, "X-Organization-Id": bobs_org}
    )
    bobs_owner_id = bobs_members.json()["items"][0]["id"]

    response = await client.delete(
        f"/api/v1/members/{bobs_owner_id}", headers=acme.headers(acme.owner)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "membership_not_found"


async def test_role_changes_and_removals_are_audited(client: httpx.AsyncClient, acme: Acme) -> None:
    current = await members(client, acme)
    headers = acme.headers(acme.owner)
    await client.patch(
        f"/api/v1/members/{current['bob@example.com']['id']}",
        json={"role": "member"},
        headers=headers,
    )
    await client.delete(f"/api/v1/members/{current['carla@example.com']['id']}", headers=headers)

    engine = create_async_engine(migrator_test_url(), poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config(:name, :value, true)"), {"name": CURRENT_ORG, "value": acme.id}
        )
        actions = (
            (
                await connection.execute(
                    text(
                        "SELECT action FROM audit_logs WHERE action LIKE 'membership.%' "
                        "ORDER BY created_at"
                    )
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    assert actions == ["membership.role_changed", "membership.removed"]


async def test_counting_owners_locks_them_until_the_transaction_ends(acme: Acme) -> None:
    """While one request checks "is there another owner?", a second one cannot change any
    owner: it has to wait, so two owners demoting each other cannot leave zero owners."""
    engine = create_async_engine(migrator_test_url(), poolclass=NullPool)
    enter = text("SELECT set_config(:name, :value, true)")
    async with engine.connect() as first, engine.connect() as second:
        await first.begin()
        await first.execute(enter, {"name": CURRENT_ORG, "value": acme.id})
        repository = SqlMembershipRepository(AsyncSession(bind=first))
        assert await repository.count_owners_for_update(UUID(acme.id)) == 1

        await second.begin()
        await second.execute(enter, {"name": CURRENT_ORG, "value": acme.id})
        with pytest.raises(DBAPIError, match="could not obtain lock"):
            await second.execute(
                text("SELECT id FROM memberships WHERE role = 'owner' FOR UPDATE NOWAIT")
            )
        await first.rollback()
    await engine.dispose()
