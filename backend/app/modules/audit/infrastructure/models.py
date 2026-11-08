"""SQLAlchemy model for the audit log. Insert-only: the `app` role has no UPDATE/DELETE on it.

No foreign keys on purpose: the log must keep its rows (and ids) after users or
organizations are deleted.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Index, String, Uuid
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin


class AuditLogModel(TimestampMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_organization_id_created_at", "organization_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # Null for events without an organization (e.g. a failed login).
    organization_id: Mapped[UUID | None] = mapped_column(Uuid)
    # Null when nobody is authenticated (e.g. a login with an unknown email).
    user_id: Mapped[UUID | None] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(64))  # e.g. "auth.login_failed"
    target: Mapped[str | None] = mapped_column(String(255))  # e.g. "membership:<uuid>"
    ip: Mapped[str | None] = mapped_column(INET)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
