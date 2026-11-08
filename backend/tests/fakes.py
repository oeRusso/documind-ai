"""In-memory fakes of the ports, for unit tests of use cases (no database, no Argon2).

They satisfy the Protocols in each module's `domain` without inheriting from them.
"""

from collections.abc import AsyncIterator, Collection, Sequence
from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.modules.audit.domain.entities import AuditEvent
from app.modules.auth.domain.refresh_tokens import RefreshToken
from app.modules.documents.domain.entities import (
    Document,
    DocumentVersion,
    DocumentWithVersion,
    FileKind,
    InspectedFile,
    PurgeItem,
)
from app.modules.documents.domain.errors import DuplicateDocumentError
from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.errors import (
    InvitationAlreadyPendingError,
    OrganizationSlugTakenError,
)
from app.modules.organizations.domain.invitation import Invitation
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from app.modules.users.domain.entities import User
from app.modules.users.domain.errors import EmailAlreadyRegisteredError
from app.shared.mail import EmailMessage


class FakeTenantContext:
    def __init__(self) -> None:
        self.user_id: UUID | None = None
        self.organization_id: UUID | None = None

    async def set_user(self, user_id: UUID) -> None:
        self.user_id = user_id

    async def set_organization(self, organization_id: UUID) -> None:
        self.organization_id = organization_id


class InMemoryOrganizationRepository:
    def __init__(self, tenant: FakeTenantContext) -> None:
        self.items: dict[UUID, Organization] = {}
        self.tenant = tenant

    async def add(self, organization: Organization) -> None:
        # Mimics the database: UNIQUE slug, and RLS only accepts rows of the active organization.
        if any(org.slug == organization.slug for org in self.items.values()):
            raise OrganizationSlugTakenError()
        assert self.tenant.organization_id == organization.id, "tenant context not set"
        self.items[organization.id] = organization

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        return self.items.get(organization_id)


class InMemoryMembershipRepository:
    def __init__(self, tenant: FakeTenantContext) -> None:
        self.items: list[Membership] = []
        self.tenant = tenant

    async def add(self, membership: Membership) -> None:
        assert self.tenant.organization_id == membership.organization_id, "tenant not set"
        self.items.append(membership)

    async def get_by_user(self, organization_id: UUID, user_id: UUID) -> Membership | None:
        return next(
            (
                m
                for m in self.items
                if m.organization_id == organization_id and m.user_id == user_id
            ),
            None,
        )

    async def list_by_user(self, user_id: UUID) -> list[Membership]:
        return [m for m in self.items if m.user_id == user_id]

    async def list_for_organization(self, organization_id: UUID) -> list[Membership]:
        return [m for m in self.items if m.organization_id == organization_id]

    async def get_by_id(self, organization_id: UUID, membership_id: UUID) -> Membership | None:
        return next(
            (
                m
                for m in self.items
                if m.organization_id == organization_id and m.id == membership_id
            ),
            None,
        )

    async def count_owners_for_update(self, organization_id: UUID) -> int:
        return sum(
            1 for m in self.items if m.organization_id == organization_id and m.role is Role.OWNER
        )

    async def update_role(
        self, organization_id: UUID, membership_id: UUID, role: Role, now: datetime
    ) -> None:
        membership = await self.get_by_id(organization_id, membership_id)
        if membership is not None:
            membership.role = role
            membership.updated_at = now

    async def remove(self, organization_id: UUID, membership_id: UUID) -> None:
        self.items = [
            m
            for m in self.items
            if not (m.organization_id == organization_id and m.id == membership_id)
        ]


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, User] = {}

    async def add(self, user: User) -> None:
        if any(u.email == user.email for u in self.items.values()):
            raise EmailAlreadyRegisteredError()
        self.items[user.id] = user

    async def get_by_id(self, user_id: UUID) -> User | None:
        return self.items.get(user_id)

    async def list_by_ids(self, user_ids: Collection[UUID]) -> list[User]:
        return [u for u in self.items.values() if u.id in user_ids]

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.items.values() if u.email == email), None)


