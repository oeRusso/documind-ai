"""Helpers for tests that need PostgreSQL.

The test database is `<main database>_test`, created by infrastructure/scripts/db-init.
If it is not reachable, tests are skipped locally; with REQUIRE_DB=1 (CI) they fail instead.
"""

import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def to_test_database_url(url: str) -> str:
    parsed = make_url(url)
    return parsed.set(database=f"{parsed.database}_test").render_as_string(hide_password=False)


def app_test_url() -> str:
    return to_test_database_url(str(get_settings().database_url))


def migrator_test_url() -> str:
    return to_test_database_url(str(get_settings().database_migration_url))


def plain_dsn(url: str) -> str:
    """asyncpg wants `postgresql://`, without SQLAlchemy's `+asyncpg` driver suffix."""
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def run_in_thread(func: Callable[[], None]) -> None:
    """Run blocking code that calls asyncio.run() away from pytest-asyncio's event loop."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(func).result()


def ensure_database_available() -> None:
    async def ping() -> None:
        connection = await asyncpg.connect(plain_dsn(migrator_test_url()), timeout=3)
        await connection.close()

    try:
        run_in_thread(lambda: asyncio.run(ping()))
    except Exception as exc:
        reason = f"PostgreSQL test database not available ({type(exc).__name__}: {exc})"
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(reason)
        pytest.skip(f"{reason}. Start it with: podman compose up -d db")


def reset_schema() -> None:
    """downgrade base + upgrade head: a clean schema, and proof that migrations are reversible."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["url"] = migrator_test_url()
    config.attributes["skip_logging_config"] = True

    def run() -> None:
        command.downgrade(config, "base")
        command.upgrade(config, "head")

    # Alembic's async env.py calls asyncio.run() itself.
    run_in_thread(run)
