"""Cut a document into chunks: the pieces that will be searched and cited (stage 5, key piece).

Why chunks at all: a model cannot read a 200-page contract for every question. The document is
cut once into pieces of a few paragraphs; each question then retrieves the few relevant ones.

The rules, in order of priority:
1. **Structure first.** A heading starts a new chunk: "CLÁUSULA QUINTA" never shares a chunk
   with the end of the fourth. Every chunk remembers its section ("Cláusula quinta > Plazos").
2. **Size.** Inside a section, paragraphs are packed together until about `max_tokens`. A
   paragraph that is too long alone is split by sentences (and, as a last resort, by words).
3. **Small overlap.** When a chunk closes only because it is full, the next one starts with the
   last sentence(s) of the previous one (up to `overlap_tokens`). An idea split in two is then
   still readable from either side. Section boundaries get no overlap: they are clean cuts.
4. **Pages.** Each chunk keeps the first and last page of the text it contains (for citations).

"Tokens" here are counted approximately (words and punctuation marks), which is close enough
to the model's tokens for Spanish (stage 6 can plug in the embedding model's real tokenizer).
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.modules.extraction.domain.text import TextBlock

_TOKEN = re.compile(r"\w+|[^\w\s]")
# A sentence ends with . ! ? … followed by space and something that can start a sentence.
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[\"«(¿¡]?[A-ZÁÉÍÓÚÑ0-9])")
SECTION_SEPARATOR = " \u203a "  # a small right angle quote between nested headings
_SECTION_MAX_CHARS = 300


def count_tokens(text: str) -> int:
    return len(_TOKEN.findall(text))


@dataclass(frozen=True, slots=True)
class ChunkingOptions:
    max_tokens: int = 450
    overlap_tokens: int = 40

    def __post_init__(self) -> None:
        if not 0 <= self.overlap_tokens < self.max_tokens // 2:
            raise ValueError("overlap_tokens must be smaller than half of max_tokens")


@dataclass(frozen=True, slots=True)
class Chunk:
    position: int  # 0, 1, 2... in reading order
    content: str
    section: str | None
    page_start: int | None
    page_end: int | None
    token_count: int


@dataclass(slots=True)
class _Piece:
    text: str
    page: int | None
    tokens: int
    is_overlap: bool = False


# Abbreviations that end with a period but do not end a sentence ("Art. 5", "inc. b").
_ABBREVIATIONS = frozenset(
    [
        "art",
        "arts",
        "inc",
        "incs",
        "sr",
        "sra",
        "srta",
        "dr",
        "dra",
        "lic",
        "ing",
        "arq",
        "prof",
        "nro",
        "núm",
        "num",
        "pág",
        "págs",
        "pag",
        "cap",
        "cía",
        "cia",
        "s.a",
        "s.r.l",
        "etc",
        "ej",
        "p.ej",
        "vs",
        "aprox",
        "dto",
        "depto",
        "av",
        "tel",
    ]
)


def split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        before = text[start : match.start()]
        last_word = before.rsplit(maxsplit=1)[-1] if before.strip() else ""
        if last_word.rstrip(".").lower() in _ABBREVIATIONS:
            continue  # "Art. 5": not the end of a sentence
        sentences.append(before)
        start = match.end()
    sentences.append(text[start:])
    return [s.strip() for s in sentences if s.strip()]


def _split_long(text: str, max_tokens: int, counter: Callable[[str], int]) -> list[str]:
    """Pieces of at most `max_tokens`: by sentences, and words when a sentence is too long."""
    if counter(text) <= max_tokens:
        return [text]
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in split_sentences(text):
        tokens = counter(sentence)
        if tokens > max_tokens:  # a monster sentence (tables, lists without periods)
            if current:
                pieces.append(" ".join(current))
                current, current_tokens = [], 0
            words = sentence.split()
            window: list[str] = []
            for word in words:
                if window and counter(" ".join([*window, word])) > max_tokens:
                    pieces.append(" ".join(window))
                    window = []
                window.append(word)
            if window:
                pieces.append(" ".join(window))
            continue
        if current and current_tokens + tokens > max_tokens:
            pieces.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += tokens
    if current:
        pieces.append(" ".join(current))
    return pieces


def _tail(text: str, max_tokens: int, counter: Callable[[str], int]) -> str:
    """The last sentences of `text` that fit in `max_tokens` (empty if not even one fits)."""
    chosen: list[str] = []
    total = 0
    for sentence in reversed(split_sentences(text)):
        tokens = counter(sentence)
        if total + tokens > max_tokens:
            break
        chosen.insert(0, sentence)
        total += tokens
    return " ".join(chosen)


class _Builder:
    def __init__(self, options: ChunkingOptions, counter: Callable[[str], int]) -> None:
        self.options = options
        self.counter = counter
        self.chunks: list[Chunk] = []
        self.pieces: list[_Piece] = []
        self.section: str | None = None

    @property
    def tokens(self) -> int:
        return sum(piece.tokens for piece in self.pieces)

    def flush(self, *, keep_overlap: bool) -> None:
        if not any(not piece.is_overlap for piece in self.pieces):
            self.pieces = []  # only an overlap left: it already lives in the previous chunk
            return
        content = "\n\n".join(piece.text for piece in self.pieces)
        pages = [piece.page for piece in self.pieces if piece.page is not None]
        self.chunks.append(
            Chunk(
                position=len(self.chunks),
                content=content,
                section=self.section,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                token_count=self.counter(content),
            )
        )
        last = self.pieces[-1]
        self.pieces = []
        if keep_overlap and self.options.overlap_tokens:
            tail = _tail(last.text, self.options.overlap_tokens, self.counter)
            if tail:
                self.pieces = [_Piece(tail, last.page, self.counter(tail), is_overlap=True)]

    def add(self, text: str, page: int | None) -> None:
        for part in _split_long(text, self.options.max_tokens, self.counter):
            tokens = self.counter(part)
            if self.pieces and self.tokens + tokens > self.options.max_tokens:
                if all(piece.is_overlap for piece in self.pieces):
                    self.pieces = []  # the overlap does not fit next to this piece: drop it
                else:
                    self.flush(keep_overlap=True)
                    if self.tokens + tokens > self.options.max_tokens:
                        self.pieces = []
            self.pieces.append(_Piece(part, page, tokens))


def chunk_blocks(
    blocks: Sequence[TextBlock],
    options: ChunkingOptions | None = None,
    *,
    counter: Callable[[str], int] = count_tokens,
) -> list[Chunk]:
    builder = _Builder(options or ChunkingOptions(), counter)
    headings: list[tuple[int, str]] = []  # the open headings, from the outermost in
    for block in blocks:
        if block.heading_level is not None:
            builder.flush(keep_overlap=False)
            headings = [h for h in headings if h[0] < block.heading_level]
            headings.append((block.heading_level, block.text))
            section = SECTION_SEPARATOR.join(text for _, text in headings)
            builder.section = section[:_SECTION_MAX_CHARS]
            continue
        builder.add(block.text, block.page)
    builder.flush(keep_overlap=False)
    return builder.chunks
