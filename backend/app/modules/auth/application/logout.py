"""Use case: log out. Revokes the whole session (the token family), not just one token."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.auth.domain.refresh_tokens import RefreshTokenRepository
from app.shared.ids import utc_now
from app.shared.secure_tokens import hash_token


@dataclass(frozen=True, slots=True)
class LogoutCommand:
    refresh_token: str
    ip: str | None = None


class Logout:
    def __init__(
        self,
        refresh_tokens: RefreshTokenRepository,
        record_audit_event: RecordAuditEvent,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._refresh_tokens = refresh_tokens
        self._audit = record_audit_event
        self._clock = clock

    async def execute(self, command: LogoutCommand) -> None:
        token = await self._refresh_tokens.get_by_hash_for_update(hash_token(command.refresh_token))
        if token is None:
            return  # Unknown or already gone: logging out twice is not an error.
        await self._refresh_tokens.revoke_family(token.family_id, self._clock())
        await self._audit.execute(
            RecordAuditEventCommand(
                action=AuditAction.LOGOUT,
                user_id=token.user_id,
                target=f"session:{token.family_id}",
                ip=command.ip,
            )
        )
