"""Organizations over HTTP, with authentication (stage 2, step 14)."""

import httpx

from tests.integration.api_helpers import register

UNKNOWN_ID = "0192f1c4-0000-7000-8000-000000000099"


async def test_after_registering_the_user_sees_their_organization(
    client: httpx.AsyncClient,
) -> None:
    ana = await register(client, slug="acme")

    response = await client.get("/api/v1/organizations", headers=ana.auth)

    assert response.status_code == 200
    page = response.json()
    assert page["next_cursor"] is None
    assert [(o["slug"], o["role"]) for o in page["items"]] == [("acme", "owner")]


async def test_create_another_organization(client: httpx.AsyncClient) -> None:
    ana = await register(client, slug="acme")

    created = await client.post(
        "/api/v1/organizations", json={"name": "Beta", "slug": "beta"}, headers=ana.auth
    )

    assert created.status_code == 201
    assert created.json()["role"] == "owner"
    listed = await client.get("/api/v1/organizations", headers=ana.auth)
    assert [o["slug"] for o in listed.json()["items"]] == ["acme", "beta"]


async def test_get_own_organization(client: httpx.AsyncClient) -> None:
    ana = await register(client, slug="acme")
    [org] = (await client.get("/api/v1/organizations", headers=ana.auth)).json()["items"]

    response = await client.get(f"/api/v1/organizations/{org['id']}", headers=ana.auth)

    assert response.status_code == 200
    assert response.json() == org


async def test_another_users_organization_is_404_not_403(client: httpx.AsyncClient) -> None:
    ana = await register(client, email="ana@example.com", slug="acme")
    bob = await register(client, email="bob@example.com", slug="bobs")
    [bobs_org] = (await client.get("/api/v1/organizations", headers=bob.auth)).json()["items"]

    foreign = await client.get(f"/api/v1/organizations/{bobs_org['id']}", headers=ana.auth)
    missing = await client.get(f"/api/v1/organizations/{UNKNOWN_ID}", headers=ana.auth)

    # Indistinguishable from outside: an organization you are not in "does not exist".
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"]["code"] == missing.json()["error"]["code"]
    listed = await client.get("/api/v1/organizations", headers=ana.auth)
    assert [o["slug"] for o in listed.json()["items"]] == ["acme"]


async def test_taken_slug_is_409(client: httpx.AsyncClient) -> None:
    await register(client, email="ana@example.com", slug="acme")
    bob = await register(client, email="bob@example.com", slug="bobs")

    response = await client.post(
        "/api/v1/organizations", json={"name": "Acme 2", "slug": "ACME"}, headers=bob.auth
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "organization_slug_taken"


async def test_invalid_slug_is_422(client: httpx.AsyncClient) -> None:
    ana = await register(client)

    response = await client.post(
        "/api/v1/organizations", json={"name": "X", "slug": "con espacios!"}, headers=ana.auth
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_organization"


async def test_organizations_require_login(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/organizations")).status_code == 401
    created = await client.post("/api/v1/organizations", json={"name": "X", "slug": "xx"})
    assert created.status_code == 401
