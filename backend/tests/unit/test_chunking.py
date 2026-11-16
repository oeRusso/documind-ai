"""Chunking rules (stage 5, key piece): structure first, size limit, small overlap, pages."""

from itertools import pairwise

import pytest

from app.modules.extraction.domain.text import TextBlock
from app.modules.ingestion.domain.chunking import (
    SECTION_SEPARATOR,
    ChunkingOptions,
    chunk_blocks,
    count_tokens,
    split_sentences,
)

SMALL = ChunkingOptions(max_tokens=40, overlap_tokens=10)


def para(text: str, page: int | None = 1) -> TextBlock:
    return TextBlock(text, page)


def heading(text: str, level: int = 1, page: int | None = 1) -> TextBlock:
    return TextBlock(text, page, heading_level=level)


def sentence(n: int, words: int = 8) -> str:
    return f"Oración número {n} " + " ".join(["palabra"] * (words - 3)) + "."


def test_count_tokens_counts_words_and_punctuation() -> None:
    assert count_tokens("El plazo es de 30 días.") == 7


def test_split_sentences() -> None:
    assert split_sentences("Primera. Segunda oración. ¿Tercera? Sí.") == [
        "Primera.",
        "Segunda oración.",
        "¿Tercera?",
        "Sí.",
    ]
    assert split_sentences("Art. 5 inc. b) del decreto") == ["Art. 5 inc. b) del decreto"]


def test_short_paragraphs_of_one_section_share_a_chunk() -> None:
    chunks = chunk_blocks([heading("Objeto"), para("Uno."), para("Dos.")], SMALL)

    assert len(chunks) == 1
    assert chunks[0].content == "Uno.\n\nDos."
    assert chunks[0].section == "Objeto"
    assert (chunks[0].position, chunks[0].token_count) == (0, 4)


def test_a_heading_always_starts_a_new_chunk_without_overlap() -> None:
    chunks = chunk_blocks(
        [
            heading("CLÁUSULA CUARTA"),
            para("Fin de la cuarta."),
            heading("CLÁUSULA QUINTA"),
            para("Plazos."),
        ],
        SMALL,
    )

    assert [(c.section, c.content) for c in chunks] == [
        ("CLÁUSULA CUARTA", "Fin de la cuarta."),
        ("CLÁUSULA QUINTA", "Plazos."),
    ]


def test_sections_are_nested_by_heading_level() -> None:
    chunks = chunk_blocks(
        [
            heading("Contrato", 1),
            heading("Plazos", 2),
            para("A."),
            heading("Prórroga", 3),
            para("B."),
            heading("Pagos", 2),
            para("C."),
        ],
        SMALL,
    )

    assert [c.section for c in chunks] == [
        SECTION_SEPARATOR.join(["Contrato", "Plazos"]),
        SECTION_SEPARATOR.join(["Contrato", "Plazos", "Prórroga"]),
        SECTION_SEPARATOR.join(["Contrato", "Pagos"]),
    ]


def test_no_chunk_goes_over_the_limit_and_nothing_is_lost() -> None:
    text = " ".join(sentence(n) for n in range(30))
    chunks = chunk_blocks([para(text)], SMALL)

    assert len(chunks) > 3
    assert all(c.token_count <= SMALL.max_tokens for c in chunks)
    for n in range(30):
        assert any(f"Oración número {n} " in c.content for c in chunks), n


def test_consecutive_chunks_overlap_by_the_last_sentence() -> None:
    blocks = [para(sentence(n)) for n in range(12)]  # 9 tokens each: 4 per chunk

    chunks = chunk_blocks(blocks, SMALL)

    for previous, current in pairwise(chunks):
        last_sentence = previous.content.split("\n\n")[-1]
        assert current.content.startswith(last_sentence)


def test_without_overlap_chunks_do_not_repeat_text() -> None:
    blocks = [para(sentence(n)) for n in range(12)]

    chunks = chunk_blocks(blocks, ChunkingOptions(max_tokens=40, overlap_tokens=0))

    joined = "\n\n".join(c.content for c in chunks)
    assert joined == "\n\n".join(b.text for b in blocks)


def test_a_huge_sentence_without_periods_is_split_by_words() -> None:
    chunks = chunk_blocks([para(" ".join(["dato"] * 100))], SMALL)

    assert [c.token_count for c in chunks] == [40, 40, 20]


def test_pages_follow_the_text() -> None:
    chunks = chunk_blocks(
        [
            para(sentence(1), page=3),
            para(sentence(2), page=4),
            heading("Anexo", page=9),
            para("x", page=9),
        ],
        SMALL,
    )

    assert [(c.page_start, c.page_end) for c in chunks] == [(3, 4), (9, 9)]


def test_documents_without_pages() -> None:
    chunks = chunk_blocks([para("Hola.", page=None)], SMALL)

    assert (chunks[0].page_start, chunks[0].page_end) == (None, None)


def test_headings_without_text_produce_no_empty_chunks() -> None:
    chunks = chunk_blocks([heading("Índice"), heading("1. Objeto", 2), para("Texto.")], SMALL)

    assert [(c.section, c.content) for c in chunks] == [
        (SECTION_SEPARATOR.join(["Índice", "1. Objeto"]), "Texto.")
    ]


def test_empty_document() -> None:
    assert chunk_blocks([], SMALL) == []


def test_positions_are_consecutive() -> None:
    chunks = chunk_blocks([para(sentence(n)) for n in range(20)], SMALL)

    assert [c.position for c in chunks] == list(range(len(chunks)))


def test_invalid_options() -> None:
    with pytest.raises(ValueError, match="overlap"):
        ChunkingOptions(max_tokens=40, overlap_tokens=30)
