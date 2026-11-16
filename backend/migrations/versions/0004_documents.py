"""Documents, their versions and the purge queue (stage 4), with Row Level Security.

documents and document_versions carry organization_id and get the same tenant_isolation policy
as invitations (ADR 0003). document_purge_queue does not: it holds only storage keys of files to
delete, and the purge job reads it before entering each organization.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = ("documents", "document_versions")


def upgrade() -> None:
    op.create_table(
        "document_purge_queue",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(length=80), nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_purge_queue")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_document_purge_queue_storage_key")),
    )
    op.create_index(
        op.f("ix_document_purge_queue_purge_after"),
        "document_purge_queue",
        ["purge_after"],
        unique=False,
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('failed', 'pending', 'processing', 'ready')",
            name=op.f("ck_documents_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_documents_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by_id"],
            ["users.id"],
            name=op.f("fk_documents_deleted_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_documents_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index(
        op.f("ix_documents_organization_id"), "documents", ["organization_id"], unique=False
    )
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=80), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "kind IN ('docx', 'md', 'pdf', 'txt')", name=op.f("ck_document_versions_kind_valid")
        ),
        sa.CheckConstraint("number >= 1", name=op.f("ck_document_versions_number_positive")),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_document_versions_size_positive")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_versions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_document_versions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name=op.f("fk_document_versions_uploaded_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_versions")),
        sa.UniqueConstraint(
            "document_id", "number", name="uq_document_versions_document_id_number"
        ),
        sa.UniqueConstraint("storage_key", name=op.f("uq_document_versions_storage_key")),
    )
    op.create_index(
        op.f("ix_document_versions_document_id"), "document_versions", ["document_id"], unique=False
    )
    op.create_index(
        "uq_document_versions_organization_id_sha256_live",
        "document_versions",
        ["organization_id", "sha256"],
        unique=True,
        postgresql_where="deleted_at IS NULL",
    )

    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (organization_id = current_org_id())
            WITH CHECK (organization_id = current_org_id())
        """)


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
    op.drop_index(
        "uq_document_versions_organization_id_sha256_live",
        table_name="document_versions",
        postgresql_where="deleted_at IS NULL",
    )
    op.drop_index(op.f("ix_document_versions_document_id"), table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index(op.f("ix_documents_organization_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_document_purge_queue_purge_after"), table_name="document_purge_queue")
    op.drop_table("document_purge_queue")
