"""Row Level Security (migration 0003, ADR 0003), tested with the real `app` role.

The queries below deliberately have NO `WHERE organization_id = ...`: they simulate a
backend that forgot to filter. Only PostgreSQL stands between the organizations.

Seed: organizations A and B. ana is owner of A, bob is member of B, carla is in both.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import asyncpg
import pytest

from app.shared.ids import new_id
from tests.db import (
    app_test_url,
    ensure_database_available,
    migrator_test_url,
    plain_dsn,
    reset_schema,
)

pytestmark = pytest.mark.integration

TENANT_TABLES = (
    "organizations",
    "memberships",
    "invitations",
    "audit_logs",
    "documents",
    "document_versions",
)


@dataclass(frozen=True)
class Seed:
    org_a: UUID
    org_b: UUID
    ana: UUID
    bob: UUID
    carla: UUID


@pytest.fixture(scope="module")
def migrated() -> None:
    ensure_database_available()
    reset_schema()


async def _set_org(connection: asyncpg.Connection, org_id: UUID) -> None:
    await connection.execute("SELECT set_config('app.current_org', $1, true)", str(org_id))


async def _seed_organization(
    connection: asyncpg.Connection, name: str, members: dict[UUID, str]
) -> UUID:
    org_id = new_id()
    async with connection.transaction():
        await _set_org(connection, org_id)
        await connection.execute(
            "INSERT INTO organizations (id, name, slug) VALUES ($1, $2, $3)", org_id, name, name
        )
        for user_id, role in members.items():
            await connection.execute(
                "INSERT INTO memberships (id, organization_id, user_id, role) "
                "VALUES ($1, $2, $3, $4)",
                new_id(),
                org_id,
                user_id,
                role,
            )
        await connection.execute(
            "INSERT INTO invitations (id, organization_id, email, role, token_hash, expires_at) "
            "VALUES ($1, $2, $3, 'member', $4, now() + interval '7 days')",
            new_id(),
            org_id,
            f"guest@{name}.com",
            org_id.hex * 2,
        )
        await connection.execute(
            "INSERT INTO audit_logs (id, organization_id, action) VALUES ($1, $2, 'test.event')",
            new_id(),
            org_id,
        )
        document_id = new_id()
        await connection.execute(
            "INSERT INTO documents (id, organization_id, title, status) "
            "VALUES ($1, $2, 'Contrato', 'pending')",
            document_id,
            org_id,
        )
        await connection.execute(
            "INSERT INTO document_versions (id, organization_id, document_id, number, "
            "storage_key, filename, sha256, kind, size_bytes) "
            "VALUES ($1, $2, $3, 1, $4, 'contrato.pdf', $5, 'pdf', 10)",
            new_id(),
            org_id,
            document_id,
            f"{org_id}/{new_id()}",
            "a" * 64,  # the same bytes in both organizations: allowed, each has its own copy
        )
    return org_id


@pytest.fixture
async def seed(migrated: None) -> AsyncIterator[Seed]:
    # Seeded as migrator, which is also subject to RLS (FORCE), so each org sets its context.
    connection = await asyncpg.connect(plain_dsn(migrator_test_url()))
    try:
        ana, bob, carla = new_id(), new_id(), new_id()
        for user_id, email in ((ana, "ana"), (bob, "bob"), (carla, "carla")):
            await connection.execute(
                "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, 'x')",
                user_id,
                f"{email}@example.com",
            )
        org_a = await _seed_organization(connection, "a", {ana: "owner", carla: "member"})
        org_b = await _seed_organization(connection, "b", {bob: "member", carla: "viewer"})
        # An event without organization, like a failed login.
        await connection.execute(
            "INSERT INTO audit_logs (id, action) VALUES ($1, 'auth.login_failed')", new_id()
        )
        yield Seed(org_a=org_a, org_b=org_b, ana=ana, bob=bob, carla=carla)
    finally:
        await connection.execute(
            "TRUNCATE organizations, memberships, invitations, audit_logs, users, "
            "documents, document_versions CASCADE"
        )
        await connection.close()


@pytest.fixture
async def app_db(seed: Seed) -> AsyncIterator[asyncpg.Connection]:
    """A connection with the API's role. Each test opens its own transactions."""
    connection = await asyncpg.connect(plain_dsn(app_test_url()))
    yield connection
    await connection.close()


