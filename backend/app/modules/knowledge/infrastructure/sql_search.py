"""ChunkSearch with PostgreSQL: pgvector (HNSW) for meaning, full-text search for words.

The one place that reads several modules' tables in a single query (chunks, their embeddings
and the document titles): a read-only search projection, so that the organization and document
filters live inside the query and it stays fast (ADR 0008). It never writes.
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.domain.search import ChunkMatch

# How far the HNSW index keeps looking when filters (organization, documents) discard rows:
# with an iterative scan it continues instead of returning fewer than asked (pgvector 0.8).
_HNSW_SETTINGS = (
    "SELECT set_config('hnsw.iterative_scan', 'relaxed_order', true), "
    "set_config('hnsw.ef_search', '100', true)"
)

_COLUMNS = """
    c.id AS chunk_id, c.document_id, d.title AS document_title, c.section, c.content,
    c.page_start, c.page_end
"""


def _match(row: Any) -> ChunkMatch:
    return ChunkMatch(
        chunk_id=row.chunk_id,
        document_id=row.document_id,
        document_title=row.document_title,
        section=row.section,
        content=row.content,
        page_start=row.page_start,
        page_end=row.page_end,
        score=float(row.score),
    )


class SqlChunkSearch:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_vector(
        self,
        organization_id: UUID,
        vector: Sequence[float],
        *,
        model: str,
        dimension: int,
        limit: int,
        document_ids: Sequence[UUID] | None,
    ) -> list[ChunkMatch]:
        # The expression must be exactly the one of the model's index (migration 0006).
        # `dimension` comes from KNOWN_MODELS (an int), never from the user.
        distance = (
            f"(e.embedding::vector({int(dimension)}) <=> CAST(:vector AS vector({int(dimension)})))"
        )
        documents = "AND c.document_id = ANY(:documents)" if document_ids else ""
        await self._session.execute(text(_HNSW_SETTINGS))
        rows = await self._session.execute(
            text(f"""
                SELECT {_COLUMNS}, 1 - {distance} AS score
                FROM chunk_embeddings e
                JOIN document_chunks c ON c.id = e.chunk_id
                JOIN documents d ON d.id = c.document_id
                WHERE e.organization_id = :org AND e.model = :model
                  AND d.organization_id = :org AND d.deleted_at IS NULL {documents}
                ORDER BY {distance}
                LIMIT :limit
            """),  # noqa: S608 (only fixed SQL and ints are interpolated)
            {
                "org": organization_id,
                "model": model,
                "vector": "[" + ",".join(f"{v:.7g}" for v in vector) + "]",
                "limit": limit,
                "documents": list(document_ids or []),
            },
        )
        return [_match(row) for row in rows]

    async def by_text(
        self,
        organization_id: UUID,
        query: str,
        *,
        limit: int,
        document_ids: Sequence[UUID] | None,
    ) -> list[ChunkMatch]:
        # Questions are sentences: any of their words may match (OR), and the rank rewards the
        # chunks that contain more of them, closer together. Stop words ("el", "de") are dropped
        # and accents ignored by the documind_es configuration.
        documents = "AND c.document_id = ANY(:documents)" if document_ids else ""
        rows = await self._session.execute(
            text(f"""
                WITH q AS (
                    SELECT to_tsquery(
                        'documind_es',
                        replace(plainto_tsquery('documind_es', :query)::text, ' & ', ' | ')
                    ) AS query
                )
                SELECT {_COLUMNS}, ts_rank_cd(c.tsv, q.query, 32) AS score
                FROM q, document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.organization_id = :org AND d.organization_id = :org
                  AND d.deleted_at IS NULL AND c.tsv @@ q.query {documents}
                ORDER BY score DESC, c.position
                LIMIT :limit
            """),  # noqa: S608 (only fixed SQL is interpolated)
            {
                "org": organization_id,
                "query": query,
                "limit": limit,
                "documents": list(document_ids or []),
            },
        )
        return [_match(row) for row in rows]
