"""Document repositories implemented with SQLAlchemy. They never commit: the transaction
belongs to the request (see get_session). Every query also filters by organization_id; Row
Level Security is the second layer, not the only one (CLAUDE.md)."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.domain.entities import (
    Document,
    DocumentStatus,
    DocumentVersion,
    DocumentWithVersion,
    FileKind,
    PurgeItem,
)
from app.modules.documents.domain.errors import DuplicateDocumentError
from app.modules.documents.infrastructure.models import (
    DocumentModel,
    DocumentPurgeModel,
    DocumentVersionModel,
)

_SHA256_INDEX = "uq_document_versions_organization_id_sha256_live"


def _document(model: DocumentModel) -> Document:
    return Document(
        id=model.id,
        organization_id=model.organization_id,
        title=model.title,
        status=DocumentStatus(model.status),
        created_by_id=model.created_by_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        deleted_by_id=model.deleted_by_id,
    )


def _version(model: DocumentVersionModel) -> DocumentVersion:
    return DocumentVersion(
        id=model.id,
        organization_id=model.organization_id,
        document_id=model.document_id,
        number=model.number,
        storage_key=model.storage_key,
        filename=model.filename,
        sha256=model.sha256,
        kind=FileKind(model.kind),
        size_bytes=model.size_bytes,
        page_count=model.page_count,
        uploaded_by_id=model.uploaded_by_id,
        created_at=model.created_at,
    )


def _version_model(version: DocumentVersion) -> DocumentVersionModel:
    return DocumentVersionModel(
        id=version.id,
        organization_id=version.organization_id,
        document_id=version.document_id,
        number=version.number,
        storage_key=version.storage_key,
        filename=version.filename,
        sha256=version.sha256,
        kind=version.kind.value,
        size_bytes=version.size_bytes,
        page_count=version.page_count,
        uploaded_by_id=version.uploaded_by_id,
        created_at=version.created_at,
        updated_at=version.created_at,
    )


class SqlDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _flush_or_duplicate(self, organization_id: UUID, sha256: str) -> None:
        try:
            async with self._session.begin_nested():  # a savepoint: the request can go on
                await self._session.flush()
        except IntegrityError as exc:
            if _SHA256_INDEX not in str(exc.orig):
                raise
            existing = await self.find_live_by_sha256(organization_id, sha256)
            if existing is None:  # deleted in between: extremely unlikely, report as conflict
                raise
            raise DuplicateDocumentError(existing.id, existing.title) from exc

    async def add(self, document: Document, version: DocumentVersion) -> None:
        self._session.add(
            DocumentModel(
                id=document.id,
                organization_id=document.organization_id,
                title=document.title,
                status=document.status.value,
                created_by_id=document.created_by_id,
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
        )
        self._session.add(_version_model(version))
        await self._flush_or_duplicate(document.organization_id, version.sha256)

    async def add_version(self, document: Document, version: DocumentVersion) -> None:
        await self._session.execute(
            update(DocumentModel)
            .where(
                DocumentModel.organization_id == document.organization_id,
                DocumentModel.id == document.id,
            )
            .values(status=document.status.value, updated_at=document.updated_at)
        )
        self._session.add(_version_model(version))
        await self._flush_or_duplicate(document.organization_id, version.sha256)

    async def get(self, organization_id: UUID, document_id: UUID) -> Document | None:
        model = await self._session.scalar(
            select(DocumentModel).where(
                DocumentModel.organization_id == organization_id,
                DocumentModel.id == document_id,
                DocumentModel.deleted_at.is_(None),
            )
        )
        return _document(model) if model else None

    async def get_for_update(self, organization_id: UUID, document_id: UUID) -> Document | None:
        model = await self._session.scalar(
            select(DocumentModel)
            .where(
                DocumentModel.organization_id == organization_id,
                DocumentModel.id == document_id,
                DocumentModel.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return _document(model) if model else None

    async def list_page(
        self, organization_id: UUID, *, limit: int, before_id: UUID | None
    ) -> list[DocumentWithVersion]:
        # The newest version of each document: DISTINCT ON keeps the first row per document.
        latest = (
            select(DocumentVersionModel)
            .where(DocumentVersionModel.organization_id == organization_id)
            .ext(distinct_on(DocumentVersionModel.document_id))
            .order_by(DocumentVersionModel.document_id, DocumentVersionModel.number.desc())
            .subquery()
        )
        query = (
            select(DocumentModel, DocumentVersionModel)
            .join(latest, latest.c.document_id == DocumentModel.id)
            .join(DocumentVersionModel, DocumentVersionModel.id == latest.c.id)
            .where(DocumentModel.organization_id == organization_id)
            .where(DocumentModel.deleted_at.is_(None))
            .order_by(DocumentModel.id.desc())  # UUID v7: newest first
            .limit(limit)
        )
        if before_id is not None:
            query = query.where(DocumentModel.id < before_id)
        rows = (await self._session.execute(query)).all()
        return [DocumentWithVersion(_document(doc), _version(ver)) for doc, ver in rows]

    async def list_versions(
        self, organization_id: UUID, document_id: UUID
    ) -> list[DocumentVersion]:
        models = await self._session.scalars(
            select(DocumentVersionModel)
            .where(
                DocumentVersionModel.organization_id == organization_id,
                DocumentVersionModel.document_id == document_id,
            )
            .order_by(DocumentVersionModel.number.desc())
        )
        return [_version(model) for model in models]

    async def find_live_by_sha256(self, organization_id: UUID, sha256: str) -> Document | None:
        model = await self._session.scalar(
            select(DocumentModel)
            .join(DocumentVersionModel, DocumentVersionModel.document_id == DocumentModel.id)
            .where(
                DocumentVersionModel.organization_id == organization_id,
                DocumentVersionModel.sha256 == sha256,
                DocumentVersionModel.deleted_at.is_(None),
            )
            .limit(1)
        )
        return _document(model) if model else None

    async def mark_deleted(self, document: Document) -> None:
        await self._session.execute(
            update(DocumentModel)
            .where(
                DocumentModel.organization_id == document.organization_id,
                DocumentModel.id == document.id,
            )
            .values(
                deleted_at=document.deleted_at,
                deleted_by_id=document.deleted_by_id,
                updated_at=document.updated_at,
            )
        )
        await self._session.execute(
            update(DocumentVersionModel)
            .where(
                DocumentVersionModel.organization_id == document.organization_id,
                DocumentVersionModel.document_id == document.id,
            )
            .values(deleted_at=document.deleted_at, updated_at=document.updated_at)
        )

    async def remove(self, organization_id: UUID, document_id: UUID) -> None:
        # The versions go with it (ON DELETE CASCADE).
        await self._session.execute(
            delete(DocumentModel).where(
                DocumentModel.organization_id == organization_id,
                DocumentModel.id == document_id,
            )
        )


class SqlPurgeQueue:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, items: Sequence[PurgeItem]) -> None:
        for item in items:
            self._session.add(
                DocumentPurgeModel(
                    id=item.id,
                    organization_id=item.organization_id,
                    document_id=item.document_id,
                    storage_key=item.storage_key,
                    purge_after=item.purge_after,
                )
            )
        await self._session.flush()

    async def due(self, now: datetime, limit: int) -> list[PurgeItem]:
        models = await self._session.scalars(
            select(DocumentPurgeModel)
            .where(DocumentPurgeModel.purge_after <= now)
            .order_by(DocumentPurgeModel.purge_after)
            .limit(limit)
            # Two purge runs at once never take the same rows.
            .with_for_update(skip_locked=True)
        )
        return [
            PurgeItem(
                id=m.id,
                organization_id=m.organization_id,
                document_id=m.document_id,
                storage_key=m.storage_key,
                purge_after=m.purge_after,
            )
            for m in models
        ]

    async def done(self, item_ids: Sequence[UUID]) -> None:
        if item_ids:
            await self._session.execute(
                delete(DocumentPurgeModel).where(DocumentPurgeModel.id.in_(item_ids))
            )
