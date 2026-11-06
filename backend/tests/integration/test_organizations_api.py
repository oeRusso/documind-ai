"""End to end through HTTP: router -> use case -> SQL repository -> PostgreSQL."""

from uuid import UUID

import httpx


async def create(
    client: httpx.AsyncClient, name: str = "Acme", slug: str = "acme"
) -> httpx.Response:
    return await client.post("/api/v1/organizations", json={"name": name, "slug": slug})


async def test_ready_is_200_with_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_create_then_get_organization(client: httpx.AsyncClient) -> None:
    created = await create(client)

    assert created.status_code == 201
    body = created.json()
    assert UUID(body["id"]).version == 7
    assert body["slug"] == "acme"

    fetched = await client.get(f"/api/v1/organizations/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


async def test_duplicate_slug_is_409(client: httpx.AsyncClient) -> None:
    await create(client)

    response = await create(client, name="Otra", slug="ACME")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "organization_slug_taken"


async def test_unknown_organization_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/organizations/0192f1c4-0000-7000-8000-000000000099")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "organization_not_found"


async def test_domain_validation_is_422(client: httpx.AsyncClient) -> None:
    response = await create(client, slug="acme corp!")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_organization"
