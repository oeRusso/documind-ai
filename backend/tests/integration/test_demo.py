"""The public demo (stage 12): reset job, public account, read-only rules and stricter limits."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from app.core.config import Settings
from app.jobs.reset_demo import DOCUMENTS_DIR, reset_demo
from app.modules.ingestion.presentation.tasks import process
from app.shared.demo import DEMO_EMAIL, DEMO_ORGANIZATION_ID
from tests.fakes import FakeEmbeddingProvider, FakeLLMProvider
from tests.integration.chat_fixtures import configure

DEMO_PASSWORD = "demo-publica-de-prueba"  # pragma: allowlist secret


@pytest.fixture
def demo_settings(db_settings: Settings, db_app: FastAPI) -> Settings:
    settings = db_settings.model_copy(update={"demo_password": SecretStr(DEMO_PASSWORD)})
    db_app.state.settings = settings
    return settings


async def login_demo(client: httpx.AsyncClient) -> dict[str, str]:
    account = (await client.get("/api/v1/demo")).json()
    assert account == {"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
    response = await client.post("/api/v1/auth/login", json=account)
    assert response.status_code == 200, response.text
    return {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "X-Organization-Id": str(DEMO_ORGANIZATION_ID),
    }


async def test_without_a_password_there_is_no_demo(
    client: httpx.AsyncClient, db_settings: Settings, db_app: FastAPI
) -> None:
    # Explicit: the developer's .env may turn the demo on.
    settings = db_settings.model_copy(update={"demo_password": None})
    db_app.state.settings = settings
    assert await reset_demo(settings, send_jobs=False) is None
    response = await client.get("/api/v1/demo")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "demo_disabled"


async def test_the_reset_builds_the_demo_and_is_idempotent(
    client: httpx.AsyncClient, demo_settings: Settings
) -> None:
    first = await reset_demo(demo_settings, send_jobs=False)
    assert first is not None and first.created
    expected = sorted(p.stem for p in Path(DOCUMENTS_DIR).glob("*.pdf"))
    assert sorted(first.uploaded) == expected
    assert len(first.jobs) == len(expected)

    second = await reset_demo(demo_settings, send_jobs=False)
    assert second is not None
    assert (second.created, second.uploaded, second.jobs) == (False, [], [])

    headers = await login_demo(client)
    documents = (await client.get("/api/v1/documents", headers=headers)).json()["items"]
    assert sorted(d["title"] for d in documents) == expected


async def test_the_demo_account_is_read_only(
    client: httpx.AsyncClient, demo_settings: Settings
) -> None:
    await reset_demo(demo_settings, send_jobs=False)
    headers = await login_demo(client)

    org = await client.post(
        "/api/v1/organizations", json={"name": "Mía", "slug": "mia-demo"}, headers=headers
    )
    assert org.status_code == 403
    assert org.json()["error"]["code"] == "demo_read_only"
    upload = await client.post(
        "/api/v1/documents", files={"file": ("x.txt", b"hola mundo")}, headers=headers
    )
    assert upload.status_code == 403
    analytics = await client.get("/api/v1/analytics/overview", headers=headers)
    assert analytics.status_code == 403


async def test_questions_are_limited_per_ip_and_deleted_every_night(
    client: httpx.AsyncClient, demo_settings: Settings, db_app: FastAPI
) -> None:
    report = await reset_demo(demo_settings, send_jobs=False)
    assert report is not None
    embeddings = FakeEmbeddingProvider()
    db_app.state.embeddings = embeddings
    db_app.state.llm = FakeLLMProvider(["Un mes [1]."])
    configure(db_app, rag_min_score=0.0)
    for org, job in report.jobs[:1]:
        await process(demo_settings, org, job, embeddings=embeddings)
    headers = await login_demo(client)

    statuses = []
    for _ in range(4):  # demo limit: 3 per minute and IP
        response = await client.post(
            "/api/v1/chat", json={"question": "¿Cuál es el preaviso?"}, headers=headers
        )
        statuses.append(response.status_code)
    assert statuses == [200, 200, 200, 429]

    conversation = await client.post("/api/v1/conversations", json={}, headers=headers)
    assert conversation.status_code == 201
    again = await reset_demo(demo_settings, send_jobs=False)
    assert again is not None and again.conversations_deleted == 1
    assert (await client.get("/api/v1/conversations", headers=headers)).json()["items"] == []
