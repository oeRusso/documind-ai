"""Small HTTP helpers shared by the API tests."""

from dataclasses import dataclass

import httpx

from tests.conftest import APP_ORIGIN

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
