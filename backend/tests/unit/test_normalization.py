"""Text cleaning before chunking: Unicode, broken words, line breaks, repeated headers/footers."""

import pytest

from app.modules.extraction.domain.headings import markdown_heading, plain_heading_level
from app.modules.extraction.domain.normalization import (
    normalize_pages,
    normalize_text,
    remove_repeated_edges,
)
from app.modules.extraction.domain.text import PageText, TextBlock


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("el con-\ntrato vence", "el contrato vence"),  # word cut at the end of a line
        ("Norte-\nSur", "Norte- Sur"),  # an uppercase continuation is not a cut word
        ("primera línea\nsegunda línea", "primera línea segunda línea"),
        ("ﬁrma del ﬂujo", "firma del flujo"),  # ligatures from PDFs
        ("pre\u00adaviso", "preaviso"),  # soft hyphen
        ("a  \t b\u00a0c", "a b c"),
        ("Requisitos:\n- DNI\n- Constancia de CUIT", "Requisitos:\n- DNI\n- Constancia de CUIT"),
        ("  \n \n", ""),
    ],
)
def test_normalize_text(raw: str, clean: str) -> None:
    assert normalize_text(raw) == clean


def page(number: int, *texts: str) -> PageText:
    return PageText(number=number, blocks=[TextBlock(t, number) for t in texts])


def test_repeated_headers_and_page_numbers_are_removed() -> None:
    pages = [
        page(n, f"ACME S.A. — Contrato marco — pág. {n}", f"Contenido de la página {n}.", f"{n}/4")
        for n in range(1, 5)
    ]

    cleaned = remove_repeated_edges(pages)

    assert [[b.text for b in p.blocks] for p in cleaned] == [
        [f"Contenido de la página {n}."] for n in range(1, 5)
    ]


def test_short_documents_keep_repeated_lines() -> None:
    pages = [page(1, "Título", "uno"), page(2, "Título", "dos")]

    assert remove_repeated_edges(pages) == pages


def test_numbered_lines_are_not_mistaken_for_page_numbers() -> None:
    pages = [page(n, f"Cláusula {n}", f"Texto {n}.", f"Cláusula {n + 10}") for n in range(1, 5)]

    assert remove_repeated_edges(pages) == pages


def test_text_repeated_in_the_middle_of_pages_is_content() -> None:
    pages = [page(n, f"inicio {n}", "x", "Ver cláusula 3.", "y", f"fin {n}") for n in range(1, 4)]

    cleaned = remove_repeated_edges(pages)

    assert all("Ver cláusula 3." in [b.text for b in p.blocks] for p in cleaned)


def test_normalize_pages_drops_empty_blocks_and_keeps_order() -> None:
    blocks = normalize_pages([page(1, "uno", "   ", "dos"), page(2, "tres")])

    assert [(b.text, b.page) for b in blocks] == [("uno", 1), ("dos", 1), ("tres", 2)]


@pytest.mark.parametrize(
    ("line", "level"),
    [
        ("CLÁUSULA PRIMERA - OBJETO", 1),
        ("Artículo 5", 1),
        ("3. Alcance del servicio", 1),
        ("3.2 Exclusiones", 2),
        ("CONDICIONES GENERALES", 1),
        ("El proveedor deberá entregar el informe.", None),
        ("Se deja constancia de que las partes acuerdan lo siguiente", None),
        ("ok", None),
        ("2024", None),
    ],
)
def test_plain_heading_level(line: str, level: int | None) -> None:
    assert plain_heading_level(line) == level


def test_markdown_heading() -> None:
    assert markdown_heading("## Plazos ##") == (2, "Plazos")
    assert markdown_heading("#sin espacio") is None
    assert markdown_heading("Texto") is None
