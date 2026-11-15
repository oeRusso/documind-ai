"""GET /analytics/overview (stage 10): numbers of the active organization, admins only."""

import httpx

from tests.fakes import FakeLLMProvider
from tests.integration.api_helpers import Acme
from tests.integration.chat_fixtures import configure, parse_sse


async def ask(client: httpx.AsyncClient, acme: Acme, question: str) -> None:
    headers = acme.headers(acme.viewer)
    conversation = (await client.post("/api/v1/conversations", json={}, headers=headers)).json()
    response = await client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"question": question},
        headers=headers,
    )
    assert response.status_code == 200
    parse_sse(response.text)


async def test_admins_see_usage_and_the_questions_without_answer(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider, db_app: object
) -> None:
    await ask(client, acme, "¿Cuál es el preaviso?")
    configure(db_app, rag_min_score=0.99)  # type: ignore[arg-type]
    await ask(client, acme, "¿Quién ganó el mundial de 1986?")

    response = await client.get(
        "/api/v1/analytics/overview", params={"days": 7}, headers=acme.headers(acme.admin)
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["days"] == 7
    assert len(data["questions_by_day"]) == 7
    assert data["questions"] == 2
    assert sum(d["questions"] for d in data["questions_by_day"]) == 2
    assert (data["answered"], data["no_evidence"], data["people"]) == (1, 1, 1)
    assert data["documents_ready"] == 1
    assert [u["question"] for u in data["unanswered"]] == ["¿Quién ganó el mundial de 1986?"]
    assert "user" not in str(data["unanswered"])  # no author


async def test_members_and_viewers_cannot_see_analytics(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    response = await client.get("/api/v1/analytics/overview", headers=acme.headers(acme.viewer))
    assert response.status_code == 403


async def test_numbers_are_per_organization(
    client: httpx.AsyncClient, acme: Acme, contrato: str, llm: FakeLLMProvider
) -> None:
    await ask(client, acme, "¿Cuál es el preaviso?")
    # carla is admin of acme and owner of her own organization, which has nothing.
    orgs = (await client.get("/api/v1/organizations", headers=acme.admin.auth)).json()["items"]
    [own] = [o for o in orgs if o["id"] != acme.id]
    headers = {**acme.admin.auth, "X-Organization-Id": own["id"]}
    data = (await client.get("/api/v1/analytics/overview", headers=headers)).json()
    assert (data["questions"], data["documents_ready"], data["unanswered"]) == (0, 0, [])
