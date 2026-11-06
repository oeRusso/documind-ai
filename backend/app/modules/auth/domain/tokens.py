"""Access tokens as seen by the application (ADR 0004). No JWT library here."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AccessToken:
    value: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: UUID
    token_id: UUID
    expires_at: datetime


class AccessTokenCodec(Protocol):
    def issue(self, user_id: UUID) -> AccessToken: ...

    def read(self, token: str) -> AccessTokenClaims:
        """Validate signature, type and expiry. Raises InvalidTokenError on any problem."""
        ...
