"""Documents over HTTP, against PostgreSQL with RLS and a real storage directory (stage 4).

Stage criteria:
1. An .exe renamed to .pdf is refused.
2. Another organization gets 404 (not 403) for a document.
3. Uploading the same file twice warns about the duplicate instead of creating two documents.
"""

from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.infrastructure.database.tenant import SqlTenantContext
from app.infrastructure.storage.filesystem import FilesystemStorage
from app.main import create_app
from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
from app.modules.documents.application.delete_document import PurgeDeletedDocuments
from app.modules.documents.infrastructure.sql_repository import (
    SqlDocumentRepository,
    SqlPurgeQueue,
)
from app.shared.ids import utc_now
from tests import sample_files
from tests.integration.api_helpers import Acme, LoggedIn, add_member, register, user_id

PDF = sample_files.pdf(2, "Contrato con el proveedor X")
PDF_PASSWORD = "clave"  # pragma: allowlist secret


async def upload(
    client: httpx.AsyncClient,
    acme: Acme,
    who: LoggedIn,
    data: bytes = PDF,
    filename: str = "contrato.pdf",
    path: str = "/api/v1/documents",
) -> httpx.Response:
    return await client.post(
        path,
        files={"file": (filename, data, "application/octet-stream")},
        headers=acme.headers(who),
    )


async def uploaded(client: httpx.AsyncClient, acme: Acme, **kwargs: Any) -> dict[str, Any]:
    response = await upload(client, acme, kwargs.pop("who", acme.owner), **kwargs)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def stored_files(settings: Settings) -> list[Path]:
    return [
        p for p in settings.storage_path.rglob("*") if p.is_file() and ".staging" not in p.parts
    ]


# --- Upload ---------------------------------------------------------------------------------


async def test_upload_list_detail_and_download(client: httpx.AsyncClient, acme: Acme) -> None:
    created = await uploaded(client, acme, filename="Contrato_Proveedor X.pdf")

    assert created["title"] == "Contrato Proveedor X"
    assert created["status"] == "pending"
    version = created["latest_version"]
    assert (version["number"], version["kind"], version["page_count"]) == (1, "pdf", 2)
    assert version["size_bytes"] == len(PDF)

    listed = await client.get("/api/v1/documents", headers=acme.headers(acme.viewer))
    assert listed.status_code == 200
    [item] = listed.json()["items"]
    assert item["id"] == created["id"]
    assert item["created_by_email"] == "ana@example.com"

    detail = await client.get(
        f"/api/v1/documents/{created['id']}", headers=acme.headers(acme.viewer)
    )
    assert detail.json()["versions"][0]["uploaded_by_email"] == "ana@example.com"

    download = await client.get(
        f"/api/v1/documents/{created['id']}/download", headers=acme.headers(acme.viewer)
    )
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert "Contrato_Proveedor%20X.pdf" in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"


async def test_files_are_stored_under_random_names_per_organization(
    client: httpx.AsyncClient, acme: Acme, db_settings: Settings
) -> None:
    before = set(stored_files(db_settings))
    await uploaded(client, acme, filename="secreto.pdf")

    [new_file] = set(stored_files(db_settings)) - before
    assert new_file.parent.name == acme.id
    assert "secreto" not in new_file.name
    assert new_file.read_bytes() == PDF


async def test_an_exe_renamed_to_pdf_is_refused(
    client: httpx.AsyncClient, acme: Acme, db_settings: Settings
) -> None:
    before = set(stored_files(db_settings))

    response = await upload(client, acme, acme.owner, sample_files.windows_exe(), "factura.pdf")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"
    assert set(stored_files(db_settings)) == before
    staging = db_settings.storage_path / ".staging"
    assert list(staging.iterdir()) == []  # nothing left behind
    listed = await client.get("/api/v1/documents", headers=acme.headers(acme.owner))
    assert listed.json()["items"] == []


@pytest.mark.parametrize(
    ("data", "filename", "status_code", "code"),
    [
        (sample_files.pdf(password=PDF_PASSWORD), "a.pdf", 422, "encrypted_file"),
        (sample_files.broken_pdf(), "a.pdf", 422, "corrupt_file"),
        (PDF, "a.txt", 415, "file_type_mismatch"),
        (b"", "vacio.txt", 422, "empty_file"),
    ],
)
async def test_invalid_files_are_refused(
    client: httpx.AsyncClient,
    acme: Acme,
    data: bytes,
    filename: str,
    status_code: int,
    code: str,
) -> None:
    response = await upload(client, acme, acme.owner, data, filename)

    assert response.status_code == status_code, response.text
    assert response.json()["error"]["code"] == code


