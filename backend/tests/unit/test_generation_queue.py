"""GenerationQueue: N answers at a time, the rest wait in order and see their position."""

import asyncio

import pytest

from app.ai.concurrency import GenerationQueue, QueueFullError


async def test_within_the_slots_it_is_your_turn_at_once() -> None:
    queue = GenerationQueue(slots=2)
    async with queue.ticket() as first, queue.ticket() as second:
        assert [p async for p in queue.positions(first)] == [0]
        assert [p async for p in queue.positions(second)] == [0]
        assert queue.waiting == 0


async def test_who_arrives_later_waits_and_sees_the_position_go_down() -> None:
    queue = GenerationQueue(slots=1)
    seen: list[int] = []
    leave_first = asyncio.Event()
    leave_second = asyncio.Event()

    async def hold(release: asyncio.Event) -> None:
        async with queue.ticket() as ticket:
            async for _ in queue.positions(ticket):
                pass
            await release.wait()

    async def third() -> None:
        async with queue.ticket() as ticket:
            async for position in queue.positions(ticket):
                seen.append(position)

    first = asyncio.create_task(hold(leave_first))
    await asyncio.sleep(0)
    second = asyncio.create_task(hold(leave_second))
    await asyncio.sleep(0)
    waiter = asyncio.create_task(third())
    await asyncio.sleep(0)
    assert seen == [2]
    assert queue.waiting == 2

    leave_first.set()
    await first
    await asyncio.sleep(0)
    assert seen == [2, 1]

    leave_second.set()
    await asyncio.gather(second, waiter)
    assert seen == [2, 1, 0]
    assert queue.waiting == 0


async def test_a_ticket_is_given_back_even_if_the_answer_fails() -> None:
    queue = GenerationQueue(slots=1)
    with pytest.raises(RuntimeError):
        async with queue.ticket():
            raise RuntimeError("Ollama se cayó")
    async with queue.ticket() as ticket:
        assert queue.position(ticket) == 0


async def test_a_cancelled_waiter_leaves_the_line() -> None:
    queue = GenerationQueue(slots=1)

    async def wait_turn() -> None:
        async with queue.ticket() as ticket:
            async for _ in queue.positions(ticket):
                pass

    async with queue.ticket():
        task = asyncio.create_task(wait_turn())
        await asyncio.sleep(0)
        assert queue.waiting == 1
        task.cancel()  # the user closed the page
        with pytest.raises(asyncio.CancelledError):
            await task
        assert queue.waiting == 0


async def test_a_full_line_rejects_new_questions() -> None:
    queue = GenerationQueue(slots=1, max_waiting=1)
    async with queue.ticket(), queue.ticket():
        with pytest.raises(QueueFullError):
            async with queue.ticket():
                pass


def test_at_least_one_slot() -> None:
    with pytest.raises(ValueError, match="slots"):
        GenerationQueue(slots=0)
