"""HTTP endpoints for invitations to the active organization (X-Organization-Id header)."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.core.dependencies import ClientIpDep
from app.core.exceptions import ErrorResponse
from app.core.pagination import Page
from app.modules.auth.presentation.dependencies import CurrentMemberDep
from app.modules.organizations.application.invitations import (
    CreateInvitation,
    CreateInvitationCommand,
    ListInvitations,
    RevokeInvitation,
    RevokeInvitationCommand,
)
from app.modules.organizations.presentation.dependencies import (
    provide_create_invitation,
    provide_list_invitations,
    provide_revoke_invitation,
)
from app.modules.organizations.presentation.schemas import (
    CreatedInvitationRead,
    InvitationCreate,
    InvitationRead,
)
from app.shared.ids import utc_now

router = APIRouter(prefix="/invitations", tags=["invitations"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        **_ERRORS,
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)
async def create_invitation(
    body: InvitationCreate,
    member: CurrentMemberDep,
    ip: ClientIpDep,
    use_case: Annotated[CreateInvitation, Depends(provide_create_invitation)],
) -> CreatedInvitationRead:
    """Invita a un email con un rol. Owners y admins (un admin invita member o viewer).

    Devuelve el link para aceptar; vence en 7 días.
    """
    created = await use_case.execute(
        CreateInvitationCommand(actor=member, email=body.email, role=body.role, ip=ip)
    )
    read = InvitationRead.build(created.invitation, utc_now())
    return CreatedInvitationRead(**read.model_dump(), link=created.link)


@router.get("", responses=_ERRORS)
async def list_invitations(
    member: CurrentMemberDep,
    use_case: Annotated[ListInvitations, Depends(provide_list_invitations)],
) -> Page[InvitationRead]:
    """Invitaciones abiertas (pendientes o vencidas). Sin cursor por ahora, como `/members`."""
    now = utc_now()
    return Page(items=[InvitationRead.build(i, now) for i in await use_case.execute(member)])


@router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def revoke_invitation(
    invitation_id: UUID,
    member: CurrentMemberDep,
    ip: ClientIpDep,
    use_case: Annotated[RevokeInvitation, Depends(provide_revoke_invitation)],
) -> Response:
    """Revoca una invitación: su link deja de servir."""
    await use_case.execute(
        RevokeInvitationCommand(actor=member, invitation_id=invitation_id, ip=ip)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
