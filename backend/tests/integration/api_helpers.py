"""Small HTTP helpers shared by the API tests."""

from dataclasses import dataclass

import httpx
from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.infrastructure.database.tenant import CURRENT_ORG
from app.shared.ids import new_id
from tests.conftest import APP_ORIGIN
from tests.db import migrator_test_url

PASSWORD = "una clave bien larga"  # pragma: allowlist secret


@dataclass(frozen=True)
class LoggedIn:
    access_token: str
    refresh_token: str
    csrf_token: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def _session_from(response: httpx.Response) -> LoggedIn:
    return LoggedIn(
        access_token=response.json()["access_token"],
        refresh_token=response.cookies["refresh_token"],
        csrf_token=response.cookies["csrf_token"],
    )


async def register(
    client: httpx.AsyncClient, email: str = "ana@example.com", slug: str = "acme"
) -> LoggedIn:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "organization_name": slug.title(),
            "organization_slug": slug,
        },
    )
    assert response.status_code == 201, response.text
    return _session_from(response)


async def login(client: httpx.AsyncClient, email: str = "ana@example.com") -> LoggedIn:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return _session_from(response)


async def post_with_cookie(
    client: httpx.AsyncClient,
    path: str,
    refresh_token: str,
    csrf_token: str,
    *,
    origin: str = APP_ORIGIN,
    csrf_header: str | None = None,
) -> httpx.Response:
    """Call /auth/refresh or /auth/logout like the browser would, with explicit cookies."""
    client.cookies.clear()  # only the cookies given here
    return await client.post(
        path,
        headers={
            "Origin": origin,
            "X-CSRF-Token": csrf_token if csrf_header is None else csrf_header,
            "Cookie": f"refresh_token={refresh_token}; csrf_token={csrf_token}",
        },
    )


def session_after(response: httpx.Response) -> LoggedIn:
    assert response.status_code == 200, response.text
    return _session_from(response)


async def add_member(organization_id: str, user_id: str, role: str) -> None:
    """Shortcut for tests: insert the membership directly (invitations have their own tests)."""
    engine = create_async_engine(migrator_test_url(), poolclass=NullPool)
    async with engine.begin() as connection:
        # migrator is subject to RLS too (FORCE), so it enters the organization first.
        await connection.execute(
            text("SELECT set_config(:name, :value, true)"),
            {"name": CURRENT_ORG, "value": organization_id},
        )
        await connection.execute(
            text(
                "INSERT INTO memberships (id, organization_id, user_id, role) "
                "VALUES (:id, :org, :user, :role)"
            ),
            {"id": new_id(), "org": organization_id, "user": user_id, "role": role},
        )
    await engine.dispose()


@dataclass
class Acme:
    id: str
    owner: LoggedIn
    admin: LoggedIn
    viewer: LoggedIn

    def headers(self, who: LoggedIn) -> dict[str, str]:
        return {**who.auth, "X-Organization-Id": self.id}


async def user_id(client: httpx.AsyncClient, who: LoggedIn) -> str:
    return str((await client.get("/api/v1/auth/me", headers=who.auth)).json()["id"])


async def first_organization_id(client: httpx.AsyncClient, who: LoggedIn) -> str:
    return str(
        (await client.get("/api/v1/organizations", headers=who.auth)).json()["items"][0]["id"]
    )


async def setup_acme(client: httpx.AsyncClient) -> Acme:
    """ana owns acme; carla is admin and bob is viewer there (each also owns their own org)."""
    ana = await register(client, "ana@example.com", slug="acme")
    carla = await register(client, "carla@example.com", slug="carlas")
    bob = await register(client, "bob@example.com", slug="bobs")
    acme_id = await first_organization_id(client, ana)
    await add_member(acme_id, await user_id(client, carla), "admin")
    await add_member(acme_id, await user_id(client, bob), "viewer")
    return Acme(id=acme_id, owner=ana, admin=carla, viewer=bob)
