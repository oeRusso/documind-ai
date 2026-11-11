"""Use case: search an organization's documents by meaning, by words, or both (stage 6).

Hybrid search (the default) runs both and fuses them with Reciprocal Rank Fusion
(app/ai/retrieval/fusion.py): words catch exact terms ("artículo 245", "ART", a law number),
meaning catches paraphrases ("me echaron" -> "despido"). Each side brings `CANDIDATES` results;
the fusion keeps the best `limit`.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from app.ai.providers.embeddings import EmbeddingProvider
from app.ai.retrieval.fusion import reciprocal_rank_fusion
from app.modules.knowledge.domain.search import ChunkMatch, ChunkSearch, SearchHit, SearchMode
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.permissions import Permission, ensure_permission
from app.shared.errors import ValidationError

CANDIDATES = 30
MAX_LIMIT = 50
MAX_QUERY_CHARS = 500


class EmptyQueryError(ValidationError):
    code = "empty_query"
    message = "Escribí qué querés buscar"


@dataclass(frozen=True, slots=True)
class SearchQuery:
    actor: Membership
    text: str
    mode: SearchMode = SearchMode.HYBRID
    limit: int = 10
    document_ids: Sequence[UUID] | None = None


@dataclass(frozen=True, slots=True)
class SearchResult:
    hits: list[SearchHit]
    # The mode really used: without an embedding model, hybrid and vector fall back to words.
    mode: SearchMode
    notes: list[str] = field(default_factory=list)


class SearchDocuments:
    def __init__(self, search: ChunkSearch, embeddings: EmbeddingProvider | None) -> None:
        self._search = search
        self._embeddings = embeddings

    async def execute(self, query: SearchQuery) -> SearchResult:
        ensure_permission(query.actor.role, Permission.VIEW_DOCUMENTS)
        text = " ".join(query.text.split())[:MAX_QUERY_CHARS]
        if not text:
            raise EmptyQueryError()
        limit = max(1, min(query.limit, MAX_LIMIT))
        org = query.actor.organization_id
        mode = query.mode
        notes = []
        if mode is not SearchMode.TEXT and self._embeddings is None:
            mode = SearchMode.TEXT
            notes.append("Búsqueda por significado no disponible: se buscó por palabras.")

        by_vector: list[ChunkMatch] = []
        by_text: list[ChunkMatch] = []
        if mode in (SearchMode.VECTOR, SearchMode.HYBRID) and self._embeddings is not None:
            model = self._embeddings.model
            by_vector = await self._search.by_vector(
                org,
                await self._embeddings.embed_query(text),
                model=model.name,
                dimension=model.dimension,
                limit=CANDIDATES if mode is SearchMode.HYBRID else limit,
                document_ids=query.document_ids,
            )
        if mode in (SearchMode.TEXT, SearchMode.HYBRID):
            by_text = await self._search.by_text(
                org,
                text,
                limit=CANDIDATES if mode is SearchMode.HYBRID else limit,
                document_ids=query.document_ids,
            )

        if mode is SearchMode.VECTOR:
            hits = [SearchHit(m, m.score, n, None) for n, m in enumerate(by_vector, start=1)]
        elif mode is SearchMode.TEXT:
            hits = [SearchHit(m, m.score, None, n) for n, m in enumerate(by_text, start=1)]
        else:
            matches = {m.chunk_id: m for m in [*by_text, *by_vector]}
            fused = reciprocal_rank_fusion(
                [[m.chunk_id for m in by_vector], [m.chunk_id for m in by_text]], limit=limit
            )
            hits = [SearchHit(matches[f.item], f.score, f.ranks[0], f.ranks[1]) for f in fused]
        return SearchResult(hits[:limit], mode, notes)
