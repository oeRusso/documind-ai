"""Imports every module's models so `Base.metadata` knows all tables (used by Alembic).

Add one import per module when it gets its first table.
"""

from app.infrastructure.database.base import Base
from app.modules.audit.infrastructure.models import AuditLogModel
from app.modules.auth.infrastructure.models import RefreshTokenModel
from app.modules.conversations.infrastructure.models import (
    CitationModel,
    ConversationModel,
    MessageModel,
)
from app.modules.documents.infrastructure.models import (
    DocumentModel,
    DocumentPurgeModel,
    DocumentVersionModel,
)
from app.modules.ingestion.infrastructure.models import (
    ChunkEmbeddingModel,
    DocumentChunkModel,
    ProcessingJobModel,
)
from app.modules.organizations.infrastructure.models import (
    InvitationModel,
    MembershipModel,
    OrganizationModel,
)
from app.modules.users.infrastructure.models import UserModel

__all__ = [
    "AuditLogModel",
    "Base",
    "ChunkEmbeddingModel",
    "CitationModel",
    "ConversationModel",
    "DocumentChunkModel",
    "DocumentModel",
    "DocumentPurgeModel",
    "DocumentVersionModel",
    "InvitationModel",
    "MembershipModel",
    "MessageModel",
    "OrganizationModel",
    "ProcessingJobModel",
    "RefreshTokenModel",
    "UserModel",
]
