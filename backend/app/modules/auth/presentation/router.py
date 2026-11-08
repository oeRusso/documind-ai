"""Auth endpoints. They translate HTTP <-> use cases; no business logic here."""

from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.core.dependencies import ClientIpDep
from app.core.exceptions import ErrorResponse
from app.modules.auth.application.issue_session import IssuedSession
from app.modules.auth.application.login import Login, LoginCommand
from app.modules.auth.application.logout import Logout, LogoutCommand
from app.modules.auth.application.refresh_session import RefreshSession, RefreshSessionCommand
from app.modules.auth.application.register import InvitationToken, Register, RegisterCommand
from app.modules.auth.domain.errors import InvalidTokenError
from app.modules.auth.presentation.cookies import (
    REFRESH_COOKIE,
    clear_session_cookies,
    set_session_cookies,
)
from app.modules.auth.presentation.csrf import reject_foreign_origin, require_csrf
from app.modules.auth.presentation.dependencies import (
    CurrentUserDep,
    provide_login,
    provide_logout,
    provide_refresh_session,
    provide_register,
)
from app.modules.auth.presentation.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE, include_in_schema=False)]


def _session_response(response: Response, session: IssuedSession) -> TokenResponse:
    set_session_cookies(response, session)
    return TokenResponse(
        access_token=session.access_token.value, expires_at=session.access_token.expires_at
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(reject_foreign_origin)],
    responses={**_ERRORS, status.HTTP_409_CONFLICT: {"model": ErrorResponse}},
)
async def register(
    body: RegisterRequest,
    response: Response,
    ip: ClientIpDep,
    use_case: Annotated[Register, Depends(provide_register)],
) -> TokenResponse:
    """Crea la cuenta e inicia sesión.

    Con `organization_name` y `organization_slug` crea su primera organización (como owner).
    Con `invitation` entra a la organización que lo invitó, con el rol de la invitación.
    """
    result = await use_case.execute(
        RegisterCommand(
            email=body.email,
            password=body.password,
            organization_name=body.organization_name,
            organization_slug=body.organization_slug,
            invitation=(
                InvitationToken(body.invitation.organization_id, body.invitation.token)
                if body.invitation
                else None
            ),
            ip=ip,
        )
    )
    return _session_response(response, result.session)


@router.post("/login", dependencies=[Depends(reject_foreign_origin)], responses=_ERRORS)
async def login(
    body: LoginRequest,
    response: Response,
    ip: ClientIpDep,
    use_case: Annotated[Login, Depends(provide_login)],
) -> TokenResponse:
    session = await use_case.execute(LoginCommand(email=body.email, password=body.password, ip=ip))
    return _session_response(response, session)


@router.post("/refresh", dependencies=[Depends(require_csrf)], responses=_ERRORS)
async def refresh(
    response: Response,
    ip: ClientIpDep,
    use_case: Annotated[RefreshSession, Depends(provide_refresh_session)],
    refresh_token: RefreshCookie = None,
) -> TokenResponse:
    """Cambia la cookie de refresh por una nueva y devuelve otro access token."""
    if not refresh_token:
        raise InvalidTokenError()
    session = await use_case.execute(RefreshSessionCommand(refresh_token=refresh_token, ip=ip))
    return _session_response(response, session)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses={status.HTTP_403_FORBIDDEN: {"model": ErrorResponse}},
)
async def logout(
    response: Response,
    ip: ClientIpDep,
    use_case: Annotated[Logout, Depends(provide_logout)],
    refresh_token: RefreshCookie = None,
) -> None:
    if refresh_token:
        await use_case.execute(LogoutCommand(refresh_token=refresh_token, ip=ip))
    clear_session_cookies(response)


@router.get("/me", responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}})
async def me(user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(user)
