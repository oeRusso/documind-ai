"""Receive an uploaded file into the staging directory, in chunks.

While copying, it counts bytes (to stop as soon as the limit is passed) and computes the
SHA-256 (to detect duplicates), so the file is read once and never held whole in memory.
"""

import asyncio
import hashlib
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

from app.modules.documents.domain.entities import StagedUpload, clean_filename
from app.modules.documents.domain.errors import EmptyFileError, FileTooLargeError

CHUNK_SIZE = 256 * 1024


class ReadableUpload(Protocol):
    """What we need from FastAPI's UploadFile (kept generic so tests can pass anything)."""

    filename: str | None

    async def read(self, size: int = -1) -> bytes: ...


@asynccontextmanager
async def staged_upload(
    upload: ReadableUpload, staging_dir: Path, *, max_bytes: int
) -> AsyncIterator[StagedUpload]:
    """`async with staged_upload(...) as staged:` gives the received file on disk.

    On the way out the staged file is deleted if nobody moved it (validation failed, the
    request errored): no leftovers in the staging directory.
    """
    path = staging_dir / secrets.token_hex(16)
    digest = hashlib.sha256()
    size = 0
    try:
        handle = await asyncio.to_thread(path.open, "xb")
        try:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLargeError(max_bytes // (1024 * 1024))
                digest.update(chunk)
                await asyncio.to_thread(handle.write, chunk)
        finally:
            await asyncio.to_thread(handle.close)
        if size == 0:
            raise EmptyFileError()
        yield StagedUpload(
            path=path,
            filename=clean_filename(upload.filename),
            size_bytes=size,
            sha256=digest.hexdigest(),
        )
    finally:
        await asyncio.to_thread(path.unlink, missing_ok=True)
