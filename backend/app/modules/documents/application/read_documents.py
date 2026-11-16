"""Use cases that only read: the list, one document with its versions, and downloading a file."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.documents.domain.entities import Document, DocumentVersion, DocumentWithVersion
from app.modules.documents.domain.errors import DocumentNotFoundError, DocumentVersionNotFoundError
from app.modules.documents.domain.repository import DocumentRepository
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.permissions import Permission, ensure_permission
from app.modules.users.application.get_users_by_ids import GetUsersByIds
from app.shared.storage import StorageBackend

MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class DocumentRow:
    item: DocumentWithVersion
    created_by_email: str | None


@dataclass(frozen=True, slots=True)
class DocumentPage:
    rows: list[DocumentRow]
    next_before_id: UUID | None  # becomes the `next_cursor` of the response


class ListDocuments:
    def __init__(self, documents: DocumentRepository, get_users: GetUsersByIds) -> None:
        self._documents = documents
        self._get_users = get_users

    async def execute(
        self, actor: Membership, *, limit: int = 20, before_id: UUID | None = None
    ) -> DocumentPage:
        ensure_permission(actor.role, Permission.VIEW_DOCUMENTS)
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        # One extra row tells whether there is a next page, without a COUNT(*).
        items = await self._documents.list_page(
            actor.organization_id, limit=limit + 1, before_id=before_id
        )
        has_more = len(items) > limit
        items = items[:limit]
        users = await self._get_users.execute(
            [i.document.created_by_id for i in items if i.document.created_by_id]
        )
        rows = [
            DocumentRow(i, users[uid].email if (uid := i.document.created_by_id) in users else None)
            for i in items
        ]
        return DocumentPage(rows, items[-1].document.id if has_more and items else None)


@dataclass(frozen=True, slots=True)
class VersionRow:
    version: DocumentVersion
    uploaded_by_email: str | None


@dataclass(frozen=True, slots=True)
class DocumentDetail:
    document: Document
    versions: list[VersionRow]  # newest first
    created_by_email: str | None


class GetDocument:
    def __init__(self, documents: DocumentRepository, get_users: GetUsersByIds) -> None:
        self._documents = documents
        self._get_users = get_users

    async def execute(self, actor: Membership, document_id: UUID) -> DocumentDetail:
        ensure_permission(actor.role, Permission.VIEW_DOCUMENTS)
        document = await self._documents.get(actor.organization_id, document_id)
        if document is None:
            raise DocumentNotFoundError()
        versions = await self._documents.list_versions(actor.organization_id, document_id)
        ids = {v.uploaded_by_id for v in versions if v.uploaded_by_id}
        if document.created_by_id:
            ids.add(document.created_by_id)
        users = await self._get_users.execute(list(ids))

        def email(user_id: UUID | None) -> str | None:
            return users[user_id].email if user_id in users else None

        return DocumentDetail(
            document,
            [VersionRow(v, email(v.uploaded_by_id)) for v in versions],
            email(document.created_by_id),
        )


@dataclass(frozen=True, slots=True)
class DownloadDocumentCommand:
    actor: Membership
    document_id: UUID
    version_number: int | None = None  # None: the newest
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class FileDownload:
    version: DocumentVersion
    chunks: AsyncIterator[bytes]


class StoredFileMissingError(RuntimeError):
    """The database points to a file that is not in storage. A 500: it should never happen."""


class DownloadDocument:
    """Files are only served through here: permission checked, download audited.
    There is never a public URL to a file (Part 1, §7)."""

    def __init__(
        self,
        documents: DocumentRepository,
        storage: StorageBackend,
        record_audit_event: RecordAuditEvent,
    ) -> None:
        self._documents = documents
        self._storage = storage
        self._audit = record_audit_event

    async def execute(self, command: DownloadDocumentCommand) -> FileDownload:
        actor = command.actor
        ensure_permission(actor.role, Permission.VIEW_DOCUMENTS)
        document = await self._documents.get(actor.organization_id, command.document_id)
        if document is None:
            raise DocumentNotFoundError()
        versions = await self._documents.list_versions(actor.organization_id, document.id)
        wanted = command.version_number
        version = next((v for v in versions if wanted is None or v.number == wanted), None)
        if version is None:
            raise DocumentVersionNotFoundError()
        if not await self._storage.exists(version.storage_key):
            raise StoredFileMissingError(version.storage_key)
        await self._audit.execute(
            RecordAuditEventCommand(
                action=AuditAction.DOCUMENT_DOWNLOADED,
                organization_id=actor.organization_id,
                user_id=actor.user_id,
                target=f"document:{document.id}",
                ip=command.ip,
                details={"version": version.number},
            )
        )
        return FileDownload(version, self._storage.read(version.storage_key))
