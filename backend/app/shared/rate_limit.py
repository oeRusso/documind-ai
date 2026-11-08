"""Attempt limits (login, register, invitations), as a port.

The in-memory implementation lives in app/infrastructure/rate_limit.py. It is enough while the
API runs as a single process; with several, it would move to Valkey behind this same Protocol.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimit:
    limit: int  # attempts allowed...
    window: timedelta  # ...within this time


class RateLimiter(Protocol):
    async def hit(self, key: str, rule: RateLimit) -> None:
        """Count one attempt for `key`. Raises TooManyRequestsError when over the limit.

        Rejected attempts are not counted: whoever waits `Retry-After` can try again.
        """
        ...