class FakePasswordHasher:
    """Instant and transparent. Counts calls so tests can check timing equalization."""

    def __init__(self) -> None:
        self.hash_calls = 0
        self.verify_calls = 0

    async def hash(self, password: str) -> str:
        self.hash_calls += 1
        return f"fake-hash:{password}"

    async def verify(self, password_hash: str, password: str) -> bool:
        self.verify_calls += 1
        return password_hash == f"fake-hash:{password}"


class InMemoryAuditLogRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def add(self, event: AuditEvent) -> None:
        self.events.append(event)

    @property
    def actions(self) -> list[str]:
        return [str(event.action) for event in self.events]


class InMemoryRefreshTokenRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, RefreshToken] = {}

    async def add(self, token: RefreshToken) -> None:
        self.items[token.id] = token

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        return next((t for t in self.items.values() if t.token_hash == token_hash), None)

    async def mark_replaced(self, token_id: UUID, replaced_by_id: UUID, now: datetime) -> None:
        self.items[token_id].replaced_by_id = replaced_by_id

    async def revoke_family(self, family_id: UUID, now: datetime) -> int:
        tokens = [
            t for t in self.items.values() if t.family_id == family_id and t.revoked_at is None
        ]
        for token in tokens:
            token.revoked_at = now
        return len(tokens)

    def family(self, family_id: UUID) -> list[RefreshToken]:
        return [t for t in self.items.values() if t.family_id == family_id]


class InMemoryInvitationRepository:
    def __init__(self, tenant: FakeTenantContext) -> None:
        self.items: list[Invitation] = []
        self.tenant = tenant

    def _open(self, organization_id: UUID) -> list[Invitation]:
        return [
            i
            for i in self.items
            if i.organization_id == organization_id
            and i.accepted_at is None
            and i.revoked_at is None
        ]

    async def add(self, invitation: Invitation) -> None:
        assert self.tenant.organization_id == invitation.organization_id, "tenant not set"
        if any(i.email == invitation.email for i in self._open(invitation.organization_id)):
            raise InvitationAlreadyPendingError()
        self.items.append(invitation)

    async def list_open(self, organization_id: UUID) -> list[Invitation]:
        return self._open(organization_id)

    async def get_by_id(self, organization_id: UUID, invitation_id: UUID) -> Invitation | None:
        return next(
            (
                i
                for i in self.items
                if i.organization_id == organization_id and i.id == invitation_id
            ),
            None,
        )

    async def get_open_by_email(self, organization_id: UUID, email: str) -> Invitation | None:
        return next((i for i in self._open(organization_id) if i.email == email), None)

    async def get_by_token_hash_for_update(
        self, organization_id: UUID, token_hash: str
    ) -> Invitation | None:
        # Like RLS: only the organization in the tenant context is visible.
        if self.tenant.organization_id != organization_id:
            return None
        return next(
            (
                i
                for i in self.items
                if i.organization_id == organization_id and i.token_hash == token_hash
            ),
            None,
        )

    async def save_status(self, invitation: Invitation) -> None:
        """The entities in `items` are the same objects the use case changed."""


