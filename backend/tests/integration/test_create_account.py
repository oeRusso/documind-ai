"""app.jobs.create_account: the first owner on a server with closed sign-up."""

import httpx

from app.core.config import Settings
from app.jobs.create_account import create_account
from tests.integration.api_helpers import PASSWORD


async def test_the_new_owner_can_log_in_and_owns_the_organization(
    client: httpx.AsyncClient, db_settings: Settings
) -> None:
    await create_account(db_settings, "esteban@example.com", PASSWORD, "Mi Empresa", "mi-empresa")

    login = await client.post(
        "/api/v1/auth/login", json={"email": "esteban@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    [organization] = (await client.get("/api/v1/organizations", headers=headers)).json()["items"]
    assert (organization["slug"], organization["role"]) == ("mi-empresa", "owner")
