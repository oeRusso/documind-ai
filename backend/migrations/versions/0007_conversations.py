"""Conversations (stage 8): conversations, messages and citations, with RLS.

The citations that stage 7 only sent over SSE and logged are stored here, one row per [n] used.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = ("conversations", "messages", "citations")


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("document_ids", postgresql.ARRAY(sa.Uuid()), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_conversations_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_conversations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index("ix_conversations_owner", "conversations", ["organization_id", "user_id", "id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("no_evidence", sa.Boolean(), nullable=True),
        sa.Column("feedback", sa.String(length=16), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("role IN ('assistant', 'user')", name=op.f("ck_messages_role_valid")),
        sa.CheckConstraint(
            "status IN ('complete', 'failed', 'stopped', 'streaming')",
            name=op.f("ck_messages_status_valid"),
        ),
        sa.CheckConstraint(
            "feedback IS NULL OR feedback IN ('helpful', 'not_helpful')",
            name=op.f("ck_messages_feedback_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_messages_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index("ix_messages_conversation_id_id", "messages", ["conversation_id", "id"])
    op.create_index(
        "ix_messages_not_helpful",
        "messages",
        ["organization_id", "id"],
        postgresql_where=sa.text("feedback = 'not_helpful'"),
    )

    op.create_table(
        "citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("marker", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("document_title", sa.String(length=255), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("chunk_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("marker >= 1", name=op.f("ck_citations_marker_positive")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_citations_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_citations_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_citations_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_citations")),
    )
    op.create_index(op.f("ix_citations_document_id"), "citations", ["document_id"])
    op.create_index(op.f("ix_citations_message_id"), "citations", ["message_id"])

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
    op.drop_table("citations")
    op.drop_table("messages")
    op.drop_table("conversations")
