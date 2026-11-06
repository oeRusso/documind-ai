"""HTTP endpoints. They translate HTTP <-> use cases; no business logic here.

Stage 1: no authentication yet (local development only). Stage 2 adds users and memberships.
"""

from uuid import UUID

from fastapi import APIRouter, status

from app.core.exceptions import ErrorResponse
from app.modules.organizations.application.create_organization import (
    CreateOrganization,
    CreateOrganizationCommand,
)
from app.modules.organizations.application.get_organization import GetOrganization
from app.modules.organizations.presentation.dependencies import OrganizationRepositoryDep
from app.modules.organizations.presentation.schemas import OrganizationCreate, OrganizationRead

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)
async def create_organization(
    body: OrganizationCreate,
    repository: OrganizationRepositoryDep,
) -> OrganizationRead:
    organization = await CreateOrganization(repository).execute(
        CreateOrganizationCommand(name=body.name, slug=body.slug)
    )
    return OrganizationRead.model_validate(organization)


@router.get(
    "/{organization_id}",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
async def get_organization(
    organization_id: UUID,
    repository: OrganizationRepositoryDep,
) -> OrganizationRead:
    organization = await GetOrganization(repository).execute(organization_id)
    return OrganizationRead.model_validate(organization)
