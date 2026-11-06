"""Use case: exchange a refresh token for a new session (rotation) and detect reuse (ADR 0004).

Each refresh token works exactly once. Using it returns a brand-new refresh token of the same
family and marks the old one as replaced. If a replaced token ever shows up again, two parties
hold copies of it (the user and possibly a thief), and we cannot tell which one is legitimate:
the whole family is revoked and everyone using it has to log in again.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.auth.application.issue_session import IssuedSession, IssueSession
from app.modules.auth.domain.errors import InvalidTokenError, RefreshTokenReuseError
from app.modules.auth.domain.refresh_tokens import RefreshTokenRepository
from app.modules.users.application.get_user import GetActiveUser
from app.shared.ids import utc_now
from app.shared.secure_tokens import hash_token


@dataclass(frozen=True, slots=True)
class RefreshSessionCommand:
    refresh_token: str
    ip: str | None = None


class RefreshSession:
    def __init__(
        self,
        refresh_tokens: RefreshTokenRepository,
        issue_session: IssueSession,
        get_active_user: GetActiveUser,
        record_audit_event: RecordAuditEvent,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._refresh_tokens = refresh_tokens
        self._issue_session = issue_session
        self._get_active_user = get_active_user
        self._audit = record_audit_event
        self._clock = clock

    async def execute(self, command: RefreshSessionCommand) -> IssuedSession:
        now = self._clock()
        token = await self._refresh_tokens.get_by_hash_for_update(hash_token(command.refresh_token))
        if token is None:
            raise InvalidTokenError()

        if token.replaced_by_id is not None:
            # Reuse: this token was already exchanged once.
            revoked = await self._refresh_tokens.revoke_family(token.family_id, now)
            await self._audit.execute(
                RecordAuditEventCommand(
                    action=AuditAction.REFRESH_REUSE_DETECTED,
                    user_id=token.user_id,
                    target=f"session:{token.family_id}",
                    ip=command.ip,
                    details={"revoked_tokens": revoked},
                )
            )
            raise RefreshTokenReuseError()  # keep_changes: the revocation is committed

        if token.revoked_at is not None or token.is_expired(now):
            raise InvalidTokenError()

        if await self._get_active_user.execute(token.user_id) is None:
            # Account deleted or disabled since the login.
            await self._refresh_tokens.revoke_family(token.family_id, now)
            raise InvalidTokenError()

        session = await self._issue_session.continue_family(token.user_id, token.family_id)
        await self._refresh_tokens.mark_replaced(token.id, session.refresh_token_id, now)
        return session
