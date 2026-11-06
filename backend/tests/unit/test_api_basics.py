"""HTTP behaviour that needs no database: health, request_id and the uniform error format."""

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.core.request_context import REQUEST_ID_HEADER


async def test_health_is_ok_without_database(offline_client: httpx.AsyncClient) -> None:
    response = await offline_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_is_503_when_database_is_down(offline_client: httpx.AsyncClient) -> None:
    response = await offline_client.get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


async def test_every_response_has_a_request_id(offline_client: httpx.AsyncClient) -> None:
    response = await offline_client.get("/health")

    assert len(response.headers[REQUEST_ID_HEADER]) == 32


async def test_incoming_request_id_is_kept(offline_client: httpx.AsyncClient) -> None:
    response = await offline_client.get("/health", headers={REQUEST_ID_HEADER: "abc-123"})

    assert response.headers[REQUEST_ID_HEADER] == "abc-123"


async def test_unsafe_incoming_request_id_is_replaced(offline_client: httpx.AsyncClient) -> None:
    response = await offline_client.get("/health", headers={REQUEST_ID_HEADER: "bad id\nforged"})

    assert response.headers[REQUEST_ID_HEADER] != "bad id\nforged"


async def test_unknown_route_uses_error_format(offline_client: httpx.AsyncClient) -> None:
    response = await offline_client.get("/api/v1/nope", headers={REQUEST_ID_HEADER: "req-1"})

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Recurso no encontrado", "request_id": "req-1"}
    }


class _Payload(BaseModel):
    name: str = Field(min_length=1)
    slug: str


async def test_validation_error_uses_error_format(
    offline_app: FastAPI, offline_client: httpx.AsyncClient
) -> None:
    @offline_app.post("/_test/validation")
    async def _endpoint(body: _Payload) -> None: ...

    response = await offline_client.post("/_test/validation", json={"name": ""})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert {tuple(detail["loc"]) for detail in error["details"]} == {
        ("body", "name"),
        ("body", "slug"),
    }


async def test_unexpected_error_is_a_generic_500(
    offline_app: FastAPI, offline_client: httpx.AsyncClient
) -> None:
    @offline_app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    response = await offline_client.get("/boom")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert "secret" not in error["message"]
    assert error["request_id"] == response.headers[REQUEST_ID_HEADER]
