"""Wiring: which concrete implementation each use case receives (dependency injection)."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.modules.organizations.domain.repository import OrganizationRepository
from app.modules.organizations.infrastructure.sql_repository import SqlOrganizationRepository

# scope="function": commit before the response is sent (see get_session).
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]


def get_organization_repository(session: SessionDep) -> OrganizationRepository:
    return SqlOrganizationRepository(session)


OrganizationRepositoryDep = Annotated[OrganizationRepository, Depends(get_organization_repository)]
