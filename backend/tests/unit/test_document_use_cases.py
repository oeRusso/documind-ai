"""Document rules with in-memory fakes: who can upload and delete, duplicates, versions, purge."""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.documents.application.delete_document import (
    DeleteDocument,
    DeleteDocumentCommand,
    PurgeDeletedDocuments,
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
from app.modules.documents.domain.entities import DocumentStatus, DocumentWithVersion, StagedUpload
from app.modules.documents.domain.errors import (
    CannotDeleteDocumentError,
    DocumentNotFoundError,
    DocumentVersionNotFoundError,
    DuplicateDocumentError,
    UnsupportedFileTypeError,
)
from app.modules.organizations.domain.errors import PermissionDeniedError
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from app.modules.users.application.get_users_by_ids import GetUsersByIds
from app.modules.users.domain.entities import User
from app.shared.ids import new_id
from tests.fakes import (
    FakeFileInspector,
    FakeTenantContext,
    InMemoryAuditLogRepository,
    InMemoryDocumentRepository,
    InMemoryPurgeQueue,
    InMemoryStorage,
    InMemoryUserRepository,
)

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
PURGE_AFTER = timedelta(days=30)


class Library:
    """One organization with one member per role, and the use cases wired to fakes."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.organization_id = new_id()
        self.documents = InMemoryDocumentRepository()
        self.storage = InMemoryStorage(tmp_path / "staging")
        self.inspector = FakeFileInspector()
        self.audit = InMemoryAuditLogRepository()
        self.queue = InMemoryPurgeQueue()
        self.users = InMemoryUserRepository()
        self.tenant = FakeTenantContext()
        self.now = NOW
        record = RecordAuditEvent(self.audit, clock=lambda: self.now)
        clock = lambda: self.now  # noqa: E731
        self.upload_uc = UploadDocument(
            self.documents, self.storage, self.inspector, record, clock=clock
        )
        self.version_uc = UploadDocumentVersion(
            self.documents, self.storage, self.inspector, record, clock=clock
        )
        get_users = GetUsersByIds(self.users)
        self.list_uc = ListDocuments(self.documents, get_users)
        self.get_uc = GetDocument(self.documents, get_users)
        self.download_uc = DownloadDocument(self.documents, self.storage, record)
        self.delete_uc = DeleteDocument(
            self.documents, self.queue, record, purge_after=PURGE_AFTER, clock=clock
        )
        self.purge_uc = PurgeDeletedDocuments(
            self.queue, self.documents, self.storage, self.tenant, record, clock=clock
        )
        self.owner = self.member(Role.OWNER, "owner@example.com")
        self.admin = self.member(Role.ADMIN, "admin@example.com")
        self.editor = self.member(Role.MEMBER, "editor@example.com")
        self.other_editor = self.member(Role.MEMBER, "otro@example.com")
        self.viewer = self.member(Role.VIEWER, "viewer@example.com")

    def member(self, role: Role, email: str, organization_id: UUID | None = None) -> Membership:
        user = User.create(id=new_id(), email=email, password_hash="h", now=NOW)
        self.users.items[user.id] = user
        return Membership.create(
            id=new_id(),
            organization_id=organization_id or self.organization_id,
            user_id=user.id,
            role=role,
            now=NOW,
        )

    def staged(self, content: bytes, filename: str = "contrato.pdf") -> StagedUpload:
        path = self.storage.staging_dir() / new_id().hex
        path.write_bytes(content)
        return StagedUpload(
            path=path,
            filename=filename,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    async def upload(
        self, actor: Membership, content: bytes = b"v1", filename: str = "contrato.pdf"
    ) -> DocumentWithVersion:
        return await self.upload_uc.execute(
            UploadDocumentCommand(actor, self.staged(content, filename))
        )

    async def delete(self, actor: Membership, document_id: UUID) -> None:
        await self.delete_uc.execute(DeleteDocumentCommand(actor, document_id))


@pytest.fixture
def lib(tmp_path: Path) -> Library:
    return Library(tmp_path)


# --- Upload ---------------------------------------------------------------------------------


async def test_member_uploads_a_pending_document(lib: Library) -> None:
    created = await lib.upload(lib.editor, b"%PDF contenido", "Contrato_Proveedor X.pdf")

    assert created.document.title == "Contrato Proveedor X"
    assert created.document.status is DocumentStatus.PENDING
    assert created.version.number == 1
    assert created.version.page_count == 3
    assert created.version.storage_key.startswith(f"{lib.organization_id}/")
    assert lib.storage.files[created.version.storage_key] == b"%PDF contenido"
    assert lib.audit.actions == ["document.uploaded"]


async def test_viewer_cannot_upload(lib: Library) -> None:
    with pytest.raises(PermissionDeniedError):
        await lib.upload(lib.viewer)

    assert lib.storage.files == {}


async def test_refused_file_saves_nothing(lib: Library) -> None:
    lib.inspector.refuse = UnsupportedFileTypeError()

    with pytest.raises(UnsupportedFileTypeError):
        await lib.upload(lib.editor)

    assert (lib.documents.documents, lib.storage.files) == ({}, {})


async def test_same_file_twice_is_a_duplicate(lib: Library) -> None:
    first = await lib.upload(lib.editor, b"mismo contenido", "a.pdf")

    with pytest.raises(DuplicateDocumentError) as error:
        await lib.upload(lib.admin, b"mismo contenido", "otro-nombre.pdf")

    assert error.value.details == [{"document_id": str(first.document.id)}]
    assert len(lib.documents.documents) == 1


async def test_same_file_in_another_organization_is_not_a_duplicate(lib: Library) -> None:
    await lib.upload(lib.editor, b"contenido")
    outsider = lib.member(Role.MEMBER, "x@otra.com", organization_id=new_id())

    await lib.upload(outsider, b"contenido")

    assert len(lib.documents.documents) == 2


# --- Versions -------------------------------------------------------------------------------


async def test_new_version_gets_the_next_number_and_is_pending_again(lib: Library) -> None:
    created = await lib.upload(lib.editor, b"v1")
    lib.now = NOW + timedelta(hours=1)

    updated = await lib.version_uc.execute(
        UploadVersionCommand(lib.other_editor, created.document.id, lib.staged(b"v2"))
    )

    assert updated.version.number == 2
    assert updated.document.updated_at == lib.now
    detail = await lib.get_uc.execute(lib.viewer, created.document.id)
    assert [(v.version.number, v.uploaded_by_email) for v in detail.versions] == [
        (2, "otro@example.com"),
        (1, "editor@example.com"),
    ]


async def test_new_version_with_bytes_already_uploaded_is_a_duplicate(lib: Library) -> None:
    created = await lib.upload(lib.editor, b"v1")

    with pytest.raises(DuplicateDocumentError):
        await lib.version_uc.execute(
            UploadVersionCommand(lib.editor, created.document.id, lib.staged(b"v1"))
        )


async def test_version_of_another_organizations_document_is_not_found(lib: Library) -> None:
    created = await lib.upload(lib.editor)
    outsider = lib.member(Role.OWNER, "x@otra.com", organization_id=new_id())

    with pytest.raises(DocumentNotFoundError):
        await lib.version_uc.execute(
            UploadVersionCommand(outsider, created.document.id, lib.staged(b"v2"))
        )


# --- Reading --------------------------------------------------------------------------------


async def test_list_is_newest_first_with_a_cursor(lib: Library) -> None:
    ids = [(await lib.upload(lib.editor, f"doc {n}".encode())).document.id for n in range(5)]

    first = await lib.list_uc.execute(lib.viewer, limit=2)
    second = await lib.list_uc.execute(lib.viewer, limit=2, before_id=first.next_before_id)
    last = await lib.list_uc.execute(lib.viewer, limit=2, before_id=second.next_before_id)

    seen = [r.item.document.id for page in (first, second, last) for r in page.rows]
    assert seen == ids[::-1]
    assert last.next_before_id is None
    assert first.rows[0].created_by_email == "editor@example.com"


async def test_download_returns_the_bytes_and_is_audited(lib: Library) -> None:
    created = await lib.upload(lib.editor, b"v1")
    await lib.version_uc.execute(
        UploadVersionCommand(lib.editor, created.document.id, lib.staged(b"v2"))
    )

    newest = await lib.download_uc.execute(DownloadDocumentCommand(lib.viewer, created.document.id))
    first = await lib.download_uc.execute(
        DownloadDocumentCommand(lib.viewer, created.document.id, version_number=1)
    )

    assert b"".join([c async for c in newest.chunks]) == b"v2"
    assert b"".join([c async for c in first.chunks]) == b"v1"
    assert lib.audit.actions[-1] == "document.downloaded"
    with pytest.raises(DocumentVersionNotFoundError):
        await lib.download_uc.execute(
            DownloadDocumentCommand(lib.viewer, created.document.id, version_number=9)
        )


async def test_another_organization_cannot_read_or_download(lib: Library) -> None:
    created = await lib.upload(lib.editor)
    outsider = lib.member(Role.OWNER, "x@otra.com", organization_id=new_id())

    with pytest.raises(DocumentNotFoundError):
        await lib.get_uc.execute(outsider, created.document.id)
    with pytest.raises(DocumentNotFoundError):
        await lib.download_uc.execute(DownloadDocumentCommand(outsider, created.document.id))
    assert (await lib.list_uc.execute(outsider)).rows == []


# --- Delete and purge -----------------------------------------------------------------------


async def test_members_delete_only_their_own_documents(lib: Library) -> None:
    mine = await lib.upload(lib.editor, b"mio")
    theirs = await lib.upload(lib.other_editor, b"suyo")

    with pytest.raises(CannotDeleteDocumentError):
        await lib.delete(lib.editor, theirs.document.id)
    await lib.delete(lib.editor, mine.document.id)

    with pytest.raises(DocumentNotFoundError):
        await lib.get_uc.execute(lib.editor, mine.document.id)


async def test_admins_delete_any_document_and_viewers_none(lib: Library) -> None:
    created = await lib.upload(lib.editor)

    with pytest.raises(PermissionDeniedError):
        await lib.delete(lib.viewer, created.document.id)
    await lib.delete(lib.admin, created.document.id)

    assert lib.audit.actions[-1] == "document.deleted"


async def test_deleted_document_can_be_uploaded_again(lib: Library) -> None:
    created = await lib.upload(lib.editor, b"contenido")
    await lib.delete(lib.editor, created.document.id)

    again = await lib.upload(lib.editor, b"contenido")

    assert again.document.id != created.document.id


async def test_files_stay_until_the_waiting_period_ends(lib: Library) -> None:
    created = await lib.upload(lib.editor, b"v1")
    await lib.version_uc.execute(
        UploadVersionCommand(lib.editor, created.document.id, lib.staged(b"v2"))
    )
    await lib.delete(lib.admin, created.document.id)

    lib.now = NOW + PURGE_AFTER - timedelta(minutes=1)
    assert await lib.purge_uc.execute() == 0
    assert len(lib.storage.files) == 2  # a backup restored now would still find its files

    lib.now = NOW + PURGE_AFTER
    assert await lib.purge_uc.execute() == 2
    assert lib.storage.files == {}
    assert lib.documents.documents == {}
    assert lib.tenant.organization_id == lib.organization_id  # it entered the organization
    assert await lib.purge_uc.execute() == 0  # nothing left, and repeating is harmless
