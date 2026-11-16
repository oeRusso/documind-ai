"""StorageBackend on the local filesystem (a Docker/Podman volume).

Layout under `root`:
    .staging/<random>            files being received (same disk, so saving is a rename)
    <organization_id>/<uuid>     saved files, readable only by the app's user (0600)
"""

import asyncio
import os
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from app.shared.storage import InvalidStorageKeyError, ensure_valid_key

CHUNK_SIZE = 256 * 1024


class FilesystemStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def staging_dir(self) -> Path:
        path = self._root / ".staging"
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return path

    def _path(self, key: str) -> Path:
        path = (self._root / ensure_valid_key(key)).resolve()
        # Belt and braces: the key format already rules out "..", but never leave the root.
        if not path.is_relative_to(self._root):
            raise InvalidStorageKeyError(key)
        return path

    async def save(self, key: str, staged_file: Path) -> None:
        target = self._path(key)

        def move() -> None:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(staged_file, 0o600)
            # Same filesystem: an atomic rename. Otherwise (tests, other mounts): copy + delete.
            shutil.move(staged_file, target)

        await asyncio.to_thread(move)

    async def read(self, key: str) -> AsyncIterator[bytes]:
        path = self._path(key)
        handle = await asyncio.to_thread(path.open, "rb")
        try:
            while chunk := await asyncio.to_thread(handle.read, CHUNK_SIZE):
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)

    @asynccontextmanager
    async def local_copy(self, key: str) -> AsyncIterator[Path]:
        """The file on local disk, for libraries that need a path (PyMuPDF). Here it is the
        stored file itself: nothing to copy, and the caller must not modify it."""
        path = self._path(key)
        if not await asyncio.to_thread(path.is_file):
            raise FileNotFoundError(key)
        yield path

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, missing_ok=True)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).is_file)
