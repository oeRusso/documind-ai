"""GET /api/v1/auth/registration: the login page hides "Creá una cuenta" when sign-up is closed."""

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings


@pytest.mark.parametrize("is_open", [True, False])
async def test_it_tells_whether_new_organizations_can_sign_up(
    offline_client: httpx.AsyncClient,
    offline_app: FastAPI,
    offline_settings: Settings,
    is_open: bool,
) -> None:
    offline_app.state.settings = offline_settings.model_copy(update={"registration_open": is_open})
    response = await offline_client.get("/api/v1/auth/registration")
    assert response.status_code == 200
    assert response.json() == {"open": is_open}
