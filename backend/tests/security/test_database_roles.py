"""The `app` role is the base of stage 2's Row Level Security: it must stay weak."""

from collections.abc import AsyncIterator

import asyncpg
import pytest

from tests.db import app_test_url, ensure_database_available, plain_dsn, reset_schema

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def migrated() -> None:
    ensure_database_available()
    reset_schema()


@pytest.fixture
async def app_connection(migrated: None) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(plain_dsn(app_test_url()))
    yield connection
    await connection.close()


async def test_app_role_is_not_superuser_and_cannot_bypass_rls(
    app_connection: asyncpg.Connection,
) -> None:
    row = await app_connection.fetchrow(
        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
        "FROM pg_roles WHERE rolname = current_user"
    )

    assert row is not None
    assert dict(row) == {
        "rolsuper": False,
        "rolbypassrls": False,
        "rolcreaterole": False,
        "rolcreatedb": False,
    }


async def test_app_role_cannot_change_the_schema(app_connection: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_connection.execute("CREATE TABLE intruder (id int)")

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_connection.execute("DROP TABLE organizations")


async def test_app_role_does_not_own_business_tables(app_connection: asyncpg.Connection) -> None:
    owner = await app_connection.fetchval(
        "SELECT tableowner FROM pg_tables WHERE tablename = 'organizations'"
    )

    assert owner == "migrator"