class FakeOutgoingMail:
    """Keeps queued emails in a list instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def queue(self, message: EmailMessage) -> None:
        self.sent.append(message)

    async def send(self, message: EmailMessage) -> None:  # also usable as a Mailer
        self.sent.append(message)


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self.documents: dict[UUID, Document] = {}
        self.versions: list[DocumentVersion] = []
        self.deleted_versions: set[UUID] = set()

    def _live(self, organization_id: UUID, document_id: UUID) -> Document | None:
        doc = self.documents.get(document_id)
        if doc is None or doc.organization_id != organization_id or doc.is_deleted:
            return None
        return doc

    def _check_duplicate(self, version: DocumentVersion) -> None:
        for v in self.versions:
            if (
                v.organization_id == version.organization_id
                and v.sha256 == version.sha256
                and v.id not in self.deleted_versions
            ):
                existing = self.documents[v.document_id]
                raise DuplicateDocumentError(existing.id, existing.title)

    async def add(self, document: Document, version: DocumentVersion) -> None:
        self._check_duplicate(version)
        self.documents[document.id] = document
        self.versions.append(version)

    async def add_version(self, document: Document, version: DocumentVersion) -> None:
        self._check_duplicate(version)
        self.documents[document.id] = document
        self.versions.append(version)

    async def get(self, organization_id: UUID, document_id: UUID) -> Document | None:
        return self._live(organization_id, document_id)

    async def get_for_update(self, organization_id: UUID, document_id: UUID) -> Document | None:
        return self._live(organization_id, document_id)

    async def list_page(
        self, organization_id: UUID, *, limit: int, before_id: UUID | None
    ) -> list[DocumentWithVersion]:
        docs = sorted(
            (
                d
                for d in self.documents.values()
                if d.organization_id == organization_id and not d.is_deleted
            ),
            key=lambda d: d.id,
            reverse=True,
        )
        if before_id is not None:
            docs = [d for d in docs if d.id < before_id]
        result = []
        for doc in docs[:limit]:
            latest = max(
                (v for v in self.versions if v.document_id == doc.id), key=lambda v: v.number
            )
            result.append(DocumentWithVersion(doc, latest))
        return result

    async def list_versions(
        self, organization_id: UUID, document_id: UUID
    ) -> list[DocumentVersion]:
        return sorted(
            (
                v
                for v in self.versions
                if v.organization_id == organization_id and v.document_id == document_id
            ),
            key=lambda v: v.number,
            reverse=True,
        )

    async def find_live_by_sha256(self, organization_id: UUID, sha256: str) -> Document | None:
        for v in self.versions:
            if (
                v.organization_id == organization_id
                and v.sha256 == sha256
                and v.id not in self.deleted_versions
            ):
                return self.documents[v.document_id]
        return None

    async def mark_deleted(self, document: Document) -> None:
        self.documents[document.id] = document
        self.deleted_versions |= {v.id for v in self.versions if v.document_id == document.id}

    async def remove(self, organization_id: UUID, document_id: UUID) -> None:
        doc = self.documents.get(document_id)
        if doc is not None and doc.organization_id == organization_id:
            del self.documents[document_id]
            self.versions = [v for v in self.versions if v.document_id != document_id]


class InMemoryPurgeQueue:
    def __init__(self) -> None:
        self.items: list[PurgeItem] = []

    async def add(self, items: Sequence[PurgeItem]) -> None:
        self.items.extend(items)

    async def due(self, now: datetime, limit: int) -> list[PurgeItem]:
        return [i for i in self.items if i.purge_after <= now][:limit]

    async def done(self, item_ids: Sequence[UUID]) -> None:
        self.items = [i for i in self.items if i.id not in item_ids]


class InMemoryStorage:
    """StorageBackend in a dict. `save` reads the staged file, like the real one moves it."""

    def __init__(self, staging: Path) -> None:
        self._staging = staging
        self.files: dict[str, bytes] = {}

    def staging_dir(self) -> Path:
        self._staging.mkdir(parents=True, exist_ok=True)
        return self._staging

    async def save(self, key: str, staged_file: Path) -> None:
        self.files[key] = staged_file.read_bytes()
        staged_file.unlink()

    async def read(self, key: str) -> AsyncIterator[bytes]:
        yield self.files[key]

    async def delete(self, key: str) -> None:
        self.files.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self.files


class FakeFileInspector:
    """Trusts the extension; `refuse` makes it raise like the real inspector would."""

    def __init__(self) -> None:
        self.refuse: Exception | None = None

    def inspect(self, path: Path, filename: str) -> InspectedFile:
        if self.refuse is not None:
            raise self.refuse
        kind = FileKind(Path(filename).suffix.lstrip(".") or "txt")
        return InspectedFile(kind, 3 if kind is FileKind.PDF else None)
