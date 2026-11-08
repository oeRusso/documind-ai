"""The processing pipeline against PostgreSQL with RLS (stage 5).

Uploads go through the API; the worker's code (`tasks.process`, the same function the Celery
task calls) runs directly here, without a broker.
"""

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.modules.ingestion.presentation.tasks import process
from tests.db import migrator_test_url
from tests.fakes import FakeJobQueue
from tests.integration.api_helpers import Acme, register

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture
def queue(db_app: FastAPI) -> FakeJobQueue:
    fake = FakeJobQueue()
    db_app.state.job_queue = fake
    return fake


async def upload_fixture(client: httpx.AsyncClient, acme: Acme, name: str) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/documents",
        files={"file": (name, (FIXTURES / name).read_bytes())},
        headers=acme.headers(acme.owner),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def run_worker(settings: Settings, queue: FakeJobQueue) -> list[str]:
    outcomes = [await process(settings, org, job) for org, job in queue.sent]
    queue.sent.clear()
    return outcomes


async def test_upload_is_queued_and_the_worker_produces_chunks(
    client: httpx.AsyncClient, acme: Acme, queue: FakeJobQueue, db_settings: Settings
) -> None:
    created = await upload_fixture(client, acme, "contrato.pdf")
    doc = f"/api/v1/documents/{created['id']}"

    pending = (await client.get(f"{doc}/processing", headers=acme.headers(acme.viewer))).json()
    assert pending["status"] == "pending"
    assert [str(org) for org, _ in queue.sent] == [acme.id]

    assert await run_worker(db_settings, queue) == ["ready"]

    done = (await client.get(f"{doc}/processing", headers=acme.headers(acme.viewer))).json()
    assert (done["status"], done["pages_total"], done["pages_done"]) == ("ready", 3, 3)
    assert done["chunk_count"] == 3
    detail = (await client.get(doc, headers=acme.headers(acme.viewer))).json()
    assert detail["status"] == "ready"

    chunks = (await client.get(f"{doc}/chunks", headers=acme.headers(acme.viewer))).json()
    plazo = next(c for c in chunks["items"] if "PLAZO" in (c["section"] or ""))
    assert "preaviso de treinta (30) días" in plazo["content"]
    assert (plazo["page_start"], plazo["page_end"]) == (2, 2)


async def test_chunks_are_paginated(
    client: httpx.AsyncClient, acme: Acme, queue: FakeJobQueue, db_settings: Settings
) -> None:
    created = await upload_fixture(client, acme, "contrato.pdf")
    await run_worker(db_settings, queue)
    doc = f"/api/v1/documents/{created['id']}"

    first = (await client.get(f"{doc}/chunks?limit=2", headers=acme.headers(acme.owner))).json()
    rest = (
        await client.get(
            f"{doc}/chunks?limit=2&cursor={first['next_cursor']}", headers=acme.headers(acme.owner)
        )
    ).json()

    assert [c["position"] for c in first["items"] + rest["items"]] == [0, 1, 2]
    assert rest["next_cursor"] is None


async def test_reprocessing_replaces_chunks_instead_of_adding(
    client: httpx.AsyncClient, acme: Acme, queue: FakeJobQueue, db_settings: Settings
) -> None:
    created = await upload_fixture(client, acme, "guia.md")
    await run_worker(db_settings, queue)
    doc = f"/api/v1/documents/{created['id']}"

    viewer = await client.post(f"{doc}/reprocess", headers=acme.headers(acme.viewer))
    again = await client.post(f"{doc}/reprocess", headers=acme.headers(acme.owner))
    assert (viewer.status_code, again.status_code) == (403, 202)
    await run_worker(db_settings, queue)

    chunks = (await client.get(f"{doc}/chunks", headers=acme.headers(acme.owner))).json()["items"]
    assert [c["position"] for c in chunks] == [0, 1, 2]


async def test_a_new_version_replaces_the_old_chunks(
    client: httpx.AsyncClient, acme: Acme, queue: FakeJobQueue, db_settings: Settings
) -> None:
    created = await upload_fixture(client, acme, "guia.md")
    await run_worker(db_settings, queue)
    doc = f"/api/v1/documents/{created['id']}"

    new = await client.post(
        f"{doc}/versions",
        files={"file": ("guia.md", b"# Nueva guia\n\nTodo cambio.\n")},
        headers=acme.headers(acme.owner),
    )
    assert new.status_code == 201
    await run_worker(db_settings, queue)

    chunks = (await client.get(f"{doc}/chunks", headers=acme.headers(acme.owner))).json()["items"]
    assert [(c["section"], c["content"]) for c in chunks] == [("Nueva guia", "Todo cambio.")]


