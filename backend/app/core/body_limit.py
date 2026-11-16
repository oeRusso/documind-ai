"""Refuse oversized request bodies before reading them.

FastAPI parses an upload before the endpoint runs, so the endpoint alone could not stop a
2 GB upload from filling the disk first. This middleware looks at Content-Length and answers
413 right away. Bodies without a length (chunked) are refused with 411: browsers always send
it for uploads, and the server (uvicorn) rejects a body longer than the length it announced.
The endpoint still counts the real bytes of the file (see documents/infrastructure/uploads.py).
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status

from app.core.exceptions import error_response

# Room for the multipart envelope around the file (boundaries, headers, small fields).
MULTIPART_OVERHEAD = 1024 * 1024
_WITH_BODY = {"POST", "PUT", "PATCH"}


def body_limit_middleware(
    max_body_bytes: int,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method in _WITH_BODY:
            length = request.headers.get("content-length")
            if length is None:
                if "chunked" in request.headers.get("transfer-encoding", "").lower():
                    return error_response(
                        status.HTTP_411_LENGTH_REQUIRED,
                        "length_required",
                        "Falta el tamaño del pedido (Content-Length)",
                    )
            elif not length.isdigit() or int(length) > max_body_bytes:
                return error_response(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "payload_too_large",
                    "El archivo es demasiado grande",
                )
        return await call_next(request)

    return middleware
