"""OrganizationRepository implemented with SQLAlchemy (PostgreSQL)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.errors import OrganizationSlugTakenError
from app.modules.organizations.infrastructure.models import OrganizationModel


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

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self._session.execute(
            select(OrganizationModel).where(OrganizationModel.slug == slug)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None
