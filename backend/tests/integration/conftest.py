from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import Settings
from app.main import create_app
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
    )


@pytest.fixture
async def db_app(db_settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(db_settings)
    yield app
    async with app.state.engine.begin() as connection:
        await connection.execute(text("DELETE FROM organizations"))
    await app.state.engine.dispose()


@pytest.fixture
async def client(db_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=db_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
