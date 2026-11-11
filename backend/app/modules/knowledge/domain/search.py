"""Search over the chunks of an organization's documents (stage 6). Pure Python."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class SearchMode(StrEnum):
    HYBRID = "hybrid"  # meaning + words, fused with RRF (the default)
    VECTOR = "vector"  # meaning only (embeddings)
    TEXT = "text"  # words only (PostgreSQL full-text search)


@dataclass(frozen=True, slots=True)
class ChunkMatch:
    """One chunk found by one search method, with that method's own score."""

    chunk_id: UUID
    document_id: UUID
    document_title: str
    section: str | None
    content: str
    page_start: int | None
    page_end: int | None
    score: float  # vector: cosine similarity (1 = same meaning); text: PostgreSQL rank


@dataclass(frozen=True, slots=True)
class SearchHit:
    match: ChunkMatch
    score: float  # the score of the final ranking (RRF in hybrid mode)
    vector_rank: int | None  # position in the meaning ranking (None: not there)
    text_rank: int | None  # position in the words ranking


class ChunkSearch(Protocol):
    """Both queries filter by organization (and by documents, when given) INSIDE the query,
    never after: the limit then applies to the right rows (stage 6 task)."""

    async def by_vector(
        self,
        organization_id: UUID,
        vector: Sequence[float],
        *,
        model: str,
        dimension: int,
        limit: int,
        document_ids: Sequence[UUID] | None,
    ) -> list[ChunkMatch]: ...

    async def by_text(
        self,
        organization_id: UUID,
        query: str,
        *,
        limit: int,
        document_ids: Sequence[UUID] | None,
    ) -> list[ChunkMatch]: ...
