"""Recognize headings in plain text (TXT files, and PDFs whose fonts give no hint).

Two kinds of signals:
- Markdown: "# Título", "## Subtítulo".
- Legal and corporate documents: "CLÁUSULA PRIMERA", "Artículo 5", "3.2 Alcance", or a short
  line in capital letters ("CONDICIONES GENERALES").
"""

import re

_MARKDOWN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_KEYWORD = re.compile(
    r"^(cap[ií]tulo|art[ií]culo|cl[aá]usula|secci[oó]n|anexo|t[ií]tulo|parte)\b", re.IGNORECASE
)
_NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})[.)]?\s+\S")
_MAX_HEADING_CHARS = 100


def markdown_heading(line: str) -> tuple[int, str] | None:
    """`(level, text)` for a Markdown heading line, otherwise None."""
    match = _MARKDOWN.match(line.strip())
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def plain_heading_level(line: str) -> int | None:
    """A guess for a line of plain text: its heading level, or None if it is a normal line."""
    text = line.strip()
    if not text or len(text) > _MAX_HEADING_CHARS or text.endswith((".", ",", ";", ":")):
        return None
    if _KEYWORD.match(text):
        return 1
    numbered = _NUMBERED.match(text)
    if numbered and len(text.split()) <= 12:
        return min(numbered.group(1).count(".") + 1, 3)
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) >= 4 and all(ch.isupper() for ch in letters) and len(text.split()) <= 10:
        return 1
    return None