async def test_another_organization_cannot_see_processing_nor_chunks(
    client: httpx.AsyncClient, acme: Acme, queue: FakeJobQueue, db_settings: Settings
) -> None:
    created = await upload_fixture(client, acme, "guia.md")
    await run_worker(db_settings, queue)
    eve = await register(client, "eve@example.com", slug="eves")
    eves_org = (await client.get("/api/v1/organizations", headers=eve.auth)).json()["items"][0]
    headers = {**eve.auth, "X-Organization-Id": eves_org["id"]}
    doc = f"/api/v1/documents/{created['id']}"

    responses = [
        await client.get(f"{doc}/processing", headers=headers),
        await client.get(f"{doc}/chunks", headers=headers),
        await client.post(f"{doc}/reprocess", headers=headers),
    ]

    assert [r.status_code for r in responses] == [404, 404, 404]


async def test_a_job_from_a_forged_task_for_another_organization_is_ignored(
    client: httpx.AsyncClient, acme: Acme, queue: FakeJobQueue, db_settings: Settings
) -> None:
    await upload_fixture(client, acme, "guia.md")
    [(_, job_id)] = queue.sent
    eve = await register(client, "eve@example.com", slug="eves")
    eves_org = (await client.get("/api/v1/organizations", headers=eve.auth)).json()["items"][0]

    # A task that says "organization of eve" for acme's job: RLS hides the job, nothing happens.
    assert await process(db_settings, UUID(eves_org["id"]), job_id) == "skipped"
    assert await run_worker(db_settings, queue) == ["ready"]


async def expire_claim(job_id: UUID, organization_id: str) -> None:
    """What a killed worker leaves behind: a running job whose claim already expired."""
    engine = create_async_engine(migrator_test_url(), poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_org', :org, true)"), {"org": organization_id}
        )
        await connection.execute(
            text(
                "UPDATE processing_jobs SET status = 'extracting', attempts = 1, "
                "locked_until = now() - interval '1 minute' WHERE id = :id"
            ),
            {"id": job_id},
        )
    await engine.dispose()


async def test_a_job_left_by_a_killed_worker_is_requeued_and_finished_once(
    client: httpx.AsyncClient, acme: Acme, queue: FakeJobQueue, db_settings: Settings
) -> None:
    created = await upload_fixture(client, acme, "contrato.pdf")
    [(_, job_id)] = queue.sent
    queue.sent.clear()
    await expire_claim(job_id, acme.id)
    doc = f"/api/v1/documents/{created['id']}"

    # Looking at the document notices the dead claim and queues the job again.
    status = (await client.get(f"{doc}/processing", headers=acme.headers(acme.owner))).json()
    assert status["status"] == "extracting"
    assert [job for _, job in queue.sent] == [job_id]

    # Both the requeued message and the original redelivered one arrive: only one works.
    queue.sent.append(queue.sent[0])
    assert sorted(await run_worker(db_settings, queue)) == ["ready", "skipped"]

    chunks = (await client.get(f"{doc}/chunks", headers=acme.headers(acme.owner))).json()["items"]
    assert len(chunks) == 3
    done = (await client.get(f"{doc}/processing", headers=acme.headers(acme.owner))).json()
    assert (done["status"], done["attempts"]) == ("ready", 2)
    assert queue.sent == []  # a finished job is never requeued


async def test_an_unreadable_file_fails_with_a_message(
    client: httpx.AsyncClient, acme: Acme, queue: FakeJobQueue, db_settings: Settings
) -> None:
    created = await upload_fixture(client, acme, "guia.md")
    [(_, job_id)] = queue.sent
    # Break the stored file behind the API's back (a disk problem, a bad copy...).
    for path in db_settings.storage_path.rglob("*"):
        if path.is_file() and acme.id in path.parts and b"incorporaci" in path.read_bytes():
            path.unlink()

    outcome = await run_worker(db_settings, queue)

    doc = f"/api/v1/documents/{created['id']}"
    status = (await client.get(f"{doc}/processing", headers=acme.headers(acme.owner))).json()
    assert outcome == ["failed"]
    assert (status["status"], status["error"]) == ("failed", "No se encontró el archivo guardado")
    detail = (await client.get(doc, headers=acme.headers(acme.owner))).json()
    assert detail["status"] == "failed"
    assert job_id
