"""get_session: commit on success, roll back on errors, except errors with keep_changes."""

from typing import Annotated
from uuid import UUID

import asyncpg
import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
from app.shared.errors import UnauthorizedError
from app.shared.ids import new_id
from tests.db import migrator_test_url, plain_dsn

SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]


class KeptError(UnauthorizedError):
    keep_changes = True


class RolledBackError(UnauthorizedError):
    pass


@pytest.fixture
def app_with_test_route(db_app: FastAPI) -> FastAPI:
    @db_app.post("/_test/audit/{org_id}")
    async def write_then_fail(org_id: UUID, outcome: str, session: SessionDep) -> None:
        await SqlTenantContext(session).set_organization(org_id)
        await RecordAuditEvent(SqlAuditLogRepository(session)).execute(
            RecordAuditEventCommand(action=AuditAction.LOGIN_FAILED, organization_id=org_id)
        )
        if outcome == "kept":
            raise KeptError()
        if outcome == "rolled_back":
            raise RolledBackError()

    return db_app


async def stored_events(org_id: UUID) -> int:
    connection = await asyncpg.connect(plain_dsn(migrator_test_url()))
    try:
        async with connection.transaction():
            await connection.execute("SELECT set_config('app.current_org', $1, true)", str(org_id))
            count: int = await connection.fetchval("SELECT count(*) FROM audit_logs")
            return count
    finally:
        await connection.close()


@pytest.mark.parametrize(
    ("outcome", "status", "expected_rows"),
    [("ok", 200, 1), ("kept", 401, 1), ("rolled_back", 401, 0)],
)
async def test_transaction_outcome(
    app_with_test_route: FastAPI, outcome: str, status: int, expected_rows: int
) -> None:
    org_id = new_id()  # audit_logs has no foreign keys, any id works
    transport = httpx.ASGITransport(app=app_with_test_route)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/_test/audit/{org_id}", params={"outcome": outcome})

    assert response.status_code == status
    assert await stored_events(org_id) == expected_rows
