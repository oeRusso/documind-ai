"""Documents and their versions. Pure Python: no FastAPI, no SQLAlchemy.

A `Document` is what people see in the list ("Contrato proveedor X"). Each file uploaded for it
is a `DocumentVersion`: the first upload is version 1, a corrected file is version 2, and so on.
The newest version is the one that gets processed and searched (stage 5 onwards).
"""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePath
from uuid import UUID

TITLE_MAX_LENGTH = 255
FILENAME_MAX_LENGTH = 255


class DocumentStatus(StrEnum):
    """Processing state. Stage 4 only creates `pending`; the pipeline (stage 5) moves it on."""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class FileKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TEXT = "txt"
    MARKDOWN = "md"

    @property
    def mime_type(self) -> str:
        return _MIME_TYPES[self]


_MIME_TYPES = {
    FileKind.PDF: "application/pdf",
    FileKind.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    FileKind.TEXT: "text/plain; charset=utf-8",
    FileKind.MARKDOWN: "text/markdown; charset=utf-8",
}

# The extension must agree with what the bytes say (see InspectedFile).
EXTENSIONS: dict[str, FileKind] = {
    ".pdf": FileKind.PDF,
    ".docx": FileKind.DOCX,
    ".txt": FileKind.TEXT,
    ".md": FileKind.MARKDOWN,
    ".markdown": FileKind.MARKDOWN,
}


def clean_filename(filename: str | None) -> str:
    """Only the last part of the name the browser sent, without control characters.

    It is shown in the UI and used in the download's Content-Disposition; it is NEVER used as a
    path on disk (files are stored under random names).
    """
    name = PurePath((filename or "").replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:FILENAME_MAX_LENGTH] or "documento"


def title_from_filename(filename: str) -> str:
    stem = PurePath(filename).stem.replace("_", " ").strip()
    return (stem or filename)[:TITLE_MAX_LENGTH]


@dataclass(frozen=True, slots=True)
class StagedUpload:
    """A received file, already on local disk, not yet validated nor saved for good."""

    path: Path
    filename: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class InspectedFile:
    """What the file really is, according to its bytes."""

    kind: FileKind
    page_count: int | None  # PDFs always; DOCX when the file says it; text files never


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    id: UUID
    organization_id: UUID
    document_id: UUID
    number: int
    storage_key: str
    filename: str
    sha256: str
    kind: FileKind
    size_bytes: int
    page_count: int | None
    uploaded_by_id: UUID | None
    created_at: datetime

    @property
    def mime_type(self) -> str:
        return self.kind.mime_type


@dataclass(frozen=True, slots=True)
class Document:
    id: UUID
    organization_id: UUID
    title: str
    status: DocumentStatus
    created_by_id: UUID | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_by_id: UUID | None = None

    @classmethod
    def create(
        cls, *, id: UUID, organization_id: UUID, title: str, created_by_id: UUID, now: datetime
    ) -> "Document":
        return cls(
            id=id,
            organization_id=organization_id,
            title=title[:TITLE_MAX_LENGTH],
            status=DocumentStatus.PENDING,
            created_by_id=created_by_id,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def with_new_version(self, now: datetime) -> "Document":
        """A new file has to be processed again."""
        return replace(self, status=DocumentStatus.PENDING, updated_at=now)

    def delete(self, *, by: UUID, now: datetime) -> "Document":
        return replace(self, deleted_at=now, deleted_by_id=by, updated_at=now)


@dataclass(frozen=True, slots=True)
class DocumentWithVersion:
    """A document and its newest version: one row of the list."""

    document: Document
    version: DocumentVersion


@dataclass(frozen=True, slots=True)
class PurgeItem:
    """A file of a deleted document, to be removed from storage after `purge_after`."""

    id: UUID
    organization_id: UUID
    document_id: UUID
    storage_key: str
    purge_after: datetime
