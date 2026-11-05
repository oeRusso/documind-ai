"""Imports every module's models so `Base.metadata` knows all tables (used by Alembic).

Add one import per module when it gets its first table.
"""

from app.infrastructure.database.base import Base
from app.modules.organizations.infrastructure.models import OrganizationModel

__all__ = ["Base", "OrganizationModel"]
