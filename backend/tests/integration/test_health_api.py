"""Readiness against a real database."""

import httpx


async def test_ready_is_200_with_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
