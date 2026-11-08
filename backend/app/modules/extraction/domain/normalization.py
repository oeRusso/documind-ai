"""Clean the text read from a document. Pure functions, tested in tests/unit/test_normalization.py.

What PDFs and scans usually get wrong, and what is fixed here:
- Ligatures and odd Unicode forms ("ﬁ" -> "fi", full-width digits) -> NFKC.
- Words cut at the end of a line ("contra-\\nto" -> "contrato").
- Lines broken in the middle of a paragraph -> joined with a space (list items stay apart).
- Soft hyphens, zero-width spaces, repeated spaces.
- The same header or footer on every page ("Contrato marco — Página 3 de 10") -> removed.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

from app.modules.extraction.domain.text import PageText, TextBlock

_INVISIBLE = re.compile("[\u00ad\u200b\u200c\u200d\u2060\ufeff]")
# "contra-\nto": a letter, a hyphen at the end of the line, and a lowercase letter next.
_HYPHEN_BREAK = re.compile(r"(\w)-\n(?=[a-záéíóúüñ])")
# A line that starts a list item keeps its own line.
_LIST_ITEM = re.compile(r"\n(?=\s*(?:[-*•▪◦]|\d{1,3}[.)]|[a-z][.)])\s)")
_KEEP_BREAK = "\u2028"  # placeholder for a line break that must survive (list items)
_SPACES = re.compile("[ \t\f\v\u00a0]+")
# Page numbers in their usual shapes: "Página 3 de 10", "3/10", "- 3 -", a line that is just
# "3" or "Página 3", or "... — pág. 3" closing a header. "la página 3 del anexo" is NOT one.
_PAGE_NUMBER = re.compile(
    r"p[aá]g(?:ina|\.)?\s*\d+\s*(?:de|/)\s*\d+"
    r"|(?:^|[\u2014\u2013\-|·•]\s*)p[aá]g(?:ina|\.)?\s*\d+\s*$"
    r"|\b\d+\s*/\s*\d+\b"
    r"|^[\s\-\u2013\u2014]*\d+[\s\-\u2013\u2014]*$",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1", text)
    text = _LIST_ITEM.sub(_KEEP_BREAK, text)  # protect list breaks with a placeholder
    text = text.replace("\n", " ").replace(_KEEP_BREAK, "\n")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def normalize_block(block: TextBlock) -> TextBlock | None:
    text = normalize_text(block.text)
    if not text:
        return None
    return TextBlock(text=text, page=block.page, heading_level=block.heading_level)


def _signature(text: str) -> str:
    """Same signature for "Contrato — Página 3 de 10" and "Contrato — Página 4 de 10".

    Only page numbers are blanked out: "Cláusula 3" and "Cláusula 4" stay different.
    """
    return _PAGE_NUMBER.sub("#", text.lower()).strip()


def remove_repeated_edges(pages: Sequence[PageText], *, edge_blocks: int = 2) -> list[PageText]:
    """Drop blocks that repeat at the top or bottom of most pages (headers, footers, numbers).

    Only with 3 or more pages: on shorter documents a repeated line may be real content.
    """
    if len(pages) < 3:
        return list(pages)

    def edges(page: PageText) -> set[str]:
        blocks = page.blocks[:edge_blocks] + page.blocks[-edge_blocks:]
        return {_signature(block.text) for block in blocks if len(block.text) <= 120}

    counts = Counter(signature for page in pages for signature in edges(page))
    threshold = max(3, (len(pages) + 1) // 2)
    repeated = {signature for signature, count in counts.items() if count >= threshold}
    if not repeated:
        return list(pages)

    cleaned = []
    for page in pages:
        keep = []
        for index, block in enumerate(page.blocks):
            at_edge = index < edge_blocks or index >= len(page.blocks) - edge_blocks
            if at_edge and _signature(block.text) in repeated:
                continue
            keep.append(block)
        cleaned.append(
            PageText(number=page.number, blocks=keep, needs_ocr=page.needs_ocr, ocr=page.ocr)
        )
    return cleaned


def normalize_pages(pages: Sequence[PageText]) -> list[TextBlock]:
    """Every page, cleaned, as one list of blocks in reading order."""
    normalized = [
        PageText(
            number=page.number,
            blocks=[b for b in (normalize_block(block) for block in page.blocks) if b is not None],
            needs_ocr=page.needs_ocr,
            ocr=page.ocr,
        )
        for page in pages
    ]
    return [block for page in remove_repeated_edges(normalized) for block in page.blocks]
