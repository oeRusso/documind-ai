"""AuditLogRepository implemented with SQLAlchemy (PostgreSQL)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.domain.entities import AuditEvent
from app.modules.audit.infrastructure.models import AuditLogModel


class SqlAuditLogRepository:
    """Does not commit: the transaction belongs to the request (see get_session)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: AuditEvent) -> None:
        self._session.add(
            AuditLogModel(
                id=event.id,
                organization_id=event.organization_id,
                user_id=event.user_id,
                action=str(event.action),
                target=event.target,
                ip=event.ip,
                details=event.details or None,
                # Both timestamps are sent, so the INSERT needs no RETURNING: the app role
                # cannot read events without an organization back (ADR 0003).
                created_at=event.created_at,
                updated_at=event.created_at,
            )
        )
        await self._session.flush()
