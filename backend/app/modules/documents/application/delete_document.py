"""Use cases: delete a document (logical delete) and purge the files later (physical delete).

Why two steps: the database is backed up every day. If a file vanished the moment its document
was deleted, restoring yesterday's backup would bring back rows that point to missing files.
So deleting only hides the document and schedules its files for removal after
DOCUMENT_PURGE_DAYS; a periodic job (`python -m app.jobs.purge_documents`) removes them.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.modules.audit.application.record_audit_event import (
    RecordAuditEvent,
    RecordAuditEventCommand,
)
from app.modules.audit.domain.entities import AuditAction
from app.modules.documents.domain.entities import PurgeItem
from app.modules.documents.domain.errors import CannotDeleteDocumentError, DocumentNotFoundError
from app.modules.documents.domain.repository import DocumentRepository, PurgeQueue
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.permissions import (
    Permission,
    ensure_permission,
    has_permission,
)
from app.shared.ids import new_id, utc_now
from app.shared.storage import StorageBackend
from app.shared.tenancy import TenantContext


@dataclass(frozen=True, slots=True)
class DeleteDocumentCommand:
    actor: Membership
    document_id: UUID
    ip: str | None = None


class DeleteDocument:
    """Admins and owners delete any document; members only the ones they uploaded."""

    def __init__(
        self,
        documents: DocumentRepository,
        purge_queue: PurgeQueue,
        record_audit_event: RecordAuditEvent,
        *,
        purge_after: timedelta,
        id_factory: Callable[[], UUID] = new_id,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._documents = documents
        self._purge_queue = purge_queue
        self._audit = record_audit_event
        self._purge_after = purge_after
        self._id_factory = id_factory
        self._clock = clock

    async def execute(self, command: DeleteDocumentCommand) -> None:
        actor = command.actor
        ensure_permission(actor.role, Permission.UPLOAD_DOCUMENTS)  # viewers: 403 right away
        document = await self._documents.get_for_update(actor.organization_id, command.document_id)
        if document is None:
            raise DocumentNotFoundError()
        is_author = document.created_by_id == actor.user_id
        if not is_author and not has_permission(actor.role, Permission.DELETE_ANY_DOCUMENT):
            raise CannotDeleteDocumentError()

        now = self._clock()
        versions = await self._documents.list_versions(actor.organization_id, document.id)
        await self._documents.mark_deleted(document.delete(by=actor.user_id, now=now))
        await self._purge_queue.add(
            [
                PurgeItem(
                    id=self._id_factory(),
                    organization_id=document.organization_id,
                    document_id=document.id,
                    storage_key=version.storage_key,
                    purge_after=now + self._purge_after,
                )
                for version in versions
            ]
        )
        await self._audit.execute(
            RecordAuditEventCommand(
                action=AuditAction.DOCUMENT_DELETED,
                organization_id=actor.organization_id,
                user_id=actor.user_id,
                target=f"document:{document.id}",
                ip=command.ip,
                details={"title": document.title, "versions": len(versions)},
            )
        )


class PurgeDeletedDocuments:
    """Removes the files whose waiting period ended, and then the document rows.

    Runs outside any request: it reads the queue (no organization context needed), then
    enters each document's organization to delete its rows, as Row Level Security requires.
    Safe to repeat: deleting a missing file or row is not an error.
    """

    def __init__(
        self,
        purge_queue: PurgeQueue,
        documents: DocumentRepository,
        storage: StorageBackend,
        tenant: TenantContext,
        record_audit_event: RecordAuditEvent,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._queue = purge_queue
        self._documents = documents
        self._storage = storage
        self._tenant = tenant
        self._audit = record_audit_event
        self._clock = clock

    async def execute(self, *, batch_size: int = 200) -> int:
        """Purges up to `batch_size` files. Returns how many were removed."""
        items = await self._queue.due(self._clock(), batch_size)
        for item in items:
            await self._storage.delete(item.storage_key)
        for organization_id, document_id in dict.fromkeys(
            (i.organization_id, i.document_id) for i in items
        ):
            await self._tenant.set_organization(organization_id)
            await self._documents.remove(organization_id, document_id)
            await self._audit.execute(
                RecordAuditEventCommand(
                    action=AuditAction.DOCUMENT_PURGED,
                    organization_id=organization_id,
                    target=f"document:{document_id}",
                )
            )
        await self._queue.done([item.id for item in items])
        return len(items)
