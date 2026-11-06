"""Use case: write an audit event. Other modules call this, never the table directly."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.modules.audit.domain.entities import AuditAction, AuditEvent
from app.modules.audit.domain.repository import AuditLogRepository
from app.shared.ids import new_id, utc_now


@dataclass(frozen=True, slots=True)
class RecordAuditEventCommand:
    action: AuditAction
    organization_id: UUID | None = None
    user_id: UUID | None = None
    target: str | None = None
    ip: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class RecordAuditEvent:
    def __init__(
        self,
        repository: AuditLogRepository,
        *,
        id_factory: Callable[[], UUID] = new_id,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._clock = clock

    async def execute(self, command: RecordAuditEventCommand) -> AuditEvent:
        event = AuditEvent(
            id=self._id_factory(),
            action=command.action,
            created_at=self._clock(),
            organization_id=command.organization_id,
            user_id=command.user_id,
            target=command.target,
            ip=command.ip,
            details=dict(command.details),
        )
        await self._repository.add(event)
        return event
