from datetime import UTC, datetime
from uuid import UUID

from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction, AuditEvent

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
EVENT_ID = UUID("0192f1c4-0000-7000-8000-0000000000a1")
USER_ID = UUID("0192f1c4-0000-7000-8000-0000000000b1")


class InMemoryAuditLogRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def add(self, event: AuditEvent) -> None:
        self.events.append(event)


async def test_record_audit_event_stores_it() -> None:
    repository = InMemoryAuditLogRepository()
    use_case = RecordAuditEvent(repository, id_factory=lambda: EVENT_ID, clock=lambda: NOW)

    event = await use_case.execute(
        RecordAuditEventCommand(
            action=AuditAction.LOGIN_FAILED,
            user_id=USER_ID,
            ip="203.0.113.7",
            details={"reason": "bad_password"},
        )
    )

    assert repository.events == [event]
    assert event.id == EVENT_ID
    assert event.created_at == NOW
    assert event.organization_id is None
    assert event.action == "auth.login_failed"


async def test_details_are_copied_not_shared() -> None:
    repository = InMemoryAuditLogRepository()
    details = {"role": "admin"}

    event = await RecordAuditEvent(repository).execute(
        RecordAuditEventCommand(action=AuditAction.MEMBER_ROLE_CHANGED, details=details)
    )
    details["role"] = "owner"

    assert event.details == {"role": "admin"}
