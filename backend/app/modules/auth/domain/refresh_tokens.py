"""Refresh tokens (ADR 0004): rotating, revocable, grouped in families. Pure Python."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(slots=True)
class RefreshToken:
    id: UUID
    user_id: UUID
    # Every token descending from one login shares the family; reuse revokes all of them.
    family_id: UUID
    token_hash: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None
    # Set when this token was exchanged for a new one. Seeing it again means reuse.
    replaced_by_id: UUID | None = None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


class RefreshTokenRepository(Protocol):
    async def add(self, token: RefreshToken) -> None: ...

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        """Read and lock the row until the transaction ends (SELECT ... FOR UPDATE).

        Two simultaneous refreshes with the same token are handled one after the other,
        so the token can never be exchanged twice.
        """
        ...

    async def mark_replaced(self, token_id: UUID, replaced_by_id: UUID, now: datetime) -> None: ...

    async def revoke_family(self, family_id: UUID, now: datetime) -> int:
        """Revoke every still-valid token of the family. Returns how many were revoked."""
        ...
