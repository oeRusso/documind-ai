"""Use case: the caller's membership in an organization, or 404 if they are not a member.

404 and not 403 on purpose: an organization you do not belong to must look like one that
does not exist (CLAUDE.md, "Reglas que nunca se rompen").
"""

from uuid import UUID

from app.modules.organizations.domain.errors import OrganizationNotFoundError
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.repository import MembershipRepository


class ResolveMembership:
    def __init__(self, memberships: MembershipRepository) -> None:
        self._memberships = memberships

    async def execute(self, organization_id: UUID, user_id: UUID) -> Membership:
        membership = await self._memberships.get_by_user(organization_id, user_id)
        if membership is None:
            raise OrganizationNotFoundError()
        return membership
