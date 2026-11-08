"""Filesystem storage and receiving uploads: random names, no path traversal, size limit."""

import hashlib
from pathlib import Path

import pytest

from app.infrastructure.storage.filesystem import FilesystemStorage
from app.modules.documents.domain.entities import clean_filename, title_from_filename
from app.modules.documents.domain.errors import EmptyFileError, FileTooLargeError
from app.modules.documents.infrastructure.uploads import staged_upload
from app.shared.ids import new_id
from app.shared.storage import InvalidStorageKeyError, storage_key


class FakeUpload:
    def __init__(self, data: bytes, filename: str | None = "a.txt") -> None:
        self._data = data
        self.filename = filename

    async def read(self, size: int = -1) -> bytes:
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk


async def collect(storage: FilesystemStorage, key: str) -> bytes:
    return b"".join([chunk async for chunk in storage.read(key)])


async def test_save_read_and_delete(tmp_path: Path) -> None:
    storage = FilesystemStorage(tmp_path)
    staged = storage.staging_dir() / "incoming"
    staged.write_bytes(b"contenido")
    key = storage_key(new_id(), new_id())

    await storage.save(key, staged)

    assert not staged.exists()
    assert await collect(storage, key) == b"contenido"
    assert (tmp_path / key).stat().st_mode & 0o777 == 0o600
    await storage.delete(key)
    await storage.delete(key)  # twice: no error (the purge can be retried)
    assert not await storage.exists(key)


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "/etc/passwd",
        f"{new_id()}/../../secret",
        f"{new_id()}",
        f"{new_id()}/{new_id()}/extra",
        "contrato.pdf",
    ],
)
async def test_keys_that_could_escape_the_root_are_refused(tmp_path: Path, key: str) -> None:
    storage = FilesystemStorage(tmp_path)

    with pytest.raises(InvalidStorageKeyError):
        await storage.exists(key)
    with pytest.raises(InvalidStorageKeyError):
        await storage.delete(key)


async def test_staged_upload_counts_hashes_and_cleans_up(tmp_path: Path) -> None:
    data = b"x" * 600_000  # several chunks

    async with staged_upload(
        FakeUpload(data, "C:\\Users\\ana\\nota.txt"), tmp_path, max_bytes=10**6
    ) as staged:
        assert staged.size_bytes == len(data)
        assert staged.sha256 == hashlib.sha256(data).hexdigest()
        assert staged.filename == "nota.txt"  # only the last part of what the browser sent
        assert staged.path.read_bytes() == data

    assert list(tmp_path.iterdir()) == []  # nobody moved it: deleted on the way out


async def test_staged_upload_stops_at_the_limit(tmp_path: Path) -> None:
    with pytest.raises(FileTooLargeError):
        async with staged_upload(FakeUpload(b"x" * 2_000_001), tmp_path, max_bytes=2_000_000):
            pass

    assert list(tmp_path.iterdir()) == []


async def test_empty_upload_is_refused(tmp_path: Path) -> None:
    with pytest.raises(EmptyFileError):
        async with staged_upload(FakeUpload(b""), tmp_path, max_bytes=100):
            pass


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\fakepath\\informe final.pdf", "informe final.pdf"),
        ("con\x00trol\n.pdf", "control.pdf"),
        ("", "documento"),
        (None, "documento"),
    ],
)
def test_clean_filename(raw: str | None, clean: str) -> None:
    assert clean_filename(raw) == clean


def test_title_from_filename() -> None:
    assert title_from_filename("contrato_proveedor_X.pdf") == "contrato proveedor X"
    assert title_from_filename(".pdf") == ".pdf"
