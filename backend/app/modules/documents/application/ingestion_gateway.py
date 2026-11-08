"""What the documents module offers the ingestion pipeline (its DocumentGateway port).

Ingestion never reads the documents tables itself: it asks through this class.
"""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from app.modules.documents.domain.entities import DocumentStatus
from app.modules.documents.domain.repository import DocumentRepository
from app.modules.ingestion.domain.ports import DocumentRef, VersionToProcess
from app.shared.ids import utc_now


class DocumentsForIngestion:
    def __init__(
        self, documents: DocumentRepository, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._documents = documents
        self._clock = clock

    async def find(self, organization_id: UUID, document_id: UUID) -> DocumentRef | None:
        document = await self._documents.get(organization_id, document_id)
        if document is None:
            return None
        versions = await self._documents.list_versions(organization_id, document_id)
        return DocumentRef(document.id, document.created_by_id, versions[0].id)

    async def version_to_process(
        self, organization_id: UUID, version_id: UUID
    ) -> VersionToProcess | None:
        version = await self._documents.get_version(organization_id, version_id)
        if version is None:
            return None
        document = await self._documents.get(organization_id, version.document_id)
        if document is None:  # deleted after the job was queued
            return None
        versions = await self._documents.list_versions(organization_id, document.id)
        newest = max(v.number for v in versions)
        return VersionToProcess(
            organization_id=organization_id,
            document_id=document.id,
            version_id=version.id,
            storage_key=version.storage_key,
            kind=version.kind,
            is_latest=version.number == newest,
        )

    async def set_status(
        self, organization_id: UUID, document_id: UUID, status: DocumentStatus
    ) -> None:
        await self._documents.set_status(organization_id, document_id, status, self._clock())
