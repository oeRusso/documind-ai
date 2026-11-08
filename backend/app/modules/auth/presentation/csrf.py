"""CSRF protection for the endpoints that authenticate with the cookie (ADR 0004).

Two independent checks:
1. Origin: browsers always send it on POST, and a page on another site cannot fake it.
2. Double submit: the X-CSRF-Token header must equal the csrf_token cookie. Another site can
   make the browser send the cookie, but cannot read it to copy it into the header.
"""

import hmac

from fastapi import Request

from app.core.dependencies import SettingsDep
from app.modules.auth.presentation.cookies import CSRF_COOKIE, CSRF_HEADER
from app.shared.errors import ForbiddenError


class CsrfError(ForbiddenError):
    code = "csrf_failed"
    message = "La solicitud no vino de la aplicación"


def _origin_matches(request: Request, allowed_origin: str) -> bool:
    origin = request.headers.get("origin")
    return origin is not None and origin.rstrip("/").lower() == allowed_origin


def require_csrf(request: Request, settings: SettingsDep) -> None:
    """For /auth/refresh and /auth/logout."""
    if not _origin_matches(request, settings.app_origin):
        raise CsrfError()
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    # compare_digest takes the same time whatever the input: no hints from timing.
    if not cookie or not hmac.compare_digest(cookie.encode(), header.encode()):
        raise CsrfError()


def reject_foreign_origin(request: Request, settings: SettingsDep) -> None:
    """For login and register: they do not use cookies, but a foreign site has no business
    posting to them. Clients that send no Origin (curl, scripts) are allowed."""
    if "origin" in request.headers and not _origin_matches(request, settings.app_origin):
        raise CsrfError()
