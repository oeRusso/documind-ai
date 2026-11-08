"""HTTP endpoints for the documents of the active organization (X-Organization-Id header).

Another organization's document, or a deleted one, is 404 (it does not exist from here).
A role that cannot do the action gets 403.
"""

from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.dependencies import ClientIpDep, SettingsDep
from app.core.exceptions import ErrorResponse
from app.core.pagination import Page
from app.modules.auth.presentation.dependencies import CurrentMemberDep
from app.modules.documents.application.delete_document import (
    DeleteDocument,
    DeleteDocumentCommand,
)
from app.modules.documents.application.read_documents import (
    DownloadDocument,
    DownloadDocumentCommand,
    GetDocument,
    ListDocuments,
)
from app.modules.documents.application.upload_document import (
    UploadDocument,
    UploadDocumentCommand,
    UploadDocumentVersion,
    UploadVersionCommand,
)
from app.modules.documents.infrastructure.uploads import staged_upload
from app.modules.documents.presentation.dependencies import (
    StorageDep,
    provide_delete_document,
    provide_download_document,
    provide_get_document,
    provide_list_documents,
    provide_upload_document,
    provide_upload_version,
)
from app.modules.documents.presentation.schemas import DocumentDetailRead, DocumentRead

router = APIRouter(prefix="/documents", tags=["documents"])

_READ_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
}
_UPLOAD_ERRORS: dict[int | str, dict[str, Any]] = {
    **_READ_ERRORS,
    status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Archivo ya cargado"},
    status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorResponse},
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"model": ErrorResponse},
}

FileField = Annotated[UploadFile, File(description="PDF, DOCX, TXT o Markdown")]


@router.post(
    "", status_code=status.HTTP_201_CREATED, responses=_UPLOAD_ERRORS, response_model=DocumentRead
)
async def upload_document(
    file: FileField,
    member: CurrentMemberDep,
    ip: ClientIpDep,
    settings: SettingsDep,
    storage: StorageDep,
    use_case: Annotated[UploadDocument, Depends(provide_upload_document)],
) -> DocumentRead:
    """Sube un documento nuevo. Queda en estado `pending` hasta que se procese (etapa 5).

    Se valida el tipo real del archivo (no la extensión), el tamaño, las páginas y que no
    tenga contraseña. Si el mismo archivo ya está cargado, responde 409 con su id en `details`.
    """
    async with staged_upload(
        file, storage.staging_dir(), max_bytes=settings.max_upload_bytes
    ) as staged:
        created = await use_case.execute(UploadDocumentCommand(member, staged, ip))
    return DocumentRead.build(created, None)


@router.get("", responses=_READ_ERRORS)
async def list_documents(
    member: CurrentMemberDep,
    use_case: Annotated[ListDocuments, Depends(provide_list_documents)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[UUID | None, Query(description="`next_cursor` de la página anterior")] = None,
) -> Page[DocumentRead]:
    """Documentos de la organización activa, del más nuevo al más viejo."""
    page = await use_case.execute(member, limit=limit, before_id=cursor)
    return Page(
        items=[DocumentRead.from_row(row) for row in page.rows],
        next_cursor=str(page.next_before_id) if page.next_before_id else None,
    )


@router.get("/{document_id}", responses=_READ_ERRORS)
async def get_document(
    document_id: UUID,
    member: CurrentMemberDep,
    use_case: Annotated[GetDocument, Depends(provide_get_document)],
) -> DocumentDetailRead:
    """Un documento con todas sus versiones (la más nueva primero)."""
    return DocumentDetailRead.build(await use_case.execute(member, document_id))


@router.post(
    "/{document_id}/versions",
    status_code=status.HTTP_201_CREATED,
    responses=_UPLOAD_ERRORS,
    response_model=DocumentRead,
)
async def upload_version(
    document_id: UUID,
    file: FileField,
    member: CurrentMemberDep,
    ip: ClientIpDep,
    settings: SettingsDep,
    storage: StorageDep,
    use_case: Annotated[UploadDocumentVersion, Depends(provide_upload_version)],
) -> DocumentRead:
    """Sube una versión nueva de un documento (por ejemplo, el contrato corregido)."""
    async with staged_upload(
        file, storage.staging_dir(), max_bytes=settings.max_upload_bytes
    ) as staged:
        updated = await use_case.execute(UploadVersionCommand(member, document_id, staged, ip))
    return DocumentRead.build(updated, None)


@router.get(
    "/{document_id}/download",
    responses={
        **_READ_ERRORS,
        status.HTTP_200_OK: {
            "content": {"application/octet-stream": {}},
            "description": "El archivo",
        },
    },
    response_class=StreamingResponse,
)
async def download_document(
    document_id: UUID,
    member: CurrentMemberDep,
    ip: ClientIpDep,
    use_case: Annotated[DownloadDocument, Depends(provide_download_document)],
    version: Annotated[int | None, Query(ge=1, description="Sin valor: la más nueva")] = None,
) -> StreamingResponse:
    """Descarga el archivo. Es la única forma de obtenerlo: no hay URLs públicas."""
    download = await use_case.execute(
        DownloadDocumentCommand(member, document_id, version_number=version, ip=ip)
    )
    filename = download.version.filename
    ascii_name = filename.encode("ascii", "replace").decode().replace('"', "").replace("?", "_")
    return StreamingResponse(
        download.chunks,
        media_type=download.version.mime_type,
        headers={
            "Content-Length": str(download.version.size_bytes),
            # attachment: the browser saves it, never renders it inside our site.
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_READ_ERRORS)
async def delete_document(
    document_id: UUID,
    member: CurrentMemberDep,
    ip: ClientIpDep,
    use_case: Annotated[DeleteDocument, Depends(provide_delete_document)],
) -> Response:
    """Borra un documento. Admins y owners, cualquiera; un miembro, solo los que subió.

    Deja de verse al instante; los archivos se eliminan del disco días después (respaldo).
    """
    await use_case.execute(DeleteDocumentCommand(member, document_id, ip))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
