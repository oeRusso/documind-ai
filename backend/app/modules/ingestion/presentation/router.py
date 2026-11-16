"""HTTP endpoints about the processing of a document: its state, re-running it, its chunks."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.exceptions import ErrorResponse
from app.core.pagination import Page
from app.modules.auth.presentation.dependencies import CurrentMemberDep
from app.modules.ingestion.application.jobs import (
    GetProcessingStatus,
    ListChunks,
    ReprocessDocument,
)
from app.modules.ingestion.presentation.dependencies import (
    provide_list_chunks,
    provide_processing_status,
    provide_reprocess,
)
from app.modules.ingestion.presentation.schemas import ChunkRead, ProcessingRead

router = APIRouter(prefix="/documents", tags=["processing"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
}


@router.get("/{document_id}/processing", responses=_ERRORS)
async def get_processing(
    document_id: UUID,
    member: CurrentMemberDep,
    use_case: Annotated[GetProcessingStatus, Depends(provide_processing_status)],
) -> ProcessingRead:
    """Estado del procesamiento de la versión más nueva. Consultalo cada pocos segundos.

    Si el trabajo quedó trabado (el worker se cayó), se vuelve a encolar automáticamente.
    """
    result = await use_case.execute(member, document_id)
    return ProcessingRead.build(result.job)


@router.post("/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED, responses=_ERRORS)
async def reprocess(
    document_id: UUID,
    member: CurrentMemberDep,
    use_case: Annotated[ReprocessDocument, Depends(provide_reprocess)],
) -> Response:
    """Vuelve a procesar la versión más nueva (por ejemplo, después de un error)."""
    await use_case.execute(member, document_id)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/{document_id}/chunks", responses=_ERRORS)
async def list_chunks(
    document_id: UUID,
    member: CurrentMemberDep,
    use_case: Annotated[ListChunks, Depends(provide_list_chunks)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[int | None, Query(ge=0, description="`next_cursor` anterior")] = None,
) -> Page[ChunkRead]:
    """Los fragmentos del documento, en orden de lectura, con su sección y sus páginas."""
    chunks = await use_case.execute(member, document_id, limit=limit + 1, after_position=cursor)
    has_more = len(chunks) > limit
    chunks = chunks[:limit]
    return Page(
        items=[ChunkRead.build(chunk) for chunk in chunks],
        next_cursor=str(chunks[-1].chunk.position) if has_more and chunks else None,
    )
