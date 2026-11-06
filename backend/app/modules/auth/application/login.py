"""Use case: log in with email and password."""

from dataclasses import dataclass

from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.auth.application.issue_session import IssuedSession, IssueSession
from app.modules.auth.domain.errors import InvalidCredentialsError
from app.modules.users.application.verify_credentials import VerifyCredentials

# Enough to investigate an attack without storing whatever huge string was sent.
_MAX_LOGGED_EMAIL = 254


@dataclass(frozen=True, slots=True)
class LoginCommand:
    email: str
    password: str
    ip: str | None = None


class Login:
    def __init__(
        self,
        verify_credentials: VerifyCredentials,
        issue_session: IssueSession,
        record_audit_event: RecordAuditEvent,
    ) -> None:
        self._verify_credentials = verify_credentials
        self._issue_session = issue_session
        self._audit = record_audit_event

    async def execute(self, command: LoginCommand) -> IssuedSession:
        user = await self._verify_credentials.execute(command.email, command.password)
        if user is None:
            await self._audit.execute(
                RecordAuditEventCommand(
                    action=AuditAction.LOGIN_FAILED,
                    ip=command.ip,
                    details={"email": command.email.strip().lower()[:_MAX_LOGGED_EMAIL]},
                )
            )
            # keep_changes: the audit event above is committed even though this is an error.
            raise InvalidCredentialsError()

        await self._audit.execute(
            RecordAuditEventCommand(
                action=AuditAction.LOGIN_SUCCEEDED, user_id=user.id, ip=command.ip
            )
        )
        return await self._issue_session.start(user.id)
