"""Repository interfaces. `application` depends on these, never on the SQL implementations.

Rule of the project: methods on tenant data take `organization_id` as a required argument,
even though RLS would also filter (two independent layers, ADR 0003).
"""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.invitation import Invitation
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role


class OrganizationRepository(Protocol):
    async def add(self, organization: Organization) -> None:
        """Persist a new organization. Raises OrganizationSlugTakenError on duplicate slug."""
        ...

    async def get_by_id(self, organization_id: UUID) -> Organization | None: ...


class MembershipRepository(Protocol):
    async def add(self, membership: Membership) -> None: ...

    async def get_by_user(self, organization_id: UUID, user_id: UUID) -> Membership | None: ...

    async def list_by_user(self, user_id: UUID) -> list[Membership]:
        """Every organization the user belongs to (organization selector).

        The one query that is not scoped by organization: it runs before one is chosen.
        RLS allows it through the `own_memberships` policy (only the user's own rows).
        """
        ...

    async def list_for_organization(self, organization_id: UUID) -> list[Membership]:
        """Every member of the organization, oldest first."""
        ...

    async def get_by_id(self, organization_id: UUID, membership_id: UUID) -> Membership | None:
        """None when the id does not exist *or* belongs to another organization."""
        ...

    async def count_owners_for_update(self, organization_id: UUID) -> int:
        """Count the owners and lock their rows until the transaction ends.

        Two owners demoting each other at the same time could otherwise both see "2 owners"
        and leave the organization with none. With the lock, the second one waits and then
        sees the first change.
        """
        ...

    async def update_role(
        self, organization_id: UUID, membership_id: UUID, role: Role, now: datetime
    ) -> None: ...

    async def remove(self, organization_id: UUID, membership_id: UUID) -> None: ...


class InvitationRepository(Protocol):
    async def add(self, invitation: Invitation) -> None:
        """Raises InvitationAlreadyPendingError if the email already has an open invitation."""
        ...

    async def list_open(self, organization_id: UUID) -> list[Invitation]:
        """Not accepted and not revoked (expired ones included, so they can be revoked)."""
        ...

    async def get_by_id(self, organization_id: UUID, invitation_id: UUID) -> Invitation | None: ...

    async def get_open_by_email(self, organization_id: UUID, email: str) -> Invitation | None: ...

    async def get_by_token_hash_for_update(
        self, organization_id: UUID, token_hash: str
    ) -> Invitation | None:
        """Locks the row: the same link accepted twice at once only works once."""
        ...

    async def save_status(self, invitation: Invitation) -> None:
        """Persist accepted_at, revoked_at and updated_at."""
        ...
