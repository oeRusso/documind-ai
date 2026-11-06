"""Session cookies (ADR 0004).

- refresh_token: HttpOnly (JavaScript cannot read it), sent only to /api/v1/auth.
- csrf_token: readable by JavaScript on purpose; the frontend copies it into the
  X-CSRF-Token header (double submit). A page on another site cannot read it.
"""

from datetime import datetime

from fastapi import Response

from app.modules.auth.application.issue_session import IssuedSession
from app.shared.ids import utc_now
from app.shared.secure_tokens import generate_token

REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _max_age(expires_at: datetime) -> int:
    return max(0, int((expires_at - utc_now()).total_seconds()))


def set_session_cookies(response: Response, session: IssuedSession) -> None:
    max_age = _max_age(session.refresh_expires_at)
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        generate_token(),
        max_age=max_age,
        path="/",
        secure=True,
        httponly=False,
        samesite="lax",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, secure=True, httponly=True, samesite="lax"
    )
    response.delete_cookie(CSRF_COOKIE, path="/", secure=True, httponly=False, samesite="lax")
