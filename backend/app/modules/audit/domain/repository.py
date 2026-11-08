"""Repository interface. Insert-only on purpose: there is no update or delete."""

from typing import Protocol

from app.modules.audit.domain.entities import AuditEvent


class AuditLogRepository(Protocol):
    async def add(self, event: AuditEvent) -> None: ...
