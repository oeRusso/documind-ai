"""RateLimiter kept in the API process memory (sliding window).

For each key, a list of the times of the recent attempts. An attempt is allowed when fewer
than `limit` attempts happened in the last `window`. Restarting the API resets every counter.
"""

import math
import time
from collections import deque
from collections.abc import Callable

from app.shared.errors import TooManyRequestsError
from app.shared.rate_limit import RateLimit

# Memory bound: past this many keys, the ones without recent attempts are dropped.
MAX_KEYS = 100_000


class InMemoryRateLimiter:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._attempts: dict[str, deque[float]] = {}

    async def hit(self, key: str, rule: RateLimit) -> None:
        now = self._clock()
        window = rule.window.total_seconds()
        attempts = self._attempts.setdefault(key, deque())
        while attempts and attempts[0] <= now - window:
            attempts.popleft()
        if len(attempts) >= rule.limit:
            retry_after = attempts[0] + window - now
            raise TooManyRequestsError(max(1, math.ceil(retry_after)))
        attempts.append(now)
        if len(self._attempts) > MAX_KEYS:
            self._forget_idle(now, window)

    def _forget_idle(self, now: float, window: float) -> None:
        idle = [k for k, times in self._attempts.items() if not times or times[-1] <= now - window]
        for key in idle:
            del self._attempts[key]
