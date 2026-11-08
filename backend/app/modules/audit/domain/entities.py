"""Audit events: who did what, when and from where. Pure Python."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class AuditAction(StrEnum):
    """Security-relevant actions. Stored as text, so new ones need no migration."""

    USER_REGISTERED = "user.registered"
    LOGIN_SUCCEEDED = "auth.login_succeeded"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"
    REFRESH_REUSE_DETECTED = "auth.refresh_reuse_detected"
    ORGANIZATION_CREATED = "organization.created"
    MEMBER_ROLE_CHANGED = "membership.role_changed"
    MEMBER_REMOVED = "membership.removed"
    INVITATION_CREATED = "invitation.created"
    INVITATION_REVOKED = "invitation.revoked"
    INVITATION_ACCEPTED = "invitation.accepted"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_VERSION_UPLOADED = "document.version_uploaded"
    DOCUMENT_DOWNLOADED = "document.downloaded"
    DOCUMENT_DELETED = "document.deleted"
    DOCUMENT_PURGED = "document.purged"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: UUID
    action: AuditAction
    created_at: datetime
    # None when the event has no organization (login, logout) or no known user (failed login).
    organization_id: UUID | None = None
    user_id: UUID | None = None
    target: str | None = None  # what was acted on, e.g. "membership:<uuid>"
    ip: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
