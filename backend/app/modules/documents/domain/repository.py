"""Ports the use cases need. Implementations: infrastructure/ (SQL) and tests/fakes.py."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.modules.documents.domain.entities import (
    Document,
    DocumentVersion,
    DocumentWithVersion,
    InspectedFile,
    PurgeItem,
)


class DocumentRepository(Protocol):
    """Every method works inside the active organization; deleted documents are invisible
    unless the method says otherwise."""

    async def add(self, document: Document, version: DocumentVersion) -> None:
        """Raises DuplicateDocumentError if the same SHA-256 is already live in the organization."""
        ...

    async def add_version(self, document: Document, version: DocumentVersion) -> None:
        """Saves `document` (new status/updated_at) and its new version. Same duplicate rule."""
        ...

    async def get(self, organization_id: UUID, document_id: UUID) -> Document | None: ...

    async def get_for_update(self, organization_id: UUID, document_id: UUID) -> Document | None:
        """Like get, but locks the row: two new versions at once get different numbers."""
        ...

    async def list_page(
        self, organization_id: UUID, *, limit: int, before_id: UUID | None
    ) -> list[DocumentWithVersion]:
        """Newest first. `before_id`: continue after that document (cursor pagination)."""
        ...

    async def list_versions(
        self, organization_id: UUID, document_id: UUID
    ) -> list[DocumentVersion]:
        """Newest version first."""
        ...

    async def find_live_by_sha256(self, organization_id: UUID, sha256: str) -> Document | None: ...

    async def mark_deleted(self, document: Document) -> None:
        """Saves the deleted document and marks its versions as deleted too."""
        ...

    async def remove(self, organization_id: UUID, document_id: UUID) -> None:
        """Deletes the rows for good (after the files were purged)."""
        ...


class PurgeQueue(Protocol):
    """Files waiting to be removed. Not tied to an organization's context: the purge job reads
    it first and then enters each organization (see PurgeDeletedDocuments)."""

    async def add(self, items: Sequence[PurgeItem]) -> None: ...

    async def due(self, now: datetime, limit: int) -> list[PurgeItem]: ...

    async def done(self, item_ids: Sequence[UUID]) -> None: ...


class FileInspector(Protocol):
    def inspect(self, path: Path, filename: str) -> InspectedFile:
        """Raises a domain error when the file is not acceptable (type, size, pages, password)."""
        ...
