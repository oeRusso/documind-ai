"""POST /api/v1/chat (stage 7): SSE answer with citations, against the real database.

The model is FakeLLMProvider (no Ollama); vectors come from FakeEmbeddingProvider. Answer
quality with real models is measured by `python -m evaluation.eval_answers`, not here.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.modules.ingestion.presentation.tasks import process
from app.modules.knowledge.application.prompt import NO_EVIDENCE_ANSWER
from tests.fakes import FakeEmbeddingProvider, FakeJobQueue, FakeLLMProvider
from tests.integration.api_helpers import Acme, register

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


async def ask(
    client: httpx.AsyncClient, headers: dict[str, str], question: str
) -> list[tuple[str, dict[str, Any]]]:
    response = await client.post("/api/v1/chat", json={"question": question}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


async def test_the_answer_streams_tokens_citations_and_done(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    events = await ask(client, acme.headers(acme.viewer), "¿Cuál es el preaviso para rescindir?")

    names = [name for name, _ in events]
    assert names[-2:] == ["citations", "done"]
    assert set(names[:-2]) == {"token"}
    text = "".join(data["text"] for name, data in events if name == "token")
    assert text == "El preaviso es de 30 días [1] y."  # [9] pointed to no chunk: dropped

    [citation] = events[-2][1]["citations"]
    assert citation["marker"] == 1
    assert citation["document_id"] == contrato
    assert citation["document_title"] == "contrato"
    assert citation["page_start"] >= 1
    assert citation["excerpt"]
    assert events[-1] == ("done", {"no_evidence": False})
    assert len(llm.calls) == 1


async def test_without_evidence_it_does_not_call_the_model(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider, db_app: FastAPI
) -> None:
    configure(db_app, rag_min_score=0.99)
    events = await ask(client, acme.headers(acme.viewer), "¿Quién ganó el mundial de 1986?")

    assert events == [
        ("token", {"text": NO_EVIDENCE_ANSWER}),
        ("citations", {"citations": []}),
        ("done", {"no_evidence": True}),
    ]
    assert llm.calls == []


async def test_another_organization_never_gets_acme_chunks(
    client: httpx.AsyncClient, contrato: str, llm: FakeLLMProvider
) -> None:
    eve = await register(client, "eve@example.com", slug="eves")
    eves_org = (await client.get("/api/v1/organizations", headers=eve.auth)).json()["items"][0]
    headers = {**eve.auth, "X-Organization-Id": eves_org["id"]}

    events = await ask(client, headers, "¿Cuál es el preaviso para rescindir?")

    assert events[-1] == ("done", {"no_evidence": True})
    assert llm.calls == []  # nothing of Acme reached the model


async def test_a_model_failure_ends_the_stream_with_an_error_event(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    llm.fail_after = 1
    events = await ask(client, acme.headers(acme.viewer), "¿Cuál es el preaviso?")

    name, data = events[-1]
    assert name == "error"
    assert data["code"] == "llm_failed"
    assert data["request_id"]


async def test_without_a_model_the_chat_answers_503(
    client: httpx.AsyncClient, acme: Acme, db_app: FastAPI
) -> None:
    db_app.state.llm = None
    response = await client.post(
        "/api/v1/chat", json={"question": "¿Algo?"}, headers=acme.headers(acme.viewer)
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "chat_unavailable"


async def test_an_empty_question_is_a_normal_422(
    client: httpx.AsyncClient, acme: Acme, llm: FakeLLMProvider
) -> None:
    for question in ("", "   "):
        response = await client.post(
            "/api/v1/chat", json={"question": question}, headers=acme.headers(acme.viewer)
        )
        assert response.status_code == 422
        assert "error" in response.json()


async def test_the_chat_needs_a_session(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json={"question": "¿Algo?"})
    assert response.status_code == 401


async def test_too_many_questions_per_minute_get_429(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider, db_app: FastAPI
) -> None:
    configure(db_app, chat_limit_per_user_per_minute=2)
    headers = acme.headers(acme.viewer)
    for _ in range(2):
        await ask(client, headers, "¿Preaviso?")
    response = await client.post("/api/v1/chat", json={"question": "¿Preaviso?"}, headers=headers)
    assert response.status_code == 429
    assert "Retry-After" in response.headers
