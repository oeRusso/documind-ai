"""Conversations (stage 8) against the real database: history, citations saved, follow-ups,
scope, ratings, privacy (404) and roles (a viewer asks but cannot upload or delete)."""

from typing import Any
from uuid import UUID

import httpx
import pytest

from app.core.config import Settings
from app.jobs import export_feedback
from tests.fakes import FakeLLMProvider
from tests.integration.api_helpers import Acme, LoggedIn
from tests.integration.chat_fixtures import FIXTURES, parse_sse


async def start(
    client: httpx.AsyncClient, acme: Acme, who: LoggedIn, **body: Any
) -> dict[str, Any]:
    response = await client.post("/api/v1/conversations", json=body, headers=acme.headers(who))
    assert response.status_code == 201, response.text
    conversation: dict[str, Any] = response.json()
    return conversation


async def ask(
    client: httpx.AsyncClient, acme: Acme, who: LoggedIn, conversation_id: str, question: str
) -> list[tuple[str, dict[str, Any]]]:
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"question": question},
        headers=acme.headers(who),
    )
    assert response.status_code == 200, response.text
    return parse_sse(response.text)


async def test_asking_saves_the_question_the_answer_and_its_citations(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    conversation = await start(client, acme, acme.viewer)
    events = await ask(client, acme, acme.viewer, conversation["id"], "¿Cuál es el preaviso?")

    name, started = events[0]
    assert name == "message"
    assert started["conversation_id"] == conversation["id"]
    assert [n for n, _ in events[-2:]] == ["citations", "done"]

    detail = (
        await client.get(
            f"/api/v1/conversations/{conversation['id']}", headers=acme.headers(acme.viewer)
        )
    ).json()
    assert detail["title"] == "¿Cuál es el preaviso?"
    question, answer = detail["messages"]
    assert (question["id"], question["role"]) == (started["question_id"], "user")
    assert (answer["id"], answer["role"]) == (started["answer_id"], "assistant")
    assert answer["content"] == "El preaviso es de 30 días [1] y."
    assert answer["status"] == "complete"
    [citation] = answer["citations"]
    assert citation["document_id"] == contrato
    assert citation["marker"] == 1
    assert citation["page_start"] >= 1


async def test_a_follow_up_gives_the_model_the_previous_question(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    conversation = await start(client, acme, acme.viewer)
    await ask(client, acme, acme.viewer, conversation["id"], "¿Cuál es el preaviso?")
    await ask(client, acme, acme.viewer, conversation["id"], "¿Y la multa?")

    user_message = llm.calls[-1][1].content
    assert "<pregunta_anterior>\n¿Cuál es el preaviso?\n</pregunta_anterior>" in user_message
    assert user_message.endswith("<pregunta>\n¿Y la multa?\n</pregunta>")


async def test_a_scope_with_other_documents_finds_no_evidence(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    other = "0190a000-0000-7000-8000-000000000000"
    conversation = await start(client, acme, acme.viewer, document_ids=[other])
    events = await ask(client, acme, acme.viewer, conversation["id"], "¿Cuál es el preaviso?")
    assert events[-1] == ("done", {"no_evidence": True})
    assert llm.calls == []

    # Back to every document: now it answers.
    response = await client.patch(
        f"/api/v1/conversations/{conversation['id']}",
        json={"document_ids": None},
        headers=acme.headers(acme.viewer),
    )
    assert response.json()["document_ids"] is None
    events = await ask(client, acme, acme.viewer, conversation["id"], "¿Cuál es el preaviso?")
    assert events[-1] == ("done", {"no_evidence": False})


async def test_conversations_are_private_even_inside_the_organization(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    conversation = await start(client, acme, acme.viewer)
    url = f"/api/v1/conversations/{conversation['id']}"
    owner = acme.headers(acme.owner)

    assert (await client.get(url, headers=owner)).status_code == 404
    assert (await client.delete(url, headers=owner)).status_code == 404
    response = await client.post(f"{url}/messages", json={"question": "¿Hola?"}, headers=owner)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"
    assert (await client.get("/api/v1/conversations", headers=owner)).json()["items"] == []
    mine = (await client.get("/api/v1/conversations", headers=acme.headers(acme.viewer))).json()
    assert [c["id"] for c in mine["items"]] == [conversation["id"]]


async def test_another_organization_gets_404(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    conversation = await start(client, acme, acme.viewer)
    # bob is viewer in acme and owner of "bobs": with the bobs header it does not exist.
    bobs = (await client.get("/api/v1/organizations", headers=acme.viewer.auth)).json()["items"]
    [own] = [o for o in bobs if o["id"] != acme.id]
    headers = {**acme.viewer.auth, "X-Organization-Id": own["id"]}
    response = await client.get(f"/api/v1/conversations/{conversation['id']}", headers=headers)
    assert response.status_code == 404


async def test_rating_an_answer(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    conversation = await start(client, acme, acme.viewer)
    events = await ask(client, acme, acme.viewer, conversation["id"], "¿Cuál es el preaviso?")
    ids = events[0][1]
    base = f"/api/v1/conversations/{conversation['id']}/messages"
    headers = acme.headers(acme.viewer)

    response = await client.put(
        f"{base}/{ids['answer_id']}/feedback", json={"feedback": "not_helpful"}, headers=headers
    )
    assert response.status_code == 204
    detail = await client.get(f"/api/v1/conversations/{conversation['id']}", headers=headers)
    assert detail.json()["messages"][1]["feedback"] == "not_helpful"

    response = await client.put(
        f"{base}/{ids['question_id']}/feedback", json={"feedback": "helpful"}, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "feedback_only_for_answers"


async def test_deleting_a_conversation_deletes_its_messages(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    conversation = await start(client, acme, acme.viewer)
    await ask(client, acme, acme.viewer, conversation["id"], "¿Cuál es el preaviso?")
    url = f"/api/v1/conversations/{conversation['id']}"
    headers = acme.headers(acme.viewer)
    assert (await client.delete(url, headers=headers)).status_code == 204
    assert (await client.get(url, headers=headers)).status_code == 404


async def test_a_model_failure_is_saved_as_failed(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    llm.fail_after = 1
    conversation = await start(client, acme, acme.viewer)
    events = await ask(client, acme, acme.viewer, conversation["id"], "¿Cuál es el preaviso?")
    assert events[-1][0] == "error"
    detail = (
        await client.get(
            f"/api/v1/conversations/{conversation['id']}", headers=acme.headers(acme.viewer)
        )
    ).json()
    assert detail["messages"][1]["status"] == "failed"
    assert detail["messages"][1]["content"] == "El preaviso"


async def test_a_viewer_asks_but_cannot_upload_or_delete_documents(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    headers = acme.headers(acme.viewer)
    upload = await client.post(
        "/api/v1/documents",
        files={"file": ("otro.pdf", (FIXTURES / "contrato.pdf").read_bytes())},
        headers=headers,
    )
    assert upload.status_code == 403
    assert (
        await client.delete(f"/api/v1/documents/{contrato}", headers=headers)
    ).status_code == 403

    conversation = await start(client, acme, acme.viewer)
    events = await ask(client, acme, acme.viewer, conversation["id"], "¿Cuál es el preaviso?")
    assert events[-1] == ("done", {"no_evidence": False})


async def test_not_helpful_answers_can_be_exported_for_the_dataset(
    client: httpx.AsyncClient,
    acme: Acme,
    contrato: str,
    llm: FakeLLMProvider,
    db_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation = await start(client, acme, acme.viewer)
    events = await ask(client, acme, acme.viewer, conversation["id"], "¿Cuál es el preaviso?")
    await client.put(
        f"/api/v1/conversations/{conversation['id']}/messages/{events[0][1]['answer_id']}/feedback",
        json={"feedback": "not_helpful"},
        headers=acme.headers(acme.viewer),
    )
    monkeypatch.setattr(export_feedback, "get_settings", lambda: db_settings)

    [item] = await export_feedback.export(UUID(acme.id), limit=10)

    assert item["question"] == "¿Cuál es el preaviso?"
    assert item["answer"] == "El preaviso es de 30 días [1] y."
    assert item["cited"][0]["document"] == "contrato"
    assert item["expected"] == {"document": None, "article": None, "anchor": None}
