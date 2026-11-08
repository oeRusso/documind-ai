"""The real type of a file, by its bytes (stage 4 criterion: an .exe renamed to .pdf is refused)."""

from pathlib import Path

import pytest

from app.modules.documents.domain.entities import FileKind
from app.modules.documents.domain.errors import (
    CorruptFileError,
    EmptyFileError,
    EncryptedFileError,
    FileTypeMismatchError,
    TooManyPagesError,
    UnsupportedFileTypeError,
)
from app.modules.documents.infrastructure.file_inspector import LibmagicFileInspector
from tests import sample_files

inspector = LibmagicFileInspector(max_pages=10)
PDF_PASSWORD = "secreta"  # pragma: allowlist secret


def write(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "upload"  # the stored name never comes from the user
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    ("filename", "data", "kind", "pages"),
    [
        ("contrato.pdf", sample_files.pdf(3), FileKind.PDF, 3),
        ("CONTRATO.PDF", sample_files.pdf(1), FileKind.PDF, 1),
        ("restringido.pdf", sample_files.pdf_with_owner_password_only(), FileKind.PDF, 1),
        ("informe.docx", sample_files.docx(pages=4), FileKind.DOCX, 4),
        ("informe.docx", sample_files.docx(), FileKind.DOCX, None),
        ("notas.txt", "Año fiscal, cláusula 5.\n".encode(), FileKind.TEXT, None),
        ("guia.md", b"# Titulo\n\nTexto *importante*.\n", FileKind.MARKDOWN, None),
    ],
)
def test_accepts_supported_files(
    tmp_path: Path, filename: str, data: bytes, kind: FileKind, pages: int | None
) -> None:
    inspected = inspector.inspect(write(tmp_path, data), filename)

    assert (inspected.kind, inspected.page_count) == (kind, pages)


def test_an_exe_renamed_to_pdf_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        inspector.inspect(write(tmp_path, sample_files.windows_exe()), "factura.pdf")


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("contrato.txt", sample_files.pdf()),  # a real PDF with the wrong extension
        ("contrato.docx", sample_files.pdf()),
        ("notas.pdf", b"solo texto"),
        ("contrato", sample_files.pdf()),  # no extension at all
    ],
)
def test_extension_must_match_the_content(tmp_path: Path, filename: str, data: bytes) -> None:
    with pytest.raises(FileTypeMismatchError):
        inspector.inspect(write(tmp_path, data), filename)


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("datos.txt", bytes(range(256)) * 8),  # binary
        ("informe.docx", sample_files.plain_zip()),  # a ZIP, but not a Word document
        ("planilla.xlsx", sample_files.plain_zip()),
        ("foto.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64),
    ],
)
def test_other_types_are_refused(tmp_path: Path, filename: str, data: bytes) -> None:
    with pytest.raises((UnsupportedFileTypeError, FileTypeMismatchError)):
        inspector.inspect(write(tmp_path, data), filename)


def test_password_protected_pdf_is_refused(tmp_path: Path) -> None:
    with pytest.raises(EncryptedFileError):
        inspector.inspect(write(tmp_path, sample_files.pdf(password=PDF_PASSWORD)), "a.pdf")


def test_broken_pdf_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CorruptFileError):
        inspector.inspect(write(tmp_path, sample_files.broken_pdf()), "a.pdf")


def test_too_many_pages_is_refused(tmp_path: Path) -> None:
    with pytest.raises(TooManyPagesError, match="10 páginas"):
        inspector.inspect(write(tmp_path, sample_files.pdf(11)), "largo.pdf")
    with pytest.raises(TooManyPagesError):
        inspector.inspect(write(tmp_path, sample_files.docx(pages=99)), "largo.docx")


def test_zip_bomb_is_refused(tmp_path: Path) -> None:
    strict = LibmagicFileInspector(max_pages=10, max_unzipped_bytes=1024 * 1024)
    bomb = sample_files.zip_bomb_docx(expanded_bytes=5 * 1024 * 1024)
    assert len(bomb) < 50_000

    with pytest.raises(CorruptFileError):
        strict.inspect(write(tmp_path, bomb), "bomba.docx")


def test_empty_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(EmptyFileError):
        inspector.inspect(write(tmp_path, b""), "vacio.txt")
