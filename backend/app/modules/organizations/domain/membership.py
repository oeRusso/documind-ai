"""Membership: a user's role inside one organization. Pure Python."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.organizations.domain.roles import Role


@dataclass(slots=True)
class Membership:
    id: UUID
    organization_id: UUID
    user_id: UUID
    role: Role
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls, *, id: UUID, organization_id: UUID, user_id: UUID, role: Role, now: datetime
    ) -> "Membership":
        return cls(
            id=id,
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            created_at=now,
            updated_at=now,
        )
