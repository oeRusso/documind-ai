"""Attempt limits over HTTP (stage 2, step 20; ADR 0005), with tiny limits to keep tests fast."""

from collections.abc import AsyncIterator

import httpx
import pytest

from app.core.config import Settings
from app.main import create_app
from tests.integration.api_helpers import PASSWORD, register
from tests.integration.conftest import truncate_all_tables

WRONG_PASSWORD = "no es la clave"  # pragma: allowlist secret


@pytest.fixture
async def strict_client(db_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    settings = db_settings.model_copy(
        update={
            "login_limit_per_ip_per_minute": 4,
            "login_limit_per_email_per_15_minutes": 2,
            "register_limit_per_ip_per_hour": 2,
            "accept_invitation_limit_per_user_per_minute": 2,
        }
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        yield client
    await app.state.engine.dispose()
    await truncate_all_tables()


def assert_rate_limited(response: httpx.Response) -> None:
    assert response.status_code == 429, response.text
    assert response.json()["error"]["code"] == "rate_limited"
    assert int(response.headers["Retry-After"]) >= 1


async def login(client: httpx.AsyncClient, email: str) -> httpx.Response:
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": WRONG_PASSWORD}
    )


async def test_login_is_limited_per_email(strict_client: httpx.AsyncClient) -> None:
    await register(strict_client, "ana@example.com")
    for _ in range(2):
        assert (await login(strict_client, "ana@example.com")).status_code == 401

    blocked = await strict_client.post(
        "/api/v1/auth/login", json={"email": "ana@example.com", "password": PASSWORD}
    )

    assert_rate_limited(blocked)
    # Other accounts from the same IP still work, until the IP limit.
    assert (await login(strict_client, "bob@example.com")).status_code == 401


async def test_login_is_limited_per_ip(strict_client: httpx.AsyncClient) -> None:
    for email in ("a@example.com", "b@example.com", "c@example.com", "d@example.com"):
        assert (await login(strict_client, email)).status_code == 401

    assert_rate_limited(await login(strict_client, "e@example.com"))


async def test_register_is_limited_per_ip(strict_client: httpx.AsyncClient) -> None:
    await register(strict_client, "a@example.com", slug="aaa")
    await register(strict_client, "b@example.com", slug="bbb")

    third = await strict_client.post(
        "/api/v1/auth/register",
        json={
            "email": "c@example.com",
            "password": PASSWORD,
            "organization_name": "C",
            "organization_slug": "ccc",
        },
    )

    assert_rate_limited(third)


async def test_accepting_invitations_is_limited_per_user(strict_client: httpx.AsyncClient) -> None:
    eve = await register(strict_client, "eve@example.com", slug="eves")
    guess = {"organization_id": "0192f1c4-0000-7000-8000-000000000001", "token": "x" * 43}

    for _ in range(2):
        response = await strict_client.post(
            "/api/v1/invitations/accept", json=guess, headers=eve.auth
        )
        assert response.status_code == 404

    assert_rate_limited(
        await strict_client.post("/api/v1/invitations/accept", json=guess, headers=eve.auth)
    )