async def act_as(
    connection: asyncpg.Connection, *, user: UUID | None = None, org: UUID | None = None
) -> None:
    """What the API does at the start of each request (app/infrastructure/database/tenant.py)."""
    if user is not None:
        await connection.execute("SELECT set_config('app.current_user', $1, true)", str(user))
    if org is not None:
        await _set_org(connection, org)


async def organization_ids(connection: asyncpg.Connection, table: str) -> set[UUID]:
    column = "id" if table == "organizations" else "organization_id"
    rows = await connection.fetch(f"SELECT {column} AS org FROM {table}")  # noqa: S608
    return {row["org"] for row in rows}


# --- Reading -----------------------------------------------------------------------------


async def test_without_context_every_tenant_table_looks_empty(app_db: asyncpg.Connection) -> None:
    async with app_db.transaction():
        for table in TENANT_TABLES:
            assert await app_db.fetchval(f"SELECT count(*) FROM {table}") == 0, table  # noqa: S608


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_active_organization_only_sees_its_own_rows(
    app_db: asyncpg.Connection, seed: Seed, table: str
) -> None:
    async with app_db.transaction():
        await act_as(app_db, user=seed.ana, org=seed.org_a)

        assert await organization_ids(app_db, table) == {seed.org_a}


async def test_other_organization_sees_only_its_rows_too(
    app_db: asyncpg.Connection, seed: Seed
) -> None:
    async with app_db.transaction():
        await act_as(app_db, user=seed.bob, org=seed.org_b)

        assert await organization_ids(app_db, "memberships") == {seed.org_b}
        assert await organization_ids(app_db, "invitations") == {seed.org_b}


async def test_user_sees_their_own_memberships_before_choosing_an_organization(
    app_db: asyncpg.Connection, seed: Seed
) -> None:
    # The organization selector: user known, organization not chosen yet.
    async with app_db.transaction():
        await act_as(app_db, user=seed.carla)

        assert await organization_ids(app_db, "organizations") == {seed.org_a, seed.org_b}
        members = await app_db.fetch("SELECT user_id FROM memberships")
        assert {row["user_id"] for row in members} == {seed.carla}
        assert await app_db.fetchval("SELECT count(*) FROM invitations") == 0


async def test_user_does_not_see_organizations_they_do_not_belong_to(
    app_db: asyncpg.Connection, seed: Seed
) -> None:
    async with app_db.transaction():
        await act_as(app_db, user=seed.ana)

        assert await organization_ids(app_db, "organizations") == {seed.org_a}


async def test_context_does_not_leak_into_the_next_transaction(
    app_db: asyncpg.Connection, seed: Seed
) -> None:
    async with app_db.transaction():
        await act_as(app_db, user=seed.ana, org=seed.org_a)
        assert await app_db.fetchval("SELECT count(*) FROM organizations") == 1

    # Same pooled connection, new request: the variables are now '' and must not crash.
    async with app_db.transaction():
        assert await app_db.fetchval("SELECT count(*) FROM organizations") == 0
        assert await app_db.fetchval("SELECT count(*) FROM memberships") == 0


# --- Writing -----------------------------------------------------------------------------


async def test_cannot_insert_rows_into_another_organization(
    app_db: asyncpg.Connection, seed: Seed
) -> None:
    async with app_db.transaction():
        await act_as(app_db, user=seed.ana, org=seed.org_a)

        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
            async with app_db.transaction():
                await app_db.execute(
                    "INSERT INTO memberships (id, organization_id, user_id, role) "
                    "VALUES ($1, $2, $3, 'owner')",
                    new_id(),
                    seed.org_b,
                    seed.ana,
                )

        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
            async with app_db.transaction():
                await app_db.execute(
                    "INSERT INTO invitations (id, organization_id, email, role, token_hash, "
                    "expires_at) VALUES ($1, $2, 'x@x.com', 'admin', $3, now())",
                    new_id(),
                    seed.org_b,
                    "f" * 64,
                )

        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
            async with app_db.transaction():
                await app_db.execute(
                    "INSERT INTO documents (id, organization_id, title, status) "
                    "VALUES ($1, $2, 'x', 'pending')",
                    new_id(),
                    seed.org_b,
                )


