"""Shared fixtures.

Unit tests never touch a real database: they build the app against an unreachable URL.
Integration/security tests use the `documind_test` database (see tests/db.py).
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app

# Port 1 on localhost: connections are refused immediately.
UNREACHABLE_DB_URL = "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/nowhere"


@pytest.fixture
def offline_settings() -> Settings:
    return Settings(
        app_env="test",
        log_format="console",
        database_url=UNREACHABLE_DB_URL,
        database_migration_url=UNREACHABLE_DB_URL,
    )


@pytest.fixture
def offline_app(offline_settings: Settings) -> FastAPI:
    return create_app(offline_settings)


@pytest.fixture
async def offline_client(offline_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    # raise_app_exceptions=False: let the app turn exceptions into 500 responses, like in prod.
    transport = httpx.ASGITransport(app=offline_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
