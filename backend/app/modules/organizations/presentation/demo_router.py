"""GET /api/v1/demo: the public demo account, for the "Probar la demo" button (stage 12).

The password is public on purpose: the account is read-only (viewer, cannot create
organizations), shared, rate limited per IP and reset every night (app/jobs/reset_demo.py).
"""

from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.core.dependencies import SettingsDep
from app.core.exceptions import ErrorResponse
from app.shared.demo import DEMO_EMAIL
from app.shared.errors import NotFoundError

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoDisabledError(NotFoundError):
    code = "demo_disabled"
    message = "La demo pública no está activa"


class DemoAccountRead(BaseModel):
    email: str
    password: str


_ERRORS: dict[int | str, dict[str, Any]] = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}


@router.get("", responses=_ERRORS)
async def demo_account(settings: SettingsDep) -> DemoAccountRead:
    """La cuenta de la demo pública (solo lectura, compartida, se borra cada noche)."""
    if settings.demo_password is None:
        raise DemoDisabledError()
    return DemoAccountRead(email=DEMO_EMAIL, password=settings.demo_password.get_secret_value())
