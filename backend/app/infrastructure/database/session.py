"""Async engine and per-request session (one transaction per request)."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str) -> AsyncEngine:
    # Creating the engine does not connect yet: connections are opened lazily from the pool.
    return create_async_engine(url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Commits if the endpoint succeeds, rolls back if it raises.

    Register it with `Depends(get_session, scope="function")` so the commit happens
    *before* the response is sent (otherwise a failed commit would follow a 2xx).
    Stage 2 adds `SET LOCAL app.current_org` here, inside the same transaction.
    """
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session, session.begin():
        yield session
