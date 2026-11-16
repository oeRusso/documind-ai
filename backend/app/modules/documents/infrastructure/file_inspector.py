"""What a file really is, judged by its bytes (libmagic), never by its name alone.

Rules (stage 4, Part 1 §7 "Archivos"):
- Accepted: PDF, DOCX, plain text and Markdown. The extension must agree with the content,
  so an .exe renamed to .pdf is refused.
- PDF: must open, must not need a password, at most `max_pages` pages. PDFs with only an
  "owner" password (restrictions on printing/copying) open without one and are accepted.
- DOCX: a ZIP, so it is checked against "zip bombs" (tiny file that expands to gigabytes)
  before anything else reads it.
- Text: no NUL bytes (binary files have them).
"""

import re
import zipfile
from pathlib import Path
from typing import Any

import magic
import pymupdf as _pymupdf

from app.modules.documents.domain.entities import EXTENSIONS, FileKind, InspectedFile
from app.modules.documents.domain.errors import (
    CorruptFileError,
    EmptyFileError,
    EncryptedFileError,
    FileTypeMismatchError,
    TooManyPagesError,
    UnsupportedFileTypeError,
)

# PyMuPDF's type hints are incomplete: treat it as untyped here.
pymupdf: Any = _pymupdf

_DOCX_MIME = FileKind.DOCX.mime_type
# What libmagic may call a DOCX, depending on its version and the order of the ZIP entries.
_DOCX_LIKE = {_DOCX_MIME, "application/zip", "application/octet-stream"}
_DOCX_REQUIRED = {"[Content_Types].xml", "word/document.xml"}
_ZIP_MAX_ENTRIES = 5_000
_ZIP_MAX_UNCOMPRESSED = 300 * 1024 * 1024
_TEXT_PROBE = 1024 * 1024
_PAGES = re.compile(rb"<Pages>(\d+)</Pages>")


class LibmagicFileInspector:
    def __init__(self, *, max_pages: int, max_unzipped_bytes: int = _ZIP_MAX_UNCOMPRESSED) -> None:
        self._max_pages = max_pages
        self._max_unzipped_bytes = max_unzipped_bytes

    def inspect(self, path: Path, filename: str) -> InspectedFile:
        if path.stat().st_size == 0:
            raise EmptyFileError()
        expected = EXTENSIONS.get(Path(filename).suffix.lower())
        mime = magic.from_file(str(path), mime=True)
        if expected is FileKind.DOCX and "encrypted" in mime:
            raise EncryptedFileError()  # a password-protected Word file is not a ZIP at all
        actual = self._kind_from_content(mime, expected)
        if actual is None:
            raise UnsupportedFileTypeError()
        if expected is None or expected is not actual:
            raise FileTypeMismatchError()

        if actual is FileKind.PDF:
            return InspectedFile(actual, self._pdf_pages(path))
        if actual is FileKind.DOCX:
            return InspectedFile(actual, self._docx_pages(path))
        self._ensure_text(path)
        return InspectedFile(actual, None)

    @staticmethod
    def _kind_from_content(mime: str, expected: FileKind | None) -> FileKind | None:
        if mime == "application/pdf":
            return FileKind.PDF
        if mime in _DOCX_LIKE and expected is FileKind.DOCX:
            return FileKind.DOCX  # confirmed by _docx_pages, which opens the ZIP
        if mime.startswith("text/"):
            # Content cannot tell .txt from .md: both are text, the extension decides.
            return expected if expected in (FileKind.TEXT, FileKind.MARKDOWN) else FileKind.TEXT
        return None

    def _pdf_pages(self, path: Path) -> int:
        try:
            document = pymupdf.open(path, filetype="pdf")
        except Exception as exc:  # PyMuPDF raises several types for broken files
            raise CorruptFileError() from exc
        with document:
            if document.needs_pass:
                raise EncryptedFileError()
            pages = int(document.page_count)
        if pages == 0:
            raise CorruptFileError()
        if pages > self._max_pages:
            raise TooManyPagesError(self._max_pages)
        return pages

    def _docx_pages(self, path: Path) -> int | None:
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > _ZIP_MAX_ENTRIES:
                    raise CorruptFileError()
                if sum(entry.file_size for entry in entries) > self._max_unzipped_bytes:
                    raise CorruptFileError()
                if any(entry.flag_bits & 0x1 for entry in entries):
                    raise EncryptedFileError()
                names = {entry.filename for entry in entries}
                if not names >= _DOCX_REQUIRED:
                    raise UnsupportedFileTypeError()  # a ZIP, but not a Word document
                if "docProps/app.xml" not in names:
                    return None
                found = _PAGES.search(archive.read("docProps/app.xml")[:65536])
        except zipfile.BadZipFile as exc:
            raise CorruptFileError() from exc
        pages = int(found.group(1)) if found else None
        if pages is not None and pages > self._max_pages:
            raise TooManyPagesError(self._max_pages)
        return pages

    @staticmethod
    def _ensure_text(path: Path) -> None:
        with path.open("rb") as handle:
            if b"\x00" in handle.read(_TEXT_PROBE):
                raise UnsupportedFileTypeError()
