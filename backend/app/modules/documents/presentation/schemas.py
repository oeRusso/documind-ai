"""JSON shapes of the documents endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.modules.documents.application.read_documents import DocumentDetail, DocumentRow
from app.modules.documents.domain.entities import (
    Document,
    DocumentStatus,
    DocumentVersion,
    DocumentWithVersion,
    FileKind,
)


class VersionRead(BaseModel):
    number: int
    filename: str
    kind: FileKind
    size_bytes: int
    page_count: int | None
    sha256: str
    uploaded_by_email: str | None
    created_at: datetime

    @classmethod
    def build(cls, version: DocumentVersion, uploaded_by_email: str | None) -> "VersionRead":
        return cls(
            number=version.number,
            filename=version.filename,
            kind=version.kind,
            size_bytes=version.size_bytes,
            page_count=version.page_count,
            sha256=version.sha256,
            uploaded_by_email=uploaded_by_email,
            created_at=version.created_at,
        )


class DocumentRead(BaseModel):
    """One row of the list: the document and its newest version."""

    id: UUID
    title: str
    status: DocumentStatus
    created_by_email: str | None
    created_at: datetime
    updated_at: datetime
    latest_version: VersionRead

    @classmethod
    def build(cls, item: DocumentWithVersion, created_by_email: str | None) -> "DocumentRead":
        return cls(
            id=item.document.id,
            title=item.document.title,
            status=item.document.status,
            created_by_email=created_by_email,
            created_at=item.document.created_at,
            updated_at=item.document.updated_at,
            latest_version=VersionRead.build(item.version, None),
        )

    @classmethod
    def from_row(cls, row: DocumentRow) -> "DocumentRead":
        return cls.build(row.item, row.created_by_email)


class DocumentDetailRead(BaseModel):
    id: UUID
    title: str
    status: DocumentStatus
    created_by_id: UUID | None
    created_by_email: str | None
    created_at: datetime
    updated_at: datetime
    versions: list[VersionRead]  # newest first

    @classmethod
    def build(cls, detail: DocumentDetail) -> "DocumentDetailRead":
        document: Document = detail.document
        return cls(
            id=document.id,
            title=document.title,
            status=document.status,
            created_by_id=document.created_by_id,
            created_by_email=detail.created_by_email,
            created_at=document.created_at,
            updated_at=document.updated_at,
            versions=[VersionRead.build(v.version, v.uploaded_by_email) for v in detail.versions],
        )
