"""Invitations over HTTP (stage 2, steps 17 and 18), against PostgreSQL with RLS."""

from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from tests.conftest import APP_ORIGIN
from tests.integration.api_helpers import PASSWORD, Acme, register


async def invite(
    client: httpx.AsyncClient,
    acme: Acme,
    email: str = "nueva@example.com",
    role: str = "member",
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/invitations",
        json={"email": email, "role": role},
        headers=acme.headers(acme.owner),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def link_params(link: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(link).fragment).items()}


# --- Step 17: create, list, revoke ----------------------------------------------------------


async def test_owner_invites_and_gets_the_link_once(client: httpx.AsyncClient, acme: Acme) -> None:
    created = await invite(client, acme, "Nueva@Example.com", "viewer")

    assert created["email"] == "nueva@example.com"
    assert (created["role"], created["status"]) == ("viewer", "pending")
    assert created["link"].startswith(f"{APP_ORIGIN}/invitations/accept#")
    assert link_params(created["link"])["organization"] == acme.id

    listed = await client.get("/api/v1/invitations", headers=acme.headers(acme.admin))
    assert listed.status_code == 200
    [item] = listed.json()["items"]
    assert item["id"] == created["id"]
    assert "link" not in item  # the token is not stored, so it cannot be shown again


async def test_viewer_cannot_invite_nor_list(client: httpx.AsyncClient, acme: Acme) -> None:
    headers = acme.headers(acme.viewer)

    created = await client.post(
        "/api/v1/invitations", json={"email": "x@example.com", "role": "viewer"}, headers=headers
    )
    listed = await client.get("/api/v1/invitations", headers=headers)

    assert (created.status_code, listed.status_code) == (403, 403)


async def test_admin_cannot_invite_admins_and_nobody_invites_owners(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    as_admin = await client.post(
        "/api/v1/invitations",
        json={"email": "x@example.com", "role": "admin"},
        headers=acme.headers(acme.admin),
    )
    as_owner = await client.post(
        "/api/v1/invitations",
        json={"email": "x@example.com", "role": "owner"},
        headers=acme.headers(acme.owner),
    )

    assert as_admin.status_code == 403
    assert as_owner.status_code == 422  # not even a valid value for this endpoint


async def test_conflicts_pending_invitation_and_existing_member(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    await invite(client, acme)
    headers = acme.headers(acme.owner)

    again = await client.post(
        "/api/v1/invitations",
        json={"email": "nueva@example.com", "role": "viewer"},
        headers=headers,
    )
    member = await client.post(
        "/api/v1/invitations", json={"email": "bob@example.com", "role": "viewer"}, headers=headers
    )

    assert again.json()["error"]["code"] == "invitation_already_pending"
    assert member.json()["error"]["code"] == "already_member"


async def test_revoked_invitation_disappears_and_its_link_stops_working(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    created = await invite(client, acme)

    revoked = await client.delete(
        f"/api/v1/invitations/{created['id']}", headers=acme.headers(acme.owner)
    )

    assert revoked.status_code == 204
    listed = await client.get("/api/v1/invitations", headers=acme.headers(acme.owner))
    assert listed.json()["items"] == []
    again = await client.delete(
        f"/api/v1/invitations/{created['id']}", headers=acme.headers(acme.owner)
    )
    assert again.status_code == 404


async def test_invitations_of_another_organization_are_invisible(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    created = await invite(client, acme)
    eve = await register(client, "eve@example.com", slug="eves")
    eves_org = (await client.get("/api/v1/organizations", headers=eve.auth)).json()["items"][0]
    eve_headers = {**eve.auth, "X-Organization-Id": eves_org["id"]}

    listed = await client.get("/api/v1/invitations", headers=eve_headers)
    revoke = await client.delete(f"/api/v1/invitations/{created['id']}", headers=eve_headers)

    assert listed.json()["items"] == []
    assert revoke.status_code == 404


# --- Step 18: accept ------------------------------------------------------------------------


def accept_body(link: str) -> dict[str, str]:
    params = link_params(link)
    return {"organization_id": params["organization"], "token": params["token"]}


async def test_existing_user_accepts_and_sees_the_new_organization(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    created = await invite(client, acme, "dana@example.com", "member")
    dana = await register(client, "dana@example.com", slug="danas")

    response = await client.post(
        "/api/v1/invitations/accept", json=accept_body(created["link"]), headers=dana.auth
    )

    assert response.status_code == 200, response.text
    assert (response.json()["id"], response.json()["role"]) == (acme.id, "member")
    mine = (await client.get("/api/v1/organizations", headers=dana.auth)).json()["items"]
    assert {o["slug"] for o in mine} == {"danas", "acme"}
    inside = await client.get("/api/v1/members", headers=acme.headers(dana))
    assert inside.status_code == 200
    again = await client.post(
        "/api/v1/invitations/accept", json=accept_body(created["link"]), headers=dana.auth
    )
    assert again.status_code == 404


async def test_new_user_registers_with_the_invitation(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    created = await invite(client, acme, "dana@example.com", "viewer")

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dana@example.com",
            "password": PASSWORD,
            "invitation": accept_body(created["link"]),
        },
    )

    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    mine = await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
    assert [(o["id"], o["role"]) for o in mine.json()["items"]] == [(acme.id, "viewer")]


async def test_registering_with_someone_elses_invitation_creates_nothing(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    created = await invite(client, acme, "dana@example.com")

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "mallory@example.com",
            "password": PASSWORD,
            "invitation": accept_body(created["link"]),
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "invitation_email_mismatch"
    login = await client.post(
        "/api/v1/auth/login", json={"email": "mallory@example.com", "password": PASSWORD}
    )
    assert login.status_code == 401  # the account was rolled back with the rest


async def test_a_tampered_link_is_not_found(client: httpx.AsyncClient, acme: Acme) -> None:
    created = await invite(client, acme, "dana@example.com")
    dana = await register(client, "dana@example.com", slug="danas")
    body = accept_body(created["link"])

    wrong_token = await client.post(
        "/api/v1/invitations/accept", json={**body, "token": "x" * 43}, headers=dana.auth
    )
    danas_org = (await client.get("/api/v1/organizations", headers=dana.auth)).json()["items"][0]
    wrong_org = await client.post(
        "/api/v1/invitations/accept",
        json={**body, "organization_id": danas_org["id"]},
        headers=dana.auth,
    )

    assert (wrong_token.status_code, wrong_org.status_code) == (404, 404)


async def test_register_needs_exactly_one_of_organization_or_invitation(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    created = await invite(client, acme, "dana@example.com")
    base = {"email": "dana@example.com", "password": PASSWORD}

    neither = await client.post("/api/v1/auth/register", json=base)
    both = await client.post(
        "/api/v1/auth/register",
        json={
            **base,
            "organization_name": "Dana",
            "organization_slug": "dana",
            "invitation": accept_body(created["link"]),
        },
    )

    assert (neither.status_code, both.status_code) == (422, 422)
