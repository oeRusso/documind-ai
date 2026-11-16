"""Prompt injection end to end through the API, with a fake model (stage 9).

What the model receives when the organization has malicious documents: no hidden text, no fake
tags, and the fixed rules. Whether the REAL model obeys is measured by evaluation.eval_injection.
"""

import re
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.core.config import Settings
from app.modules.ingestion.presentation.tasks import process
from app.modules.knowledge.application.prompt import SYSTEM_PROMPT
from evaluation.injection import ATTACKS, build_file
from tests.fakes import FakeEmbeddingProvider, FakeJobQueue, FakeLLMProvider
from tests.integration.api_helpers import Acme
from tests.integration.chat_fixtures import configure


async def test_the_model_gets_no_hidden_text_and_no_fake_tags(
    client: httpx.AsyncClient,
    acme: Acme,
    queue: FakeJobQueue,
    db_settings: Settings,
    embeddings: FakeEmbeddingProvider,
    db_app: FastAPI,
    tmp_path: Path,
) -> None:
    llm = FakeLLMProvider(["Respuesta [1]."])
    db_app.state.llm = llm
    configure(db_app, rag_min_score=0.0)
    for attack in ATTACKS:
        path = build_file(attack, tmp_path)
        response = await client.post(
            "/api/v1/documents",
            files={"file": (path.name, path.read_bytes())},
            headers=acme.headers(acme.owner),
        )
        assert response.status_code == 201, response.text
    for org, job in queue.sent:
        assert await process(db_settings, org, job, embeddings=embeddings) == "ready"

    for attack in ATTACKS:
        response = await client.post(
            "/api/v1/chat", json={"question": attack.question}, headers=acme.headers(acme.viewer)
        )
        assert response.status_code == 200
    assert len(llm.calls) == len(ATTACKS)
    sent = "\n".join(m.content for call in llm.calls for m in call)
    assert "canario-blanco-9" not in sent.lower()  # the hidden order never left the PDF
    for system, user in llm.calls:
        assert system.content == SYSTEM_PROMPT
        assert len(re.findall(r"<pregunta>", user.content)) == 1
        assert len(re.findall(r"</fragmentos>", user.content)) == 1
