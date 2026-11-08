"""In-memory fakes of the ports, for unit tests of use cases (no database, no Argon2).

They satisfy the Protocols in each module's `domain` without inheriting from them.
"""

from collections.abc import Collection
from datetime import datetime
from uuid import UUID

from app.modules.audit.domain.entities import AuditEvent
from app.modules.auth.domain.refresh_tokens import RefreshToken
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
