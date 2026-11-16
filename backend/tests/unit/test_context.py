"""Context for the model: the best chunks within a token budget, contiguous ones merged."""

from uuid import UUID, uuid4

from app.modules.knowledge.domain.context import build_context, estimate_tokens
from app.modules.knowledge.domain.search import ChunkMatch

DOC_A = uuid4()
DOC_B = uuid4()


def chunk(
    document: UUID,
    position: int,
    content: str,
    *,
    pages: tuple[int, int] = (1, 1),
    section: str | None = None,
) -> ChunkMatch:
    return ChunkMatch(
        chunk_id=uuid4(),
        document_id=document,
        document_title="Ley A" if document == DOC_A else "Ley B",
        section=section,
        content=content,
        page_start=pages[0],
        page_end=pages[1],
        position=position,
        score=0.8,
    )


def words(n: int, word: str = "palabra") -> str:
    return " ".join([word] * n)


def test_sources_are_numbered_from_one_in_order_of_relevance() -> None:
    best, second = chunk(DOC_B, 7, "El plazo es de 30 días."), chunk(DOC_A, 2, "Otra cosa.")
    sources = build_context([best, second], budget_tokens=500)
    assert [s.marker for s in sources] == [1, 2]
    assert sources[0].document_id == DOC_B
    assert sources[0].content == "El plazo es de 30 días."
    assert sources[0].chunk_ids == (best.chunk_id,)


def test_chunks_that_do_not_fit_the_budget_are_left_out() -> None:
    big = chunk(DOC_A, 0, words(150))
    small = chunk(DOC_B, 0, "Corto.")
    sources = build_context([big, chunk(DOC_A, 5, words(150)), small], budget_tokens=500)
    # The second big one does not fit; the small one after it still does.
    assert [s.document_id for s in sources] == [DOC_A, DOC_B]


def test_the_best_chunk_always_goes_even_over_budget() -> None:
    sources = build_context([chunk(DOC_A, 0, words(900))], budget_tokens=200)
    assert len(sources) == 1


def test_no_chunks_no_sources() -> None:
    assert build_context([], budget_tokens=500) == []


def test_contiguous_chunks_of_a_document_are_merged_in_document_order() -> None:
    third = chunk(DOC_A, 3, "Tercero.", pages=(5, 6))
    second = chunk(DOC_A, 2, "Segundo.", pages=(4, 5), section="Capítulo II")
    other = chunk(DOC_B, 9, "De otra ley.")
    sources = build_context([third, other, second], budget_tokens=500)

    assert len(sources) == 2
    merged = sources[0]  # the merged one keeps the place of its best chunk (third was first)
    assert merged.content == "Segundo.\n\nTercero."
    assert (merged.page_start, merged.page_end) == (4, 6)
    assert merged.section == "Capítulo II"
    assert merged.chunk_ids == (second.chunk_id, third.chunk_id)
    assert sources[1].document_id == DOC_B


def test_chunks_with_a_gap_or_from_other_documents_are_not_merged() -> None:
    sources = build_context(
        [chunk(DOC_A, 1, "Uno."), chunk(DOC_A, 3, "Tres."), chunk(DOC_B, 2, "Dos de B.")],
        budget_tokens=500,
    )
    assert len(sources) == 3


def test_the_overlap_between_contiguous_chunks_is_not_repeated() -> None:
    # Chunking repeats the last sentence of a chunk at the start of the next one.
    shared = "Esta oración se repite al principio del fragmento siguiente."
    first = chunk(DOC_A, 0, f"Primera parte del texto. {shared}")
    second = chunk(DOC_A, 1, f"{shared} Y acá sigue lo nuevo.")
    [source] = build_context([first, second], budget_tokens=500)
    assert source.content == f"Primera parte del texto. {shared} Y acá sigue lo nuevo."


def test_estimate_tokens_is_conservative_for_spanish() -> None:
    # Spanish words are often split in two or more pieces by the model's tokenizer.
    assert estimate_tokens("") == 0
    assert estimate_tokens(words(100)) >= 130
