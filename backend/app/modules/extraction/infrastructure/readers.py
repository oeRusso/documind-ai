"""Read the text of each supported file type, one page at a time.

- PDF: PyMuPDF, block by block, with headings guessed from the font size (bigger than the body
  text) or from the wording ("CLÁUSULA PRIMERA"). A page with almost no text but with images
  is probably a scan: `needs_ocr`, and `ocr_page` reads it with Tesseract (Spanish + English).
  Text a person cannot see is left out (stage 9): white, transparent / invisible, or smaller
  than 1 point. It is the classic way to hide instructions for an AI inside a document.
- DOCX: python-docx, paragraphs and tables in order; "Heading N" / "Título N" styles are
  headings. Word files have no fixed pages: everything is one page with number None.
- TXT and Markdown: blank lines separate paragraphs; "#" lines (Markdown) or legal-style lines
  are headings. A form feed (\\f) in a TXT file is a page break.
"""

import os
import re
import statistics
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pymupdf as _pymupdf
from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.modules.documents.domain.entities import FileKind
from app.modules.extraction.domain.headings import markdown_heading, plain_heading_level
from app.modules.extraction.domain.text import PageText, TextBlock

# PyMuPDF's type hints are incomplete: treat it as untyped here.
pymupdf: Any = _pymupdf

# Fewer visible characters than this, plus images, and the page is treated as scanned.
MIN_TEXT_CHARS = 40
OCR_LANGUAGES = "spa+eng"
OCR_DPI = 300
_HEADING_SIZE_RATIO = 1.18
_HEADING_STYLE = re.compile(r"(heading|t[ií]tulo)\s*(\d)?", re.IGNORECASE)
_MIN_VISIBLE_SIZE = 1.0  # points
_NEAR_WHITE = 0xF0  # every RGB channel at least this: white on (assumed) white paper


def is_hidden_span(span: dict[str, Any]) -> bool:
    """Would a person reading the page miss this text? (White text on a dark box would be
    dropped too: a rare layout, and losing it is safer than feeding hidden orders to the model.)"""
    if int(span.get("alpha", 255)) == 0:  # transparent, or render mode "invisible"
        return True
    if float(span.get("size", 0)) < _MIN_VISIBLE_SIZE:
        return True
    color = int(span.get("color", 0))
    return all(((color >> shift) & 0xFF) >= _NEAR_WHITE for shift in (16, 8, 0))


class PdfReader:
    def __init__(self, path: Path) -> None:
        self._document = pymupdf.open(path, filetype="pdf")

    @property
    def page_count(self) -> int:
        return int(self._document.page_count)

    def close(self) -> None:
        self._document.close()

    def read_page(self, index: int) -> PageText:
        page = self._document[index]
        blocks, hidden = _pdf_blocks(page.get_text("dict", sort=True), index + 1, drop_hidden=True)
        visible = sum(len(block.text.strip()) for block in blocks)
        scanned = visible < MIN_TEXT_CHARS and bool(page.get_images(full=False))
        return PageText(number=index + 1, blocks=blocks, needs_ocr=scanned, hidden_chars=hidden)

    def ocr_page(self, index: int) -> PageText:
        page = self._document[index]
        textpage = page.get_textpage_ocr(
            language=OCR_LANGUAGES, dpi=OCR_DPI, full=True, tessdata=_tessdata()
        )
        # The OCR layer is invisible text by design: it must not be filtered out.
        blocks, _ = _pdf_blocks(
            page.get_text("dict", sort=True, textpage=textpage), index + 1, drop_hidden=False
        )
        return PageText(number=index + 1, blocks=blocks, ocr=True)


def _tessdata() -> str | None:
    return os.environ.get("TESSDATA_PREFIX") or None


