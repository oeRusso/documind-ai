"""Search over documents (stage 6), against PostgreSQL with RLS, pgvector and full-text search.

Vectors come from FakeEmbeddingProvider (texts sharing words are close), so the plumbing of
the vector and hybrid modes is tested without Ollama. The quality of the real models is
measured by `python -m evaluation.eval_retrieval`, not here.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.modules.ingestion.presentation.tasks import process
from tests.fakes import FakeEmbeddingProvider, FakeJobQueue
from tests.integration.api_helpers import Acme, register

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture
def embeddings(db_app: FastAPI) -> FakeEmbeddingProvider:
    fake = FakeEmbeddingProvider()
    db_app.state.embeddings = fake
    return fake


@pytest.fixture
def queue(db_app: FastAPI) -> FakeJobQueue:
    fake = FakeJobQueue()
    db_app.state.job_queue = fake
    return fake


async def load(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    queue: FakeJobQueue,
    settings: Settings,
    embeddings: FakeEmbeddingProvider,
    *names: str,
) -> dict[str, str]:
    ids = {}
    for name in names:
        response = await client.post(
            "/api/v1/documents",
            files={"file": (name, (FIXTURES / name).read_bytes())},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        ids[name] = response.json()["id"]
    for org, job in queue.sent:
        assert await process(settings, org, job, embeddings=embeddings) == "ready"
    queue.sent.clear()
    return ids


async def search(
    client: httpx.AsyncClient, headers: dict[str, str], q: str, **params: Any
) -> dict[str, Any]:
    response = await client.get("/api/v1/search", params={"q": q, **params}, headers=headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_finds_the_clause_by_words_ignoring_accents(
    client: httpx.AsyncClient,
    acme: Acme,
    queue: FakeJobQueue,
    db_settings: Settings,
    embeddings: FakeEmbeddingProvider,
) -> None:
    headers = acme.headers(acme.viewer)
    await load(client, acme.headers(acme.owner), queue, db_settings, embeddings, "contrato.pdf")

    # "rescindirlo con un preaviso" is in clause 2; no accents typed, plural forms.
    result = await search(client, headers, "preavisos para rescindir", mode="text")

    top = result["items"][0]
    assert result["mode"] == "text"
    assert "PLAZO" in top["section"]
    assert (top["page_start"], top["document_title"]) == (2, "contrato")
    assert top["text_rank"] == 1 and top["vector_rank"] is None


async def test_vector_and_hybrid_modes(
    client: httpx.AsyncClient,
    acme: Acme,
    queue: FakeJobQueue,
    db_settings: Settings,
    embeddings: FakeEmbeddingProvider,
) -> None:
    headers = acme.headers(acme.owner)
    await load(client, headers, queue, db_settings, embeddings, "contrato.pdf", "guia.md")

    by_meaning = await search(client, headers, "precio mensual factura", mode="vector")
    hybrid = await search(client, headers, "precio mensual factura")

    assert "PRECIO" in by_meaning["items"][0]["section"]
    top = hybrid["items"][0]
    assert hybrid["mode"] == "hybrid"
    assert "PRECIO" in top["section"]
    assert top["vector_rank"] == 1 and top["text_rank"] == 1
    assert top["score"] == pytest.approx(2 / 61)


async def test_results_can_be_limited_to_some_documents(
    client: httpx.AsyncClient,
    acme: Acme,
    queue: FakeJobQueue,
    db_settings: Settings,
    embeddings: FakeEmbeddingProvider,
) -> None:
    headers = acme.headers(acme.owner)
    ids = await load(client, headers, queue, db_settings, embeddings, "contrato.pdf", "guia.md")

    result = await search(client, headers, "contrato", document_id=ids["guia.md"])

    assert {item["document_id"] for item in result["items"]} <= {ids["guia.md"]}


async def test_another_organization_finds_nothing(
    client: httpx.AsyncClient,
    acme: Acme,
    queue: FakeJobQueue,
    db_settings: Settings,
    embeddings: FakeEmbeddingProvider,
) -> None:
    await load(client, acme.headers(acme.owner), queue, db_settings, embeddings, "contrato.pdf")
    eve = await register(client, "eve@example.com", slug="eves")
    eves_org = (await client.get("/api/v1/organizations", headers=eve.auth)).json()["items"][0]
    headers = {**eve.auth, "X-Organization-Id": eves_org["id"]}

    for mode in ("text", "vector", "hybrid"):
        assert (await search(client, headers, "preaviso precio", mode=mode))["items"] == []


async def test_deleted_documents_are_not_searchable(
    client: httpx.AsyncClient,
    acme: Acme,
    queue: FakeJobQueue,
    db_settings: Settings,
    embeddings: FakeEmbeddingProvider,
) -> None:
    headers = acme.headers(acme.owner)
    ids = await load(client, headers, queue, db_settings, embeddings, "contrato.pdf")

    await client.delete(f"/api/v1/documents/{ids['contrato.pdf']}", headers=headers)

    assert (await search(client, headers, "preaviso"))["items"] == []


async def test_without_an_embedding_model_hybrid_falls_back_to_words(
    client: httpx.AsyncClient,
    acme: Acme,
    queue: FakeJobQueue,
    db_settings: Settings,
    db_app: FastAPI,
) -> None:
    db_app.state.embeddings = None
    headers = acme.headers(acme.owner)
    await client.post(
        "/api/v1/documents",
        files={"file": ("guia.md", (FIXTURES / "guia.md").read_bytes())},
        headers=headers,
    )
    for org, job in queue.sent:
        await process(db_settings, org, job)

    result = await search(client, headers, "acceso a la VPN")

    assert result["mode"] == "text"
    assert result["notes"]
    assert "VPN" in result["items"][0]["content"]


async def test_empty_or_whitespace_query_is_refused(client: httpx.AsyncClient, acme: Acme) -> None:
    empty = await client.get("/api/v1/search", params={"q": ""}, headers=acme.headers(acme.owner))
    blank = await client.get(
        "/api/v1/search", params={"q": "   "}, headers=acme.headers(acme.owner)
    )

    assert empty.status_code == 422
    assert blank.json()["error"]["code"] == "empty_query"
