"""SQLAlchemy model for users. Identity table: no organization_id and no RLS (ADR 0003)."""

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, String, Uuid, true
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin

EMAIL_MAX_LENGTH = 254  # RFC 5321 limit for a full address


class UserModel(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # The domain stores emails lowercased; the database refuses anything else,
        # so the UNIQUE constraint below is also case-insensitive in practice.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
