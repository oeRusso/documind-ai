"""Invitation: a link that lets one email join an organization with a given role. Pure Python.

The link carries a random token; only its SHA-256 hash is stored (like refresh tokens).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from app.modules.organizations.domain.roles import Role

INVITATION_LIFETIME = timedelta(days=7)


class InvitationStatus(StrEnum):
    PENDING = "pending"
    EXPIRED = "expired"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


@dataclass(slots=True)
class Invitation:
    id: UUID
    organization_id: UUID
    email: str
    role: Role
    token_hash: str
    invited_by_id: UUID | None
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        organization_id: UUID,
        email: str,
        role: Role,
        token_hash: str,
        invited_by_id: UUID,
        now: datetime,
    ) -> "Invitation":
        return cls(
            id=id,
            organization_id=organization_id,
            email=email,
            role=role,
            token_hash=token_hash,
            invited_by_id=invited_by_id,
            expires_at=now + INVITATION_LIFETIME,
            accepted_at=None,
            revoked_at=None,
            created_at=now,
            updated_at=now,
        )

    def status(self, now: datetime) -> InvitationStatus:
        if self.revoked_at is not None:
            return InvitationStatus.REVOKED
        if self.accepted_at is not None:
            return InvitationStatus.ACCEPTED
        if now >= self.expires_at:
            return InvitationStatus.EXPIRED
        return InvitationStatus.PENDING

    def revoke(self, now: datetime) -> None:
        self.revoked_at = now
        self.updated_at = now

    def accept(self, now: datetime) -> None:
        self.accepted_at = now
        self.updated_at = now