async def test_same_file_twice_is_reported_as_duplicate(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    first = await uploaded(client, acme)

    again = await upload(client, acme, acme.admin, PDF, "copia.pdf")

    assert again.status_code == 409
    error = again.json()["error"]
    assert error["code"] == "duplicate_document"
    assert error["details"] == [{"document_id": first["id"]}]
    listed = await client.get("/api/v1/documents", headers=acme.headers(acme.owner))
    assert len(listed.json()["items"]) == 1


async def test_viewer_cannot_upload(client: httpx.AsyncClient, acme: Acme) -> None:
    response = await upload(client, acme, acme.viewer)

    assert response.status_code == 403


# --- Isolation ------------------------------------------------------------------------------


async def test_another_organization_gets_404_for_everything(
    client: httpx.AsyncClient, acme: Acme
) -> None:
    created = await uploaded(client, acme)
    eve = await register(client, "eve@example.com", slug="eves")
    eves_org = (await client.get("/api/v1/organizations", headers=eve.auth)).json()["items"][0]
    headers = {**eve.auth, "X-Organization-Id": eves_org["id"]}
    doc = f"/api/v1/documents/{created['id']}"

    responses = [
        await client.get(doc, headers=headers),
        await client.get(f"{doc}/download", headers=headers),
        await client.delete(doc, headers=headers),
        await client.post(
            f"{doc}/versions", files={"file": ("v2.pdf", sample_files.pdf(3))}, headers=headers
        ),
    ]

    assert [r.status_code for r in responses] == [404, 404, 404, 404]
    assert {r.json()["error"]["code"] for r in responses} == {"document_not_found"}
    listed = await client.get("/api/v1/documents", headers=headers)
    assert listed.json()["items"] == []
    # And the same file in eve's organization is not a duplicate: each has its own copy.
    own = await client.post(
        "/api/v1/documents", files={"file": ("contrato.pdf", PDF)}, headers=headers
    )
    assert own.status_code == 201


# --- Versions -------------------------------------------------------------------------------


async def test_new_version(client: httpx.AsyncClient, acme: Acme) -> None:
    created = await uploaded(client, acme)
    path = f"/api/v1/documents/{created['id']}/versions"

    response = await upload(client, acme, acme.admin, sample_files.pdf(5), "corregido.pdf", path)

    assert response.status_code == 201, response.text
    assert response.json()["latest_version"]["number"] == 2
    detail = (
        await client.get(f"/api/v1/documents/{created['id']}", headers=acme.headers(acme.owner))
    ).json()
    assert [v["number"] for v in detail["versions"]] == [2, 1]
    old = await client.get(
        f"/api/v1/documents/{created['id']}/download?version=1", headers=acme.headers(acme.owner)
    )
    assert old.content == PDF


# --- Delete ---------------------------------------------------------------------------------


async def test_member_deletes_own_documents_only(client: httpx.AsyncClient, acme: Acme) -> None:
    mario = await register(client, "mario@example.com", slug="marios")
    await add_member(acme.id, await user_id(client, mario), "member")
    by_owner = await uploaded(client, acme)
    by_mario = await uploaded(client, acme, who=mario, data=sample_files.pdf(1), filename="m.pdf")

    refused = await client.delete(
        f"/api/v1/documents/{by_owner['id']}", headers=acme.headers(mario)
    )
    deleted = await client.delete(
        f"/api/v1/documents/{by_mario['id']}", headers=acme.headers(mario)
    )

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "cannot_delete_document"
    assert deleted.status_code == 204
    gone = await client.get(f"/api/v1/documents/{by_mario['id']}", headers=acme.headers(mario))
    assert gone.status_code == 404


async def test_deleted_files_are_purged_after_the_waiting_period(
    client: httpx.AsyncClient, acme: Acme, db_settings: Settings
) -> None:
    created = await uploaded(client, acme)
    before = set(stored_files(db_settings))
    await client.delete(f"/api/v1/documents/{created['id']}", headers=acme.headers(acme.owner))
    assert set(stored_files(db_settings)) == before  # still there: backups may need it

    engine = create_async_engine(str(db_settings.database_url), poolclass=NullPool)
    later = utc_now() + timedelta(days=db_settings.document_purge_days, minutes=1)
    try:
        async with AsyncSession(engine) as session, session.begin():
            purged = await PurgeDeletedDocuments(
                SqlPurgeQueue(session),
                SqlDocumentRepository(session),
                FilesystemStorage(db_settings.storage_path),
                SqlTenantContext(session),
                RecordAuditEvent(SqlAuditLogRepository(session)),
                clock=lambda: later,
            ).execute()
    finally:
        await engine.dispose()

    assert purged == 1
    assert len(set(stored_files(db_settings))) == len(before) - 1
    # The same file can be uploaded again as a brand new document.
    again = await upload(client, acme, acme.owner)
    assert again.status_code == 201


# --- Size limits ----------------------------------------------------------------------------


@pytest.fixture
async def small_limit_client(db_settings: Settings) -> Any:
    app: FastAPI = create_app(db_settings.model_copy(update={"max_upload_mb": 1}))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as http_client:
        yield http_client
    await app.state.engine.dispose()


async def test_file_over_the_limit_is_refused(small_limit_client: httpx.AsyncClient) -> None:
    owner = await register(small_limit_client, "big@example.com", slug="bigs")
    org = (await small_limit_client.get("/api/v1/organizations", headers=owner.auth)).json()
    headers = {**owner.auth, "X-Organization-Id": org["items"][0]["id"]}
    just_over = b"a" * (1024 * 1024 + 1)  # within the multipart allowance, over the file limit
    far_over = b"a" * (3 * 1024 * 1024)  # rejected by Content-Length before reading the body

    near = await small_limit_client.post(
        "/api/v1/documents", files={"file": ("a.txt", just_over)}, headers=headers
    )
    far = await small_limit_client.post(
        "/api/v1/documents", files={"file": ("a.txt", far_over)}, headers=headers
    )

    assert (near.status_code, near.json()["error"]["code"]) == (413, "file_too_large")
    assert (far.status_code, far.json()["error"]["code"]) == (413, "payload_too_large")
