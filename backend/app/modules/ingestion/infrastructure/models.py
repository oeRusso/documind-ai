"""SQLAlchemy models of the ingestion module. Both tables carry organization_id and RLS (0005)."""

from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin
from app.modules.ingestion.domain.jobs import JobStatus

_STATUSES = ", ".join(f"'{s.value}'" for s in sorted(JobStatus, key=lambda s: s.value))


class ProcessingJobModel(TimestampMixin, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (CheckConstraint(f"status IN ({_STATUSES})", name="status_valid"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    # One job per version: reprocessing resets it instead of adding another.
    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pages_total: Mapped[int | None] = mapped_column(Integer)
    pages_done: Mapped[int] = mapped_column(Integer, default=0)
    ocr_pages: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)


class DocumentChunkModel(TimestampMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("version_id", "position", name="uq_document_chunks_version_id_position"),
        # Full-text search in Spanish, accents ignored ("plazos" and "informacion" find "plazo"
        # and "información"). documind_es = spanish + unaccent (migration 0006).
        Index("ix_document_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(300))
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    # Computed by PostgreSQL from section + content; the app never writes it.
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('documind_es'::regconfig, coalesce(section, '') || ' ' || content)",
            persisted=True,
        ),
    )


class ChunkEmbeddingModel(TimestampMixin, Base):
    """One vector per chunk and per model (changing the model = reindexing, old ones stay)."""

    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "model", name="uq_chunk_embeddings_chunk_id_model"),
        # One HNSW index per model: the vector column has no fixed size (models differ),
        # so each index casts it to its model's size. Queries must use the same expression.
        Index(
            "ix_chunk_embeddings_bge_m3_hnsw",
            sql_text("(embedding::vector(1024)) vector_cosine_ops"),
            postgresql_using="hnsw",
            postgresql_where=sql_text("model = 'bge-m3'"),
        ),
        Index(
            "ix_chunk_embeddings_paraphrase_multilingual_hnsw",
            sql_text("(embedding::vector(768)) vector_cosine_ops"),
            postgresql_using="hnsw",
            postgresql_where=sql_text("model = 'paraphrase-multilingual'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey("document_chunks.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(100))
    embedding: Mapped[list[float]] = mapped_column(Vector())
