"""Private history per visitor in the public demo (stage 3, after the first deploy).

The demo account is shared by strangers (ADR 0014); each browser gets a random `demo_visitor`
cookie and its conversations carry that id. NULL for every other account. Additive only, so a
rollback to 0007 code keeps working.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("demo_visitor_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "demo_visitor_id")
