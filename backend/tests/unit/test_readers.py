"""Reading the sample documents in tests/fixtures, and the whole read -> clean -> chunk path.

The OCR test needs Tesseract's Spanish data (in the worker image and in CI). Without it, it is
skipped locally; with REQUIRE_OCR=1 (CI) it fails instead.
"""

import os
from pathlib import Path
from typing import Any

import pymupdf as _pymupdf
import pytest

from app.modules.documents.domain.entities import FileKind
from app.modules.extraction.domain.normalization import normalize_pages
from app.modules.extraction.domain.text import PageText
from app.modules.extraction.infrastructure.readers import FileTextExtractor
from app.modules.ingestion.domain.chunking import SECTION_SEPARATOR, chunk_blocks

pymupdf: Any = _pymupdf
FIXTURES = Path(__file__).parents[1] / "fixtures"
extractor = FileTextExtractor()


def read_all(name: str, kind: FileKind, *, ocr: bool = False) -> list[PageText]:
    with extractor.open(FIXTURES / name, kind) as reader:
        pages = [reader.read_page(i) for i in range(reader.page_count)]
        if ocr:
            pages = [reader.ocr_page(i) if p.needs_ocr else p for i, p in enumerate(pages)]
        return pages


def test_pdf_pages_headings_and_repeated_header_footer() -> None:
    pages = read_all("contrato.pdf", FileKind.PDF)

    assert [p.number for p in pages] == [1, 2, 3]
    assert not any(p.needs_ocr for p in pages)
    headings = [b.text for p in pages for b in p.blocks if b.is_heading]
    assert "CLÁUSULA SEGUNDA - PLAZO" in headings

    blocks = normalize_pages(pages)
    texts = [b.text for b in blocks]
    assert not any("Página" in t for t in texts)  # footer gone
    assert not any("ACME S.A. - Contrato" in t for t in texts)  # header gone


def test_contract_chunks_follow_its_clauses_and_pages() -> None:
    chunks = chunk_blocks(normalize_pages(read_all("contrato.pdf", FileKind.PDF)))

    by_section = {c.section: c for c in chunks}
    plazo = by_section[
        SECTION_SEPARATOR.join(["CONTRATO DE SERVICIOS", "CLÁUSULA SEGUNDA - PLAZO"])
    ]
    assert "preaviso de treinta (30) días" in plazo.content
    assert (plazo.page_start, plazo.page_end) == (2, 2)
    assert len(chunks) == 3


def test_a_scanned_pdf_is_detected() -> None:
    [page] = read_all("escaneado.pdf", FileKind.PDF)

    assert page.needs_ocr
    assert page.char_count == 0


def _tessdata_available() -> bool:
    try:
        pymupdf.get_tessdata(os.environ.get("TESSDATA_PREFIX"))
    except Exception:
        return False
    return True


@pytest.mark.skipif(
    not _tessdata_available() and os.environ.get("REQUIRE_OCR") != "1",
    reason="Tesseract language data not installed (it is in the worker image and in CI)",
)
def test_a_scanned_pdf_ends_with_readable_text() -> None:
    """Stage 5 criterion: a scanned PDF ends with readable text in its chunks."""
    pages = read_all("escaneado.pdf", FileKind.PDF, ocr=True)

    chunks = chunk_blocks(normalize_pages(pages))
    text = " ".join(c.content for c in chunks).lower()
    assert pages[0].ocr
    assert "casco" in text
    assert "seguridad" in text


def test_docx_headings_paragraphs_and_tables() -> None:
    [page] = read_all("politica.docx", FileKind.DOCX)

    assert page.number is None
    assert [(b.text, b.heading_level) for b in page.blocks if b.is_heading] == [
        ("Política de viáticos", 1),
        ("Montos diarios", 2),
        ("Rendición", 2),
    ]
    assert "CABA | $30.000" in [b.text for b in page.blocks]

    chunks = chunk_blocks(normalize_pages([page]))
    montos = next(c for c in chunks if c.section and c.section.endswith("Montos diarios"))
    assert "Interior | $25.000" in montos.content


def test_markdown_headings() -> None:
    chunks = chunk_blocks(normalize_pages(read_all("guia.md", FileKind.MARKDOWN)))

    assert [c.section for c in chunks] == [
        "Guía de incorporación",
        SECTION_SEPARATOR.join(["Guía de incorporación", "Accesos"]),
        SECTION_SEPARATOR.join(["Guía de incorporación", "Horarios"]),
    ]
    assert chunks[1].content == (
        "Pedí tu usuario de correo a Sistemas el primer día. "
        "El acceso a la VPN se habilita en 24 horas."
    )
    assert "\n- Reunión de equipo" in chunks[2].content  # list items keep their lines


def test_text_with_form_feed_has_pages_and_guessed_headings() -> None:
    pages = read_all("notas.txt", FileKind.TEXT)

    assert [p.number for p in pages] == [1, 2]
    chunks = chunk_blocks(normalize_pages(pages))
    assert [(c.section, c.page_start) for c in chunks] == [
        ("CONDICIONES GENERALES", 1),
        ("GARANTIA", 1),
        ("ANEXO I", 2),
    ]


def test_windows_encoded_text(tmp_path: Path) -> None:
    path = tmp_path / "viejo.txt"
    path.write_bytes("Año fiscal y contraseña".encode("cp1252"))

    with extractor.open(path, FileKind.TEXT) as reader:
        [block] = reader.read_page(0).blocks

    assert block.text == "Año fiscal y contraseña"
