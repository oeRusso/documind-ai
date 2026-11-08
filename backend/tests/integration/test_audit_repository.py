"""SqlAuditLogRepository against PostgreSQL, with the `app` role and RLS."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
from tests.integration.factories import create_organization, create_user


async def test_event_without_organization_can_be_written(app_session: AsyncSession) -> None:
    # A failed login: no tenant context at all. Must not need to read the row back.
    use_case = RecordAuditEvent(SqlAuditLogRepository(app_session))

    await use_case.execute(
        RecordAuditEventCommand(action=AuditAction.LOGIN_FAILED, ip="203.0.113.7")
    )


async def test_event_of_the_active_organization_is_readable(app_session: AsyncSession) -> None:
    organization = await create_organization(app_session, await create_user(app_session))

    event = await RecordAuditEvent(SqlAuditLogRepository(app_session)).execute(
        RecordAuditEventCommand(
            action=AuditAction.ORGANIZATION_CREATED,
            organization_id=organization.id,
            target=f"organization:{organization.id}",
            details={"slug": "acme"},
        )
    )

    row = (
        await app_session.execute(
            text("SELECT action, target, host(ip) AS ip, details FROM audit_logs WHERE id = :id"),
            {"id": event.id},
        )
    ).one()
    assert row.action == "organization.created"
    assert row.target == f"organization:{organization.id}"
    assert row.details == {"slug": "acme"}
    assert isinstance(event.id, UUID)
