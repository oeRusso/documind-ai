"""Shared fixtures of the answer tests (POST /chat and conversations): fake models, a processed
contract and an SSE parser. Registered in conftest.py."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.modules.ingestion.presentation.tasks import process
from tests.fakes import FakeEmbeddingProvider, FakeJobQueue, FakeLLMProvider
from tests.integration.api_helpers import Acme

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture
def embeddings(db_app: FastAPI) -> FakeEmbeddingProvider:
    fake = FakeEmbeddingProvider()
    db_app.state.embeddings = fake
    return fake


@pytest.fixture
def llm(db_app: FastAPI) -> FakeLLMProvider:
    fake = FakeLLMProvider(["El preaviso ", "es de 30 días [1", "] y [9]."])
    db_app.state.llm = fake
    return fake


@pytest.fixture
def queue(db_app: FastAPI) -> FakeJobQueue:
    fake = FakeJobQueue()
    db_app.state.job_queue = fake
    return fake


def configure(app: FastAPI, **values: Any) -> None:
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update=values)


@pytest.fixture
async def contrato(
    client: httpx.AsyncClient,
    acme: Acme,
    queue: FakeJobQueue,
    db_settings: Settings,
    embeddings: FakeEmbeddingProvider,
    db_app: FastAPI,
) -> str:
    # Fake vectors are rough: any closeness counts as evidence here (the real threshold is
    # calibrated with real models in evaluation/).
    configure(db_app, rag_min_score=0.0)
    response = await client.post(
        "/api/v1/documents",
        files={"file": ("contrato.pdf", (FIXTURES / "contrato.pdf").read_bytes())},
        headers=acme.headers(acme.owner),
    )
    assert response.status_code == 201, response.text
    for org, job in queue.sent:
        assert await process(db_settings, org, job, embeddings=embeddings) == "ready"
    document_id: str = response.json()["id"]
    return document_id


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        if not lines:
            continue
        name = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append((name, json.loads(data)))
    return events
