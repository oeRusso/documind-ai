"""HTTP endpoints for invitations to the active organization (X-Organization-Id header)."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.core.dependencies import ClientIpDep, SettingsDep
from app.core.exceptions import ErrorResponse
from app.core.pagination import Page
from app.core.rate_limits import RateLimiterDep, accept_invitation_per_user
from app.modules.auth.presentation.dependencies import (
    CurrentMemberDep,
    CurrentUserDep,
    provide_accept_invitation,
)
from app.modules.auth.presentation.schemas import InvitationAccept
from app.modules.organizations.application.invitations import (
    AcceptInvitation,
    AcceptInvitationCommand,
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
    OrganizationRead,
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


async def limit_accept_by_user(
    user: CurrentUserDep, limiter: RateLimiterDep, settings: SettingsDep
) -> None:
    await limiter.hit(f"accept_invitation:user:{user.id}", accept_invitation_per_user(settings))


@router.post(
    "/accept",
    dependencies=[Depends(limit_accept_by_user)],
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    },
)
async def accept_invitation(
    body: InvitationAccept,
    user: CurrentUserDep,
    ip: ClientIpDep,
    use_case: Annotated[AcceptInvitation, Depends(provide_accept_invitation)],
) -> OrganizationRead:
    """Acepta una invitación con la sesión iniciada. El email de la cuenta debe ser el invitado.

    Sin cuenta todavía: `POST /auth/register` con `invitation` en lugar de la organización.
    """
    joined = await use_case.execute(
        AcceptInvitationCommand(
            user_id=user.id,
            user_email=user.email,
            organization_id=body.organization_id,
            token=body.token,
            ip=ip,
        )
    )
    return OrganizationRead.build(joined)
