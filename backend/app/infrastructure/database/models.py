"""Imports every module's models so `Base.metadata` knows all tables (used by Alembic).

Add one import per module when it gets its first table.
"""

from app.infrastructure.database.base import Base
from app.modules.audit.infrastructure.models import AuditLogModel
from app.modules.auth.infrastructure.models import RefreshTokenModel
from app.modules.organizations.infrastructure.models import (
    InvitationModel,
    MembershipModel,
    OrganizationModel,
)
from app.modules.users.infrastructure.models import UserModel

__all__ = [
    "AuditLogModel",
    "Base",
    "InvitationModel",
    "MembershipModel",
    "OrganizationModel",
    "RefreshTokenModel",
    "UserModel",
]
