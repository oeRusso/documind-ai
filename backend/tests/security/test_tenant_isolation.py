"""Stage 2 criterion: a user of organization A cannot read data of B, even when the backend
forgets to filter (Row Level Security stops it). ADR 0003.

The test routes below are deliberately broken: they query the tenant tables WITHOUT any
`WHERE organization_id = ...`. They go through the same dependencies as a real endpoint
(access token, X-Organization-Id, membership check, tenant context), so the only thing left
between the organizations is PostgreSQL.
"""

from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.dependencies import SessionDep
from app.modules.auth.presentation.dependencies import CurrentMemberDep, CurrentUserDep
from app.shared.ids import new_id
from tests.integration.api_helpers import LoggedIn, register

pytestmark = pytest.mark.integration

# Every query forgets the organization filter on purpose.
_UNFILTERED = {
    "organizations": "SELECT id AS org FROM organizations",
    "memberships": "SELECT organization_id AS org FROM memberships",
    "invitations": "SELECT organization_id AS org FROM invitations",
    "audit_logs": "SELECT organization_id AS org FROM audit_logs",
    "documents": "SELECT organization_id AS org FROM documents",
    "document_versions": "SELECT organization_id AS org FROM document_versions",
    "processing_jobs": "SELECT organization_id AS org FROM processing_jobs",
    "document_chunks": "SELECT organization_id AS org FROM document_chunks",
    "chunk_embeddings": "SELECT organization_id AS org FROM chunk_embeddings",
}


@pytest.fixture
def leaky_app(db_app: FastAPI) -> FastAPI:
    async def read_everything(session: Any) -> dict[str, list[str]]:
        seen: dict[str, list[str]] = {}
        for table, sql in _UNFILTERED.items():
            rows = (await session.execute(text(sql))).scalars().all()
            seen[table] = sorted({str(org) for org in rows})
        return seen

    @db_app.get("/_test/leaky/inside-organization")
    async def inside_organization(
        member: CurrentMemberDep, session: SessionDep
    ) -> dict[str, list[str]]:
        return await read_everything(session)

    @db_app.get("/_test/leaky/no-organization-chosen")
    async def no_organization_chosen(
        user: CurrentUserDep, session: SessionDep
    ) -> dict[str, list[str]]:
        return await read_everything(session)

    @db_app.post("/_test/leaky/write-into/{target_org}")
    async def write_into(
        target_org: UUID, member: CurrentMemberDep, session: SessionDep
    ) -> dict[str, bool]:
        """Try to add yourself as owner of another organization, and to rename it."""
        refused = False
        try:
            async with session.begin_nested():
                await session.execute(
                    text(
                        "INSERT INTO memberships (id, organization_id, user_id, role) "
                        "VALUES (:id, :org, :user, 'owner')"
                    ),
                    {"id": new_id(), "org": target_org, "user": member.user_id},
                )
        except DBAPIError:
            refused = True
        renamed = await session.execute(
            text("UPDATE organizations SET name = 'hacked' WHERE id = :org"), {"org": target_org}
        )
        return {"insert_refused": refused, "update_matched_rows": bool(renamed.rowcount)}  # type: ignore[attr-defined]

    return db_app


async def org_id_of(client: httpx.AsyncClient, user: LoggedIn) -> str:
    [org] = (await client.get("/api/v1/organizations", headers=user.auth)).json()["items"]
    return str(org["id"])


@pytest.fixture
async def two_organizations(
    leaky_app: FastAPI, client: httpx.AsyncClient
) -> tuple[LoggedIn, str, LoggedIn, str]:
    ana = await register(client, email="ana@example.com", slug="acme")
    bob = await register(client, email="bob@example.com", slug="bobs")
    return ana, await org_id_of(client, ana), bob, await org_id_of(client, bob)


async def test_forgotten_filter_only_returns_the_active_organization(
    client: httpx.AsyncClient, two_organizations: tuple[LoggedIn, str, LoggedIn, str]
) -> None:
    ana, org_a, bob, org_b = two_organizations

    seen_by_ana = (
        await client.get(
            "/_test/leaky/inside-organization",
            headers={**ana.auth, "X-Organization-Id": org_a},
        )
    ).json()
    seen_by_bob = (
        await client.get(
            "/_test/leaky/inside-organization",
            headers={**bob.auth, "X-Organization-Id": org_b},
        )
    ).json()

    # B's data exists (bob sees it), yet ana's unfiltered queries never return it.
    assert seen_by_bob["organizations"] == [org_b]
    assert seen_by_bob["audit_logs"] == [org_b]
    for table in _UNFILTERED:
        assert org_b not in seen_by_ana[table], table
    assert seen_by_ana["organizations"] == [org_a]
    assert seen_by_ana["memberships"] == [org_a]
    assert seen_by_ana["audit_logs"] == [org_a]


async def test_without_choosing_an_organization_only_own_memberships_are_visible(
    client: httpx.AsyncClient, two_organizations: tuple[LoggedIn, str, LoggedIn, str]
) -> None:
    ana, org_a, _, _ = two_organizations

    seen = (await client.get("/_test/leaky/no-organization-chosen", headers=ana.auth)).json()

    assert seen == {
        "organizations": [org_a],  # the organization selector
        "memberships": [org_a],
        "invitations": [],
        "audit_logs": [],
        "documents": [],
        "document_versions": [],
        "processing_jobs": [],
        "document_chunks": [],
        "chunk_embeddings": [],
    }


async def test_asking_for_another_organization_is_404(
    client: httpx.AsyncClient, two_organizations: tuple[LoggedIn, str, LoggedIn, str]
) -> None:
    ana, _, _, org_b = two_organizations

    response = await client.get(
        "/_test/leaky/inside-organization", headers={**ana.auth, "X-Organization-Id": org_b}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "organization_not_found"


async def test_cannot_write_into_another_organization(
    client: httpx.AsyncClient, two_organizations: tuple[LoggedIn, str, LoggedIn, str]
) -> None:
    ana, org_a, bob, org_b = two_organizations

    response = await client.post(
        f"/_test/leaky/write-into/{org_b}", headers={**ana.auth, "X-Organization-Id": org_a}
    )

    assert response.json() == {"insert_refused": True, "update_matched_rows": False}
    [bobs_org] = (await client.get("/api/v1/organizations", headers=bob.auth)).json()["items"]
    assert bobs_org["name"] == "Bobs"


async def test_organization_header_is_required_inside_an_organization(
    client: httpx.AsyncClient, two_organizations: tuple[LoggedIn, str, LoggedIn, str]
) -> None:
    ana, _, _, _ = two_organizations

    response = await client.get("/_test/leaky/inside-organization", headers=ana.auth)

    assert response.status_code == 422
