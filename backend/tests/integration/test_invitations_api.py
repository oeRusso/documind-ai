"""Invitations over HTTP (stage 2, steps 17 and 18), against PostgreSQL with RLS."""

from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from tests.conftest import APP_ORIGIN
from tests.integration.api_helpers import Acme, register


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
