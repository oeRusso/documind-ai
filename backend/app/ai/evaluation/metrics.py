"""Retrieval metrics (stage 6). Pure functions over "which results were relevant".

- recall@k: of the questions, how many found a relevant result among the first k.
  "Did the answer make it into what the LLM will read?"
- MRR (mean reciprocal rank): average of 1/position of the first relevant result
  (1st -> 1, 2nd -> 0.5, 5th -> 0.2, not found -> 0). Rewards putting it at the top.
"""

from collections.abc import Sequence


def first_relevant_rank(relevant: Sequence[bool]) -> int | None:
    """Position (1 = first) of the first relevant result, None if there is none."""
    for position, is_relevant in enumerate(relevant, start=1):
        if is_relevant:
            return position
    return None


def recall_at_k(ranks: Sequence[int | None], k: int) -> float:
    if not ranks:
        return 0.0
    return sum(1 for rank in ranks if rank is not None and rank <= k) / len(ranks)


def mean_reciprocal_rank(ranks: Sequence[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(1 / rank for rank in ranks if rank is not None) / len(ranks)
