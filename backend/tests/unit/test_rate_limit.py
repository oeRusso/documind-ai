"""InMemoryRateLimiter: sliding window, driven by a fake clock (seconds)."""

from datetime import timedelta

import pytest

from app.infrastructure import rate_limit
from app.infrastructure.rate_limit import InMemoryRateLimiter
from app.shared.errors import TooManyRequestsError
from app.shared.rate_limit import RateLimit

THREE_PER_MINUTE = RateLimit(3, timedelta(minutes=1))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def limiter(clock: Clock) -> InMemoryRateLimiter:
    return InMemoryRateLimiter(clock=clock)


async def test_allows_up_to_the_limit_then_says_how_long_to_wait(
    limiter: InMemoryRateLimiter, clock: Clock
) -> None:
    for _ in range(3):
        await limiter.hit("k", THREE_PER_MINUTE)
        clock.now += 10

    with pytest.raises(TooManyRequestsError) as error:
        await limiter.hit("k", THREE_PER_MINUTE)

    # The first attempt (at 1000) leaves the window at 1060; now is 1030.
    assert error.value.retry_after_seconds == 30
    assert error.value.code == "rate_limited"


async def test_the_window_slides(limiter: InMemoryRateLimiter, clock: Clock) -> None:
    for _ in range(3):
        await limiter.hit("k", THREE_PER_MINUTE)
    clock.now += 60

    await limiter.hit("k", THREE_PER_MINUTE)  # the old attempts left the window


async def test_rejected_attempts_do_not_extend_the_wait(
    limiter: InMemoryRateLimiter, clock: Clock
) -> None:
    for _ in range(3):
        await limiter.hit("k", THREE_PER_MINUTE)
    for _ in range(10):  # hammering while blocked...
        with pytest.raises(TooManyRequestsError):
            await limiter.hit("k", THREE_PER_MINUTE)
    clock.now += 60

    await limiter.hit("k", THREE_PER_MINUTE)  # ...does not keep the client blocked forever


async def test_keys_are_independent(limiter: InMemoryRateLimiter) -> None:
    for _ in range(3):
        await limiter.hit("login:ip:1.1.1.1", THREE_PER_MINUTE)

    await limiter.hit("login:ip:2.2.2.2", THREE_PER_MINUTE)


async def test_idle_keys_are_forgotten_to_bound_memory(
    limiter: InMemoryRateLimiter, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limit, "MAX_KEYS", 2)
    await limiter.hit("a", THREE_PER_MINUTE)
    await limiter.hit("b", THREE_PER_MINUTE)
    clock.now += 120

    await limiter.hit("c", THREE_PER_MINUTE)

    assert set(limiter._attempts) == {"c"}
