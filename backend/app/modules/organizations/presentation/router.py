"""HTTP endpoints for organizations. They translate HTTP <-> use cases; no business logic here.

These endpoints identify the organization by its id in the path, so they only need the user
(CurrentUserDep). Endpoints *inside* an organization (members, documents...) use
CurrentMemberDep and the X-Organization-Id header instead.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.dependencies import ClientIpDep
from app.core.exceptions import ErrorResponse
from app.core.pagination import Page
from app.modules.auth.presentation.dependencies import CurrentUserDep
from app.modules.organizations.application.create_organization import (
    CreateOrganization,
    CreateOrganizationCommand,
)
from app.modules.organizations.application.get_organization import (
    GetOrganization,
    ListMyOrganizations,
    OrganizationWithRole,
)
from app.modules.organizations.domain.roles import Role
from app.modules.organizations.presentation.dependencies import (
    provide_create_organization,
    provide_get_organization,
    provide_list_my_organizations,
)
from app.modules.organizations.presentation.schemas import OrganizationCreate, OrganizationRead

router = APIRouter(prefix="/organizations", tags=["organizations"])

_UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}
}


@router.get("", responses=_UNAUTHORIZED)
async def list_my_organizations(
    user: CurrentUserDep,
    use_case: Annotated[ListMyOrganizations, Depends(provide_list_my_organizations)],
) -> Page[OrganizationRead]:
    """Las organizaciones a las que pertenecés, con tu rol (selector de organización)."""
    items = await use_case.execute(user.id)
    return Page(items=[OrganizationRead.build(item) for item in items])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        **_UNAUTHORIZED,
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)
async def create_organization(
    body: OrganizationCreate,
    user: CurrentUserDep,
    ip: ClientIpDep,
    use_case: Annotated[CreateOrganization, Depends(provide_create_organization)],
) -> OrganizationRead:
    """Crea una organización; quien la crea queda como owner."""
    organization = await use_case.execute(
        CreateOrganizationCommand(name=body.name, slug=body.slug, owner_id=user.id, ip=ip)
    )
    return OrganizationRead.build(OrganizationWithRole(organization, Role.OWNER))


@router.get(
    "/{organization_id}",
    responses={**_UNAUTHORIZED, status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
async def get_organization(
    organization_id: UUID,
    user: CurrentUserDep,
    use_case: Annotated[GetOrganization, Depends(provide_get_organization)],
) -> OrganizationRead:
    """404 si no existe **o** si no sos miembro: desde afuera no se distinguen."""
    return OrganizationRead.build(await use_case.execute(organization_id, user.id))