def _pdf_blocks(
    content: dict[str, Any], page_number: int, *, drop_hidden: bool
) -> tuple[list[TextBlock], int]:
    """The page's blocks, and how many hidden characters were left out."""
    raw: list[tuple[str, float]] = []  # (text, biggest font size in the block)
    sizes: list[float] = []
    hidden = 0
    for block in content.get("blocks", []):
        if block.get("type") != 0:  # 1 = image
            continue
        lines = []
        biggest = 0.0
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if drop_hidden:
                hidden += sum(len(s.get("text", "").strip()) for s in spans if is_hidden_span(s))
                spans = [s for s in spans if not is_hidden_span(s)]
            text = "".join(span.get("text", "") for span in spans)
            if text.strip():
                lines.append(text)
            for span in spans:
                size = float(span.get("size", 0))
                biggest = max(biggest, size)
                sizes.extend([size] * len(span.get("text", "").strip()))
        if lines:
            raw.append(("\n".join(lines), biggest))
    body = statistics.median(sizes) if sizes else 0.0
    blocks = []
    for text, size in raw:
        one_line = " ".join(text.split())
        level: int | None = None
        if body and size >= body * _HEADING_SIZE_RATIO and len(one_line) <= 120:
            level = 1 if size >= body * 1.5 else 2
        elif "\n" not in text:
            level = plain_heading_level(one_line)
        blocks.append(TextBlock(text=text, page=page_number, heading_level=level))
    return blocks, hidden


class DocxReader:
    """The whole document as one page (Word has no fixed pages)."""

    def __init__(self, path: Path) -> None:
        self._document = DocxDocument(str(path))

    @property
    def page_count(self) -> int:
        return 1

    def close(self) -> None:
        return None

    def read_page(self, index: int) -> PageText:
        blocks: list[TextBlock] = []
        for item in self._document.iter_inner_content():
            if isinstance(item, Paragraph):
                text = item.text.strip()
                if not text:
                    continue
                style = item.style.name if item.style is not None else ""
                match = _HEADING_STYLE.match(style or "")
                level = None
                if match:
                    level = int(match.group(2) or 1)
                elif len(text) <= 100:
                    level = plain_heading_level(text)
                blocks.append(TextBlock(text=text, heading_level=level))
            elif isinstance(item, Table):
                for row in item.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    unique = list(dict.fromkeys(cell for cell in cells if cell))  # merged cells
                    if unique:
                        blocks.append(TextBlock(text=" | ".join(unique)))
        return PageText(number=None, blocks=blocks)

    def ocr_page(self, index: int) -> PageText:
        return self.read_page(index)


class PlainTextReader:
    def __init__(self, path: Path, *, markdown: bool) -> None:
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")  # old Windows files
        self._markdown = markdown
        parts = text.split("\f")
        self._pages = parts if len(parts) > 1 else [text]
        self._numbered = len(parts) > 1

    @property
    def page_count(self) -> int:
        return len(self._pages)

    def close(self) -> None:
        return None

    def read_page(self, index: int) -> PageText:
        number = index + 1 if self._numbered else None
        blocks = []
        for paragraph in re.split(r"\n\s*\n", self._pages[index]):
            lines = [line for line in paragraph.split("\n") if line.strip()]
            if not lines:
                continue
            # A heading line followed by text in the same paragraph: split them.
            first = lines[0].strip()
            heading = markdown_heading(first) if self._markdown else None
            if heading is not None:
                blocks.append(TextBlock(heading[1], number, heading_level=heading[0]))
                lines = lines[1:]
            elif not self._markdown and len(lines) > 0 and plain_heading_level(first):
                blocks.append(TextBlock(first, number, heading_level=plain_heading_level(first)))
                lines = lines[1:]
            if lines:
                blocks.append(TextBlock("\n".join(lines), number))
        return PageText(number=number, blocks=blocks)

    def ocr_page(self, index: int) -> PageText:
        return self.read_page(index)


Reader = PdfReader | DocxReader | PlainTextReader


class FileTextExtractor:
    """TextExtractor for the four supported kinds."""

    @contextmanager
    def open(self, path: Path, kind: FileKind) -> Iterator[Reader]:
        reader: Reader
        if kind is FileKind.PDF:
            reader = PdfReader(path)
        elif kind is FileKind.DOCX:
            reader = DocxReader(path)
        else:
            reader = PlainTextReader(path, markdown=kind is FileKind.MARKDOWN)
        try:
            yield reader
        finally:
            reader.close()
