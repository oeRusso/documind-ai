"""Text read from a document, before it is cut into chunks. Pure Python.

A document becomes a list of `TextBlock`s in reading order: paragraphs and headings, each one
knowing its page (None for formats without pages, like DOCX or Markdown). Keeping the page on
every block is what later lets an answer say "página 4".
"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TextBlock:
    text: str
    page: int | None = None
    # None for a paragraph; 1, 2, 3... for a heading of that level (1 = the biggest).
    heading_level: int | None = None

    @property
    def is_heading(self) -> bool:
        return self.heading_level is not None


@dataclass(frozen=True, slots=True)
class PageText:
    """One page as the reader found it."""

    number: int | None
    blocks: list[TextBlock] = field(default_factory=list)
    # True when the page has (almost) no text but has images: probably scanned, needs OCR.
    needs_ocr: bool = False
    ocr: bool = False  # this text came from OCR

    @property
    def char_count(self) -> int:
        return sum(len(block.text) for block in self.blocks)
