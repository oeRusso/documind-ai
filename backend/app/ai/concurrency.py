"""A line for answer generation: at most N answers at a time, the rest wait their turn (stage 7).

On a CPU-only VPS, two answers at once already take all the cores: a third one would make the
three slower, and ten could exhaust the shared RAM. So generation goes through a line with
`slots` places (LLM_MAX_CONCURRENCY). Whoever is beyond them waits and learns its position, so
the web can show "hay 2 preguntas antes que la tuya". If the line is too long, new questions
are rejected (429) instead of piling up forever.

It lives in memory: enough while the API runs as one process (as with the rate limiter). With
several processes it would move to Valkey behind the same methods.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.shared.errors import TooManyRequestsError


class QueueFullError(TooManyRequestsError):
    code = "chat_queue_full"
    message = "Hay muchas preguntas en espera. Probá de nuevo en un momento"

    def __init__(self) -> None:
        super().__init__(retry_after_seconds=30)


class Ticket:
    """A place in the line. Compared by identity: two tickets are never equal."""


class GenerationQueue:
    def __init__(self, slots: int, *, max_waiting: int = 20) -> None:
        if slots < 1:
            raise ValueError("slots must be at least 1")
        self._slots = slots
        self._max_waiting = max_waiting
        # Arrival order. The first `slots` tickets are generating; the rest are waiting.
        self._line: list[Ticket] = []
        # Set (and replaced by a new one) each time the line changes: waiters wake up and look.
        self._changed = asyncio.Event()

    @property
    def waiting(self) -> int:
        return max(0, len(self._line) - self._slots)

    def position(self, ticket: Ticket) -> int:
        """0 = your turn; 1 = next one; 2 = one more before you..."""
        return max(0, self._line.index(ticket) - self._slots + 1)

    @asynccontextmanager
    async def ticket(self) -> AsyncIterator[Ticket]:
        """Take a place in the line; it is given back when the `async with` block ends,
        whatever happens inside (an answer that finished, failed or was abandoned)."""
        if len(self._line) >= self._slots and self.waiting >= self._max_waiting:
            raise QueueFullError()
        ticket = Ticket()
        self._line.append(ticket)
        try:
            yield ticket
        finally:
            # No await here: leaving must work even while the task is being cancelled.
            self._line.remove(ticket)
            self._notify()

    async def positions(self, ticket: Ticket) -> AsyncIterator[int]:
        """Yields the position each time it changes, ending with 0 (your turn)."""
        last: int | None = None
        while True:
            changed = self._changed  # taken before looking, so no change is missed
            position = self.position(ticket)
            if position != last:
                last = position
                yield position
            if position == 0:
                return
            await changed.wait()

    def _notify(self) -> None:
        self._changed.set()
        self._changed = asyncio.Event()
