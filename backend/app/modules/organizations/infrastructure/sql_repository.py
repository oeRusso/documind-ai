"""Organization and membership repositories implemented with SQLAlchemy (PostgreSQL)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.errors import OrganizationSlugTakenError
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from app.modules.organizations.infrastructure.models import MembershipModel, OrganizationModel


def _to_entity(model: OrganizationModel) -> Organization:
    return Organization(
        id=model.id,
        name=model.name,
        slug=model.slug,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlOrganizationRepository:
    """Does not commit: the transaction belongs to the request (see get_session)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, organization: Organization) -> None:
        self._session.add(
            OrganizationModel(
                id=organization.id,
                name=organization.name,
                slug=organization.slug,
                created_at=organization.created_at,
                updated_at=organization.updated_at,
            )
        )
        try:
            await self._session.flush()  # sends the INSERT now, so constraint errors surface here
        except IntegrityError as exc:
            raise OrganizationSlugTakenError() from exc

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        model = await self._session.get(OrganizationModel, organization_id)
        return _to_entity(model) if model else None


def _membership_to_entity(model: MembershipModel) -> Membership:
    return Membership(
        id=model.id,
        organization_id=model.organization_id,
        user_id=model.user_id,
        role=Role(model.role),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlMembershipRepository:
    """Does not commit: the transaction belongs to the request (see get_session)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, membership: Membership) -> None:
        self._session.add(
            MembershipModel(
                id=membership.id,
                organization_id=membership.organization_id,
                user_id=membership.user_id,
                role=str(membership.role),
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
        )
        await self._session.flush()

    async def get_by_user(self, organization_id: UUID, user_id: UUID) -> Membership | None:
        result = await self._session.execute(
            select(MembershipModel).where(
                MembershipModel.organization_id == organization_id,
                MembershipModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return _membership_to_entity(model) if model else None

    async def list_by_user(self, user_id: UUID) -> list[Membership]:
        result = await self._session.execute(
            select(MembershipModel)
            .where(MembershipModel.user_id == user_id)
            .order_by(MembershipModel.created_at)
        )
        return [_membership_to_entity(model) for model in result.scalars()]
