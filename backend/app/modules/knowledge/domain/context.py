"""The context given to the model: which chunks, how many, numbered for citing (stage 7).

Small models answer better with a short context: they get lost in long ones. So:
1. Chunks are taken by relevance (best first) while they fit the token budget. The best one
   always goes, even if it is bigger than the budget (otherwise there is nothing to answer with).
2. Chunks that follow each other in a document (positions 4 and 5) are joined into one source:
   an idea split by the chunker reads whole again, and the model gets one number to cite.
3. Each source gets its number, [1], [2]..., in order of relevance (a merged source takes the
   place of its best chunk). The model cites these numbers; citations.py checks them.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.modules.knowledge.domain.search import ChunkMatch

# The chunker repeats the end of a chunk at the start of the next one (up to ~40 tokens).
_MAX_OVERLAP_CHARS = 600
_MIN_OVERLAP_CHARS = 20


def estimate_tokens(text: str) -> int:
    """Rough count of the model's tokens, on the safe side (no tokenizer needed).

    Spanish runs about 4 characters per token, and long words split in several pieces.
    """
    if not text:
        return 0
    return max(math.ceil(len(text) / 4), math.ceil(len(text.split()) * 1.3))


@dataclass(frozen=True, slots=True)
class ContextSource:
    marker: int  # the n of [n]
    document_id: UUID
    document_title: str
    section: str | None
    page_start: int | None
    page_end: int | None
    content: str
    chunk_ids: tuple[UUID, ...]


def _join(first: str, second: str) -> str:
    """Join two contiguous chunks, without repeating the text they share."""
    longest = min(len(first), len(second), _MAX_OVERLAP_CHARS)
    for size in range(longest, _MIN_OVERLAP_CHARS - 1, -1):
        if first.endswith(second[:size]):
            return first + second[size:]
    return f"{first}\n\n{second}"


def _pages(chunks: Sequence[ChunkMatch]) -> tuple[int | None, int | None]:
    starts = [c.page_start for c in chunks if c.page_start is not None]
    ends = [c.page_end for c in chunks if c.page_end is not None]
    return (min(starts) if starts else None, max(ends) if ends else None)


def build_context(matches: Sequence[ChunkMatch], *, budget_tokens: int) -> list[ContextSource]:
    """`matches` ordered best first (as the search returns them)."""
    chosen: list[ChunkMatch] = []
    used = 0
    for match in matches:
        cost = estimate_tokens(match.content)
        if chosen and used + cost > budget_tokens:
            continue  # a smaller chunk further down may still fit
        chosen.append(match)
        used += cost

    # Group runs of contiguous chunks: (document, position) -> its group.
    rank = {match.chunk_id: n for n, match in enumerate(chosen)}
    by_place = {(m.document_id, m.position): m for m in chosen}
    groups: list[list[ChunkMatch]] = []
    for match in sorted(chosen, key=lambda m: (str(m.document_id), m.position)):
        previous = by_place.get((match.document_id, match.position - 1))
        if previous is not None and groups and groups[-1][-1] is previous:
            groups[-1].append(match)
        else:
            groups.append([match])
    groups.sort(key=lambda group: min(rank[m.chunk_id] for m in group))

    sources = []
    for marker, group in enumerate(groups, start=1):
        content = group[0].content
        for following in group[1:]:
            content = _join(content, following.content)
        page_start, page_end = _pages(group)
        sources.append(
            ContextSource(
                marker=marker,
                document_id=group[0].document_id,
                document_title=group[0].document_title,
                section=group[0].section,
                page_start=page_start,
                page_end=page_end,
                content=content,
                chunk_ids=tuple(m.chunk_id for m in group),
            )
        )
    return sources
