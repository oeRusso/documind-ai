"""Auth over HTTP: register, login, me, refresh (rotation, reuse), logout, cookies and CSRF."""

import httpx
import pytest

from tests.integration.api_helpers import (
    PASSWORD,
    LoggedIn,
    login,
    post_with_cookie,
    register,
    session_after,
)

REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
WRONG_PASSWORD = "otra clave larga"  # pragma: allowlist secret


async def refresh(client: httpx.AsyncClient, session: LoggedIn) -> httpx.Response:
    return await post_with_cookie(client, REFRESH, session.refresh_token, session.csrf_token)


# --- Register, login, me -------------------------------------------------------------------


async def test_register_returns_an_access_token_that_identifies_the_user(
    client: httpx.AsyncClient,
) -> None:
    session = await register(client)

    me = await client.get("/api/v1/auth/me", headers=session.auth)

    assert me.status_code == 200
    assert me.json()["email"] == "ana@example.com"


async def test_refresh_cookie_is_httponly_secure_lax_and_scoped_to_auth(
    client: httpx.AsyncClient,
) -> None:
    await register(client, email="x@example.com")
    response = await client.post(
        "/api/v1/auth/login", json={"email": "x@example.com", "password": PASSWORD}
    )

    cookies = {c.split("=", 1)[0]: c for c in response.headers.get_list("set-cookie")}
    refresh_cookie = cookies["refresh_token"].lower()
    for attribute in ("httponly", "secure", "samesite=lax", "path=/api/v1/auth"):
        assert attribute in refresh_cookie
    csrf_cookie = cookies["csrf_token"].lower()
    assert "secure" in csrf_cookie and "httponly" not in csrf_cookie
    assert "refresh_token" not in response.json()  # never in the body


async def test_duplicate_email_is_409(client: httpx.AsyncClient) -> None:
    await register(client, email="ana@example.com", slug="one")

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ANA@example.com",
            "password": PASSWORD,
            "organization_name": "Two",
            "organization_slug": "two",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"


async def test_wrong_password_is_401_with_a_generic_message(client: httpx.AsyncClient) -> None:
    await register(client)

    wrong = await client.post(
        "/api/v1/auth/login", json={"email": "ana@example.com", "password": WRONG_PASSWORD}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "nadie@example.com", "password": PASSWORD}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert wrong.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("headers", "code"),
    [({}, "not_authenticated"), ({"Authorization": "Bearer not-a-jwt"}, "invalid_token")],
)
async def test_me_requires_a_valid_access_token(
    client: httpx.AsyncClient, headers: dict[str, str], code: str
) -> None:
    response = await client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == code


# --- Refresh -------------------------------------------------------------------------------


async def test_refresh_rotates_the_cookie_and_returns_a_new_access_token(
    client: httpx.AsyncClient,
) -> None:
    first = await register(client)

    second = session_after(await refresh(client, first))

    assert second.refresh_token != first.refresh_token
    me = await client.get("/api/v1/auth/me", headers=second.auth)
    assert me.status_code == 200


async def test_reusing_a_rotated_refresh_token_ends_the_session(
    client: httpx.AsyncClient,
) -> None:
    """Stage 2 criterion: reusing an already rotated refresh token invalidates the session."""
    first = await register(client)
    second = session_after(await refresh(client, first))

    replay = await refresh(client, first)  # e.g. a stolen copy of the old cookie

    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "session_revoked"
    # The legitimate, newest token is dead too (the revocation was committed despite the 401).
    after = await refresh(client, second)
    assert after.status_code == 401
    assert after.json()["error"]["code"] == "invalid_token"


async def test_other_logins_survive_a_reuse(client: httpx.AsyncClient) -> None:
    laptop = await register(client)
    phone = await login(client)
    await refresh(client, laptop)

    await refresh(client, laptop)  # reuse on the laptop's family

    assert (await refresh(client, phone)).status_code == 200


async def test_refresh_without_cookie_is_401(client: httpx.AsyncClient) -> None:
    session = await register(client)
    client.cookies.clear()

    response = await client.post(
        REFRESH,
        headers={
            "Origin": "http://localhost:3000",
            "X-CSRF-Token": session.csrf_token,
            "Cookie": f"csrf_token={session.csrf_token}",
        },
    )

    assert response.status_code == 401


# --- CSRF ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("origin", "csrf_header"),
    [
        ("https://evil.example", None),  # foreign site
        ("http://localhost:3000", ""),  # header missing
        ("http://localhost:3000", "forged-value"),  # header does not match the cookie
    ],
)
async def test_refresh_and_logout_reject_csrf(
    client: httpx.AsyncClient, origin: str, csrf_header: str | None
) -> None:
    session = await register(client)

    for path in (REFRESH, LOGOUT):
        response = await post_with_cookie(
            client,
            path,
            session.refresh_token,
            session.csrf_token,
            origin=origin,
            csrf_header=csrf_header,
        )
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "csrf_failed"

    # Nothing happened: the session still works.
    assert (await refresh(client, session)).status_code == 200


async def test_login_from_a_foreign_origin_is_rejected(client: httpx.AsyncClient) -> None:
    await register(client)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "ana@example.com", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403


# --- Logout --------------------------------------------------------------------------------


async def test_logout_clears_cookies_and_ends_the_session(client: httpx.AsyncClient) -> None:
    session = await register(client)

    response = await post_with_cookie(client, LOGOUT, session.refresh_token, session.csrf_token)

    assert response.status_code == 204
    cleared = " ".join(response.headers.get_list("set-cookie")).lower()
    assert "refresh_token=" in cleared and "max-age=0" in cleared
    assert (await refresh(client, session)).status_code == 401


async def test_a_filled_honeypot_looks_like_any_invalid_form(client: httpx.AsyncClient) -> None:
    """ADR 0005: the hidden `website` field is only filled by bots. Nothing is created and the
    answer is the same generic one as any invalid form."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "bot@example.com",
            "password": PASSWORD,
            "organization_name": "Spam",
            "organization_slug": "spam",
            "website": "https://spam.example",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["message"] == "Datos inválidos"
    login = await client.post(
        "/api/v1/auth/login", json={"email": "bot@example.com", "password": PASSWORD}
    )
    assert login.status_code == 401


async def test_an_empty_honeypot_is_fine(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ana@example.com",
            "password": PASSWORD,
            "organization_name": "Acme",
            "organization_slug": "acme",
            "website": "",
        },
    )

    assert response.status_code == 201
