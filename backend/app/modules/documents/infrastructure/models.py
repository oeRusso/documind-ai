"""SQLAlchemy models of the documents module. Only map columns: no business logic here.

`documents` and `document_versions` are business tables: they carry `organization_id` and Row
Level Security (migration 0004). `document_purge_queue` is not: it only holds opaque storage keys
of files to delete, and the purge job has to read it before entering any organization.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin
from app.modules.documents.domain.entities import DocumentStatus, FileKind


def _in_list(column: str, values: list[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in sorted(values))
    return f"{column} IN ({quoted})"


class DocumentModel(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(_in_list("status", [s.value for s in DocumentStatus]), name="status_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class DocumentVersionModel(TimestampMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "number", name="uq_document_versions_document_id_number"),
        CheckConstraint(_in_list("kind", [k.value for k in FileKind]), name="kind_valid"),
        CheckConstraint("number >= 1", name="number_positive"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        # The same bytes can be live only once per organization (duplicates, even under a race).
        Index(
            "uq_document_versions_organization_id_sha256_live",
            "organization_id",
            "sha256",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(8))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentPurgeModel(TimestampMixin, Base):
    __tablename__ = "document_purge_queue"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # Plain ids, no foreign keys: the rows they point to are deleted by the purge itself.
    organization_id: Mapped[UUID] = mapped_column(Uuid)
    document_id: Mapped[UUID] = mapped_column(Uuid)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
