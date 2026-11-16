"""Reciprocal Rank Fusion (RRF): combine several rankings into one (stage 6, key piece).

The search runs twice: once by meaning (vectors) and once by words (PostgreSQL full-text).
Each gives an ordered list, but their scores are not comparable (a cosine distance of 0.3 and a
text rank of 0.08 mean nothing side by side). RRF ignores the scores and uses only positions:

    score(chunk) = sum over the rankings it appears in of  1 / (k + position)

with positions starting at 1 and k = 60 (the value from the original paper, Cormack et al. 2009).
- A chunk that is 1st in both lists gets 2/61; 1st in one and absent from the other, 1/61.
- So appearing in both lists matters more than being first in only one: agreement wins.
- k softens the gap between positions: with k = 60, 1st (1/61) and 5th (1/65) are close,
  so one list cannot impose its order alone.
"""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass

DEFAULT_K = 60


@dataclass(frozen=True, slots=True)
class Fused[T: Hashable]:
    item: T
    score: float
    # Position (1 = best) in each input ranking, None where it did not appear.
    ranks: tuple[int | None, ...]


def reciprocal_rank_fusion[T: Hashable](
    rankings: Sequence[Sequence[T]], *, k: int = DEFAULT_K, limit: int | None = None
) -> list[Fused[T]]:
    if k < 1:
        raise ValueError("k must be at least 1")
    positions: dict[T, list[int | None]] = {}
    for index, ranking in enumerate(rankings):
        for position, item in enumerate(ranking, start=1):
            slots = positions.setdefault(item, [None] * len(rankings))
            if slots[index] is None:  # a repeated item counts at its best position only
                slots[index] = position

    fused = [
        Fused(item, sum(1 / (k + p) for p in ranks if p is not None), tuple(ranks))
        for item, ranks in positions.items()
    ]
    # Ties (same score): the one with the best single position first, then input order.
    order = {item: n for n, item in enumerate(positions)}
    fused.sort(
        key=lambda f: (
            -f.score,
            min(p for p in f.ranks if p is not None),
            order[f.item],
        )
    )
    return fused[:limit] if limit is not None else fused
