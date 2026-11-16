"""Where the bytes of uploaded files live. Port (interface) only: the filesystem implementation
is in app/infrastructure/storage/. A future S3-compatible backend implements the same Protocol,
and the `documents` module does not change.

Keys look like `{organization_id}/{uuid}`: two UUIDs and a slash, nothing a user typed. That is
what makes path traversal (`../../etc/passwd`) impossible: a key that does not match is refused.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol
from uuid import UUID

_UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_KEY = re.compile(rf"^{_UUID}/{_UUID}$")


class InvalidStorageKeyError(ValueError):
    """A key that is not `{uuid}/{uuid}`. A programming error, never user input."""


def storage_key(organization_id: UUID, object_id: UUID) -> str:
    return f"{organization_id}/{object_id}"


def ensure_valid_key(key: str) -> str:
    if not _KEY.fullmatch(key):
        raise InvalidStorageKeyError(key)
    return key


class StorageBackend(Protocol):
    def staging_dir(self) -> Path:
        """A local directory for files being received, before they are validated and saved."""
        ...

    async def save(self, key: str, staged_file: Path) -> None:
        """Move a staged file under `key`. The staged file no longer exists afterwards."""
        ...

    def read(self, key: str) -> AsyncIterator[bytes]:
        """The file's bytes, in chunks (never the whole file in memory)."""
        ...

    async def delete(self, key: str) -> None:
        """Remove the file. No error if it is already gone (purging can be retried)."""
        ...

    async def exists(self, key: str) -> bool: ...
