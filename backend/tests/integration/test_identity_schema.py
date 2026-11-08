"""Constraints of the identity tables (migration 0002) and model/migration drift.

Runs as `migrator`, inside a transaction that is rolled back at the end. Each failing
statement runs in its own savepoint (`async with connection.transaction()`), so one
expected error does not abort the rest of the test.
"""

from collections.abc import AsyncIterator
from uuid import UUID

import asyncpg
import pytest
from alembic import command
from alembic.config import Config

from app.shared.ids import new_id
from tests.db import BACKEND_DIR, migrator_test_url, plain_dsn, run_in_thread

pytestmark = pytest.mark.integration


@pytest.fixture
async def connection(migrated_database: None) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(plain_dsn(migrator_test_url()))
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


async def set_context(connection: asyncpg.Connection, org_id: UUID, user_id: UUID) -> None:
    # Tables use FORCE ROW LEVEL SECURITY (ADR 0003): even migrator needs the context.
    await connection.execute(
        "SELECT set_config('app.current_org', $1, true), set_config('app.current_user', $2, true)",
        str(org_id),
        str(user_id),
    )


async def add_organization(connection: asyncpg.Connection, slug: str = "acme") -> UUID:
    org_id = new_id()
    # RLS (migration 0003) only accepts rows of the active organization, even for migrator.
    await connection.execute("SELECT set_config('app.current_org', $1, true)", str(org_id))
    await connection.execute(
        "INSERT INTO organizations (id, name, slug) VALUES ($1, $2, $3)", org_id, slug, slug
    )
    return org_id


async def add_user(connection: asyncpg.Connection, email: str = "ana@example.com") -> UUID:
    user_id = new_id()
    await connection.execute(
        "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, 'hash')", user_id, email
    )
    return user_id


async def add_membership(
    connection: asyncpg.Connection, org_id: UUID, user_id: UUID, role: str = "member"
) -> None:
    await connection.execute(
        "INSERT INTO memberships (id, organization_id, user_id, role) VALUES ($1, $2, $3, $4)",
        new_id(),
        org_id,
        user_id,
        role,
    )


async def add_invitation(
    connection: asyncpg.Connection, org_id: UUID, email: str, role: str = "member"
) -> UUID:
    invitation_id = new_id()
    await connection.execute(
        "INSERT INTO invitations (id, organization_id, email, role, token_hash, expires_at) "
        "VALUES ($1, $2, $3, $4, $5, now() + interval '7 days')",
        invitation_id,
        org_id,
        email,
        role,
        invitation_id.hex * 2,  # any unique 64-char string
    )
    return invitation_id


async def test_user_email_must_be_lowercase(connection: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.CheckViolationError):
        async with connection.transaction():
            await add_user(connection, "Ana@Example.com")


async def test_user_email_is_unique(connection: asyncpg.Connection) -> None:
    await add_user(connection, "ana@example.com")
    with pytest.raises(asyncpg.UniqueViolationError):
        async with connection.transaction():
            await add_user(connection, "ana@example.com")


async def test_new_user_is_active_by_default(connection: asyncpg.Connection) -> None:
    user_id = await add_user(connection)
    assert await connection.fetchval("SELECT is_active FROM users WHERE id = $1", user_id) is True


async def test_membership_role_must_be_known(connection: asyncpg.Connection) -> None:
    org_id, user_id = await add_organization(connection), await add_user(connection)
    await set_context(connection, org_id, user_id)
    with pytest.raises(asyncpg.CheckViolationError):
        async with connection.transaction():
            await add_membership(connection, org_id, user_id, role="superadmin")


async def test_user_has_one_membership_per_organization(connection: asyncpg.Connection) -> None:
    org_id, user_id = await add_organization(connection), await add_user(connection)
    await set_context(connection, org_id, user_id)
    await add_membership(connection, org_id, user_id, role="owner")
    with pytest.raises(asyncpg.UniqueViolationError):
        async with connection.transaction():
            await add_membership(connection, org_id, user_id, role="viewer")


async def test_nobody_can_be_invited_as_owner(connection: asyncpg.Connection) -> None:
    org_id, user_id = await add_organization(connection), await add_user(connection)
    await set_context(connection, org_id, user_id)
    with pytest.raises(asyncpg.CheckViolationError):
        async with connection.transaction():
            await add_invitation(connection, org_id, "bob@example.com", role="owner")


async def test_only_one_open_invitation_per_email(connection: asyncpg.Connection) -> None:
    org_id, user_id = await add_organization(connection), await add_user(connection)
    await set_context(connection, org_id, user_id)
    first = await add_invitation(connection, org_id, "bob@example.com")

    with pytest.raises(asyncpg.UniqueViolationError):
        async with connection.transaction():
            await add_invitation(connection, org_id, "bob@example.com")

    # Once the first one is revoked, a new invitation is allowed.
    await connection.execute("UPDATE invitations SET revoked_at = now() WHERE id = $1", first)
    await add_invitation(connection, org_id, "bob@example.com")


async def test_deleting_an_organization_removes_its_memberships(
    connection: asyncpg.Connection,
) -> None:
    org_id, user_id = await add_organization(connection), await add_user(connection)
    await set_context(connection, org_id, user_id)
    await add_membership(connection, org_id, user_id)

    await connection.execute("DELETE FROM organizations WHERE id = $1", org_id)

    count = await connection.fetchval(
        "SELECT count(*) FROM memberships WHERE organization_id = $1", org_id
    )
    assert count == 0


def test_models_match_migrations(migrated_database: None) -> None:
    """Fails if a model changed without a migration (same as `alembic check`)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["url"] = migrator_test_url()
    config.attributes["skip_logging_config"] = True
    run_in_thread(lambda: command.check(config))
