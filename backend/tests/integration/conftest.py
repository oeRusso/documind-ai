from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.infrastructure.database.models import Base
from app.main import create_app
from tests.conftest import TEST_JWT_SECRET
from tests.db import app_test_url, ensure_database_available, migrator_test_url, reset_schema

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[None]:
    ensure_database_available()
    reset_schema()
    yield


@pytest.fixture(scope="session")
def db_settings(migrated_database: None) -> Settings:
    # The API connects with the restricted `app` role, exactly like in production.
    return Settings(
        app_env="test",
        log_format="console",
        database_url=app_test_url(),
        database_migration_url=migrator_test_url(),
        jwt_secret=TEST_JWT_SECRET,
    )


async def truncate_all_tables() -> None:
    """Empty every table between tests.

    Runs as `migrator` with TRUNCATE on purpose: with Row Level Security, a DELETE as `app`
    without tenant context would match no rows and silently leave data behind.
    """
    engine = create_async_engine(migrator_test_url(), poolclass=NullPool)
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} CASCADE"))
    await engine.dispose()


@pytest.fixture
async def db_app(db_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(db_settings)
    yield app
    await app.state.engine.dispose()
    await truncate_all_tables()


@pytest.fixture
async def client(db_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=db_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def app_session(db_settings: Settings) -> AsyncIterator[AsyncSession]:
    """A session with the API's `app` role, inside a transaction that is rolled back at the end.

    Use it to test SQL repositories exactly as the API runs them (RLS included).
    """
    engine = create_async_engine(str(db_settings.database_url), poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            # A database error inside the test may have rolled it back already.
            if transaction.is_active:
                await transaction.rollback()
    await engine.dispose()
