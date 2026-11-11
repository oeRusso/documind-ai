"""Search (stage 6): embeddings per chunk and model, Spanish full-text search without accents.

- unaccent + text search configuration `documind_es` (spanish stemming, accents ignored);
  document_chunks.tsv is recomputed with it.
- chunk_embeddings: one vector per chunk and model, RLS, one HNSW index per known model.
- processing_jobs gets the `embedding` state.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = "'chunking', 'embedding', 'extracting', 'failed', 'ocr', 'pending', 'ready'"
OLD_STATUSES = "'chunking', 'extracting', 'failed', 'ocr', 'pending', 'ready'"
# name in the database -> vector size (must match app/ai/providers/embeddings.py KNOWN_MODELS)
MODELS = {"bge-m3": 1024, "paraphrase-multilingual": 768}


def _tsv(config: str) -> None:
    op.drop_index("ix_document_chunks_tsv", table_name="document_chunks")
    op.drop_column("document_chunks", "tsv")
    op.execute(f"""
        ALTER TABLE document_chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS
        (to_tsvector('{config}'::regconfig, coalesce(section, '') || ' ' || content)) STORED
    """)
    op.create_index("ix_document_chunks_tsv", "document_chunks", ["tsv"], postgresql_using="gin")


def upgrade() -> None:
    # unaccent is a "trusted" extension: the database owner (migrator) may create it.
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE TEXT SEARCH CONFIGURATION documind_es (COPY = spanish)")
    op.execute(
        "ALTER TEXT SEARCH CONFIGURATION documind_es "
        "ALTER MAPPING FOR hword, hword_part, word WITH unaccent, spanish_stem"
    )
    _tsv("documind_es")

    op.drop_constraint(op.f("ck_processing_jobs_status_valid"), "processing_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_processing_jobs_status_valid"), "processing_jobs", f"status IN ({STATUSES})"
    )

    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_chunk_embeddings_chunk_id_document_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_chunk_embeddings_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_chunk_embeddings_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunk_embeddings")),
        sa.UniqueConstraint("chunk_id", "model", name="uq_chunk_embeddings_chunk_id_model"),
    )
    op.create_index(op.f("ix_chunk_embeddings_document_id"), "chunk_embeddings", ["document_id"])
    op.create_index(
        op.f("ix_chunk_embeddings_organization_id"), "chunk_embeddings", ["organization_id"]
    )
    for model, size in MODELS.items():
        name = f"ix_chunk_embeddings_{model.replace('-', '_')}_hnsw"
        op.execute(
            f"CREATE INDEX {name} ON chunk_embeddings USING hnsw "
            f"((embedding::vector({size})) vector_cosine_ops) WHERE model = '{model}'"
        )

    op.execute("ALTER TABLE chunk_embeddings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE chunk_embeddings FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON chunk_embeddings
        USING (organization_id = current_org_id())
        WITH CHECK (organization_id = current_org_id())
    """)


def downgrade() -> None:
    op.execute("DROP POLICY tenant_isolation ON chunk_embeddings")
    op.drop_table("chunk_embeddings")
    op.execute("UPDATE processing_jobs SET status = 'chunking' WHERE status = 'embedding'")
    op.drop_constraint(op.f("ck_processing_jobs_status_valid"), "processing_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_processing_jobs_status_valid"), "processing_jobs", f"status IN ({OLD_STATUSES})"
    )
    _tsv("spanish")
    op.execute("DROP TEXT SEARCH CONFIGURATION documind_es")
