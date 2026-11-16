"""Use cases: upload a new document, and upload a new version of an existing one.

Order of the checks (cheapest and least revealing first):
1. The role may upload at all -> 403 (a viewer).
2. (new version) The document exists in this organization -> 404, also for another org's id.
3. The file is what it claims and within limits -> 413/415/422 (FileInspector).
4. The same bytes are not already here -> 409 with the existing document's id.
Then the rows are written, the file is moved to its final place, its processing is scheduled
(the worker starts after the request commits) and the event is audited.
If anything fails, the request's transaction rolls back and the staged file is discarded.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.documents.domain.entities import (
    Document,
    DocumentVersion,
    DocumentWithVersion,
    InspectedFile,
    StagedUpload,
    title_from_filename,
)
from app.modules.documents.domain.errors import DocumentNotFoundError, DuplicateDocumentError
from app.modules.documents.domain.repository import (
    DocumentRepository,
    FileInspector,
    ProcessingScheduler,
)
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.permissions import Permission, ensure_permission
from app.shared.ids import new_id, utc_now
from app.shared.storage import StorageBackend, storage_key


@dataclass(frozen=True, slots=True)
class UploadDocumentCommand:
    actor: Membership
    file: StagedUpload
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class UploadVersionCommand:
    actor: Membership
    document_id: UUID
    file: StagedUpload
    ip: str | None = None


class _Uploads:
    def __init__(
        self,
        documents: DocumentRepository,
        storage: StorageBackend,
        inspector: FileInspector,
        record_audit_event: RecordAuditEvent,
        scheduler: ProcessingScheduler,
        *,
        id_factory: Callable[[], UUID] = new_id,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._documents = documents
        self._storage = storage
        self._inspector = inspector
        self._audit = record_audit_event
        self._scheduler = scheduler
        self._id_factory = id_factory
        self._clock = clock

    async def _inspect_and_check_duplicate(
        self, actor: Membership, file: StagedUpload
    ) -> InspectedFile:
        # libmagic and PyMuPDF are blocking (disk + CPU): run them off the event loop.
        inspected = await asyncio.to_thread(self._inspector.inspect, file.path, file.filename)
        existing = await self._documents.find_live_by_sha256(actor.organization_id, file.sha256)
        if existing is not None:
            raise DuplicateDocumentError(existing.id, existing.title)
        return inspected

    def _new_version(
        self,
        document: Document,
        number: int,
        file: StagedUpload,
        inspected: InspectedFile,
        actor: Membership,
        now: datetime,
    ) -> DocumentVersion:
        return DocumentVersion(
            id=self._id_factory(),
            organization_id=document.organization_id,
            document_id=document.id,
            number=number,
            # A fresh random id, not the version id: nothing about the file is guessable from it.
            storage_key=storage_key(document.organization_id, self._id_factory()),
            filename=file.filename,
            sha256=file.sha256,
            kind=inspected.kind,
            size_bytes=file.size_bytes,
            page_count=inspected.page_count,
            uploaded_by_id=actor.user_id,
            created_at=now,
        )

    async def _audit_upload(
        self, action: AuditAction, actor: Membership, version: DocumentVersion, ip: str | None
    ) -> None:
        await self._audit.execute(
            RecordAuditEventCommand(
                action=action,
                organization_id=actor.organization_id,
                user_id=actor.user_id,
                target=f"document:{version.document_id}",
                ip=ip,
                details={
                    "version": version.number,
                    "filename": version.filename,
                    "size_bytes": version.size_bytes,
                    "sha256": version.sha256,
                },
            )
        )


class UploadDocument(_Uploads):
    async def execute(self, command: UploadDocumentCommand) -> DocumentWithVersion:
        actor, file = command.actor, command.file
        ensure_permission(actor.role, Permission.UPLOAD_DOCUMENTS)
        inspected = await self._inspect_and_check_duplicate(actor, file)

        now = self._clock()
        document = Document.create(
            id=self._id_factory(),
            organization_id=actor.organization_id,
            title=title_from_filename(file.filename),
            created_by_id=actor.user_id,
            now=now,
        )
        version = self._new_version(document, 1, file, inspected, actor, now)
        await self._documents.add(document, version)
        await self._storage.save(version.storage_key, file.path)
        await self._scheduler.schedule(actor.organization_id, document.id, version.id)
        await self._audit_upload(AuditAction.DOCUMENT_UPLOADED, actor, version, command.ip)
        return DocumentWithVersion(document, version)


class UploadDocumentVersion(_Uploads):
    async def execute(self, command: UploadVersionCommand) -> DocumentWithVersion:
        actor, file = command.actor, command.file
        ensure_permission(actor.role, Permission.UPLOAD_DOCUMENTS)
        # Locked until the request ends: two versions at once get numbers 2 and 3, not 2 and 2.
        document = await self._documents.get_for_update(actor.organization_id, command.document_id)
        if document is None:
            raise DocumentNotFoundError()
        inspected = await self._inspect_and_check_duplicate(actor, file)

        now = self._clock()
        versions = await self._documents.list_versions(actor.organization_id, document.id)
        number = max((v.number for v in versions), default=0) + 1
        document = document.with_new_version(now)
        version = self._new_version(document, number, file, inspected, actor, now)
        await self._documents.add_version(document, version)
        await self._storage.save(version.storage_key, file.path)
        await self._scheduler.schedule(actor.organization_id, document.id, version.id)
        await self._audit_upload(AuditAction.DOCUMENT_VERSION_UPLOADED, actor, version, command.ip)
        return DocumentWithVersion(document, version)
