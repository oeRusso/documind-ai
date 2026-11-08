"""HTTP endpoints for the members of the active organization (X-Organization-Id header).

404 for a membership of another organization (it does not exist from here); 403 when your
role does not allow the action; 409 when the change would leave the organization without owner.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.core.dependencies import ClientIpDep
from app.core.exceptions import ErrorResponse
from app.core.pagination import Page
from app.modules.auth.presentation.dependencies import CurrentMemberDep
from app.modules.organizations.application.manage_members import (
    ChangeMemberRole,
    ChangeMemberRoleCommand,
    ListMembers,
    RemoveMember,
    RemoveMemberCommand,
)
from app.modules.organizations.presentation.dependencies import (
    provide_change_member_role,
    provide_list_members,
    provide_remove_member,
)
from app.modules.organizations.presentation.schemas import MemberRead, MemberRoleUpdate

router = APIRouter(prefix="/members", tags=["members"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
}
_MANAGE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ErrorResponse},
}


@router.get("", responses=_ERRORS)
async def list_members(
    member: CurrentMemberDep,
    use_case: Annotated[ListMembers, Depends(provide_list_members)],
) -> Page[MemberRead]:
    """Los miembros de la organización activa, del más antiguo al más nuevo.

    Sin cursor por ahora: una organización tiene pocos miembros, así que `next_cursor` es null.
    """
    items = await use_case.execute(member)
    return Page(items=[MemberRead.build(item) for item in items])


@router.patch("/{membership_id}", responses=_MANAGE_ERRORS)
async def change_member_role(
    membership_id: UUID,
    body: MemberRoleUpdate,
    member: CurrentMemberDep,
    ip: ClientIpDep,
    use_case: Annotated[ChangeMemberRole, Depends(provide_change_member_role)],
) -> MemberRead:
    """Cambia el rol de un miembro. Owners y admins; un admin solo maneja roles menores al suyo."""
    updated = await use_case.execute(
        ChangeMemberRoleCommand(actor=member, membership_id=membership_id, role=body.role, ip=ip)
    )
    return MemberRead.build(updated)


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_MANAGE_ERRORS)
async def remove_member(
    membership_id: UUID,
    member: CurrentMemberDep,
    ip: ClientIpDep,
    use_case: Annotated[RemoveMember, Depends(provide_remove_member)],
) -> Response:
    """Quita a alguien de la organización. No borra su cuenta: solo pierde el acceso a esta."""
    await use_case.execute(RemoveMemberCommand(actor=member, membership_id=membership_id, ip=ip))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