async def test_cannot_update_or_delete_rows_of_another_organization(
    app_db: asyncpg.Connection, seed: Seed
) -> None:
    async with app_db.transaction():
        await act_as(app_db, user=seed.ana, org=seed.org_a)

        # Invisible rows are simply not matched.
        assert (
            await app_db.execute(
                "UPDATE organizations SET name = 'hacked' WHERE id = $1", seed.org_b
            )
            == "UPDATE 0"
        )
        assert (
            await app_db.execute("DELETE FROM memberships WHERE organization_id = $1", seed.org_b)
            == "DELETE 0"
        )
        assert await app_db.execute("UPDATE documents SET title = 'hacked'") == "UPDATE 1"
        assert await app_db.execute("DELETE FROM document_versions") == "DELETE 1"  # only A's


async def test_cannot_move_a_row_into_another_organization(
    app_db: asyncpg.Connection, seed: Seed
) -> None:
    async with app_db.transaction():
        await act_as(app_db, user=seed.ana, org=seed.org_a)

        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
            async with app_db.transaction():
                await app_db.execute(
                    "UPDATE memberships SET organization_id = $1 WHERE user_id = $2",
                    seed.org_b,
                    seed.ana,
                )


async def test_own_memberships_elsewhere_are_read_only(
    app_db: asyncpg.Connection, seed: Seed
) -> None:
    # carla can SEE her membership in B while working in A, but not change it from A.
    async with app_db.transaction():
        await act_as(app_db, user=seed.carla, org=seed.org_a)

        result = await app_db.execute(
            "UPDATE memberships SET role = 'owner' WHERE organization_id = $1", seed.org_b
        )
        assert result == "UPDATE 0"


# --- Audit log -----------------------------------------------------------------------------


async def test_audit_log_accepts_events_of_the_active_organization_or_without_one(
    app_db: asyncpg.Connection, seed: Seed
) -> None:
    async with app_db.transaction():
        # A failed login: nobody is authenticated and there is no organization.
        await app_db.execute(
            "INSERT INTO audit_logs (id, action) VALUES ($1, 'auth.login_failed')", new_id()
        )
        await act_as(app_db, user=seed.ana, org=seed.org_a)
        await app_db.execute(
            "INSERT INTO audit_logs (id, organization_id, action) VALUES ($1, $2, 'x')",
            new_id(),
            seed.org_a,
        )

        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
            async with app_db.transaction():
                await app_db.execute(
                    "INSERT INTO audit_logs (id, organization_id, action) VALUES ($1, $2, 'x')",
                    new_id(),
                    seed.org_b,
                )


@pytest.mark.parametrize(
    "statement",
    ["UPDATE audit_logs SET action = 'erased'", "DELETE FROM audit_logs", "TRUNCATE audit_logs"],
)
async def test_audit_log_cannot_be_changed_by_the_app(
    app_db: asyncpg.Connection, seed: Seed, statement: str
) -> None:
    async with app_db.transaction():
        await act_as(app_db, user=seed.ana, org=seed.org_a)

        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="permission denied"):
            await app_db.execute(statement)


# --- Guard for future tables ---------------------------------------------------------------

# Tables that have an organization_id but no RLS, each with its reason (ADR 0006).
# Adding a table here needs a written reason; adding one without RLS and without this fails.
WITHOUT_RLS_ON_PURPOSE = {
    # Only storage keys of files to delete. The purge job reads it before entering each
    # organization; the document rows themselves are deleted under RLS.
    "document_purge_queue": "ADR 0006",
}


async def test_every_table_with_organization_id_has_forced_rls(app_db: asyncpg.Connection) -> None:
    """Stage 4+ adds business tables: forgetting RLS on one of them makes this test fail."""
    rows = await app_db.fetch(
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        WHERE c.relkind = 'r'
          AND (c.relname = 'organizations' OR EXISTS (
                SELECT 1 FROM information_schema.columns col
                WHERE col.table_schema = 'public' AND col.table_name = c.relname
                  AND col.column_name = 'organization_id'))
        """
    )

    tables = {row["relname"]: (row["relrowsecurity"], row["relforcerowsecurity"]) for row in rows}
    assert set(tables) >= set(TENANT_TABLES)
    unprotected = [name for name, flags in tables.items() if flags != (True, True)]
    assert sorted(unprotected) == sorted(WITHOUT_RLS_ON_PURPOSE)
