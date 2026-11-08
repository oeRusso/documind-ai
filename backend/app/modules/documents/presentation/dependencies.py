"""Wiring: which concrete implementation each documents use case receives."""

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request

from app.core.dependencies import SessionDep, SettingsDep
from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
from app.modules.documents.application.delete_document import DeleteDocument
from app.modules.documents.application.read_documents import (
    DownloadDocument,
    GetDocument,
    ListDocuments,
)
from app.modules.documents.application.upload_document import UploadDocument, UploadDocumentVersion
from app.modules.documents.infrastructure.file_inspector import LibmagicFileInspector
from app.modules.documents.infrastructure.sql_repository import (
    SqlDocumentRepository,
    SqlPurgeQueue,
)
from app.modules.users.application.get_users_by_ids import GetUsersByIds
from app.modules.users.infrastructure.sql_repository import SqlUserRepository
from app.shared.storage import StorageBackend


def get_storage(request: Request) -> StorageBackend:
    storage: StorageBackend = request.app.state.storage
    return storage


StorageDep = Annotated[StorageBackend, Depends(get_storage)]


def provide_upload_document(
    session: SessionDep, settings: SettingsDep, storage: StorageDep
) -> UploadDocument:
    return UploadDocument(
        SqlDocumentRepository(session),
        storage,
        LibmagicFileInspector(max_pages=settings.max_upload_pages),
        RecordAuditEvent(SqlAuditLogRepository(session)),
    )


def provide_upload_version(
    session: SessionDep, settings: SettingsDep, storage: StorageDep
) -> UploadDocumentVersion:
    return UploadDocumentVersion(
        SqlDocumentRepository(session),
        storage,
        LibmagicFileInspector(max_pages=settings.max_upload_pages),
        RecordAuditEvent(SqlAuditLogRepository(session)),
    )


def provide_list_documents(session: SessionDep) -> ListDocuments:
    return ListDocuments(SqlDocumentRepository(session), GetUsersByIds(SqlUserRepository(session)))


def provide_get_document(session: SessionDep) -> GetDocument:
    return GetDocument(SqlDocumentRepository(session), GetUsersByIds(SqlUserRepository(session)))


def provide_download_document(session: SessionDep, storage: StorageDep) -> DownloadDocument:
    return DownloadDocument(
        SqlDocumentRepository(session), storage, RecordAuditEvent(SqlAuditLogRepository(session))
    )


def provide_delete_document(session: SessionDep, settings: SettingsDep) -> DeleteDocument:
    return DeleteDocument(
        SqlDocumentRepository(session),
        SqlPurgeQueue(session),
        RecordAuditEvent(SqlAuditLogRepository(session)),
        purge_after=timedelta(days=settings.document_purge_days),
    )
