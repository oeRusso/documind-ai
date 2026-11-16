"""GET /api/v1/search: search the active organization's documents."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel

from app.ai.providers.embeddings import EmbeddingProvider
from app.core.dependencies import SessionDep
from app.core.exceptions import ErrorResponse
from app.modules.auth.presentation.dependencies import CurrentMemberDep
from app.modules.knowledge.application.search_documents import (
    MAX_LIMIT,
    MAX_QUERY_CHARS,
    SearchDocuments,
    SearchQuery,
)
from app.modules.knowledge.domain.search import SearchHit, SearchMode
from app.modules.knowledge.infrastructure.sql_search import SqlChunkSearch

router = APIRouter(prefix="/search", tags=["search"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
}


def provide_search(request: Request, session: SessionDep) -> SearchDocuments:
    embeddings: EmbeddingProvider | None = request.app.state.embeddings
    return SearchDocuments(SqlChunkSearch(session), embeddings)


class SearchHitRead(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    section: str | None
    content: str
    page_start: int | None
    page_end: int | None
    score: float
    vector_rank: int | None
    text_rank: int | None

    @classmethod
    def build(cls, hit: SearchHit) -> "SearchHitRead":
        match = hit.match
        return cls(
            chunk_id=match.chunk_id,
            document_id=match.document_id,
            document_title=match.document_title,
            section=match.section,
            content=match.content,
            page_start=match.page_start,
            page_end=match.page_end,
            score=hit.score,
            vector_rank=hit.vector_rank,
            text_rank=hit.text_rank,
        )


class SearchResponse(BaseModel):
    mode: SearchMode
    items: list[SearchHitRead]
    notes: list[str]


@router.get("", responses=_ERRORS)
async def search(
    member: CurrentMemberDep,
    use_case: Annotated[SearchDocuments, Depends(provide_search)],
    q: Annotated[str, Query(min_length=1, max_length=MAX_QUERY_CHARS, description="Qué buscar")],
    mode: SearchMode = SearchMode.HYBRID,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 10,
    document_id: Annotated[
        list[UUID] | None, Query(description="Limitar a estos documentos (se puede repetir)")
    ] = None,
) -> SearchResponse:
    """Busca en los documentos de la organización activa, por significado y por palabras.

    Cada resultado es un fragmento con su documento, sección y páginas.
    """
    result = await use_case.execute(
        SearchQuery(member, q, mode=mode, limit=limit, document_ids=document_id)
    )
    return SearchResponse(
        mode=result.mode, items=[SearchHitRead.build(h) for h in result.hits], notes=result.notes
    )
