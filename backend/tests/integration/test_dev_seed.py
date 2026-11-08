"""The demo data script (app/dev/seed.py) loads what the guide in the README promises."""

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.dev.seed import DEMO_PASSWORD, main, seed


async def login(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_seed_loads_two_organizations_once(
    client: httpx.AsyncClient, db_app: FastAPI, db_settings: Settings
) -> None:
    assert await seed(db_settings) is True
    assert await seed(db_settings) is False  # second run: nothing to do

    ana = await login(client, "ana@acme.test")
    [acme] = (await client.get("/api/v1/organizations", headers=ana)).json()["items"]
    members = await client.get("/api/v1/members", headers={**ana, "X-Organization-Id": acme["id"]})
    assert [(m["email"], m["role"]) for m in members.json()["items"]] == [
        ("ana@acme.test", "owner"),
        ("carla@acme.test", "admin"),
        ("mario@acme.test", "member"),
        ("bob@acme.test", "viewer"),
    ]
    eve = await login(client, "eve@globex.test")
    [globex] = (await client.get("/api/v1/organizations", headers=eve)).json()["items"]
    assert globex["slug"] == "globex"


def test_seed_refuses_to_run_outside_development(
    monkeypatch: pytest.MonkeyPatch, offline_settings: Settings
) -> None:
    production = offline_settings.model_copy(update={"app_env": "production"})
    monkeypatch.setattr("app.dev.seed.get_settings", lambda: production)

    with pytest.raises(SystemExit, match="only runs with APP_ENV=development"):
        main()
