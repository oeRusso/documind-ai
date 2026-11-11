"""Citation markers: every [n] must point to a chunk that was given to the model (stage 7).

Written before the code (CLAUDE.md: tests first in critical logic).
"""

import pytest

from app.modules.knowledge.domain.citations import MarkerFilter, check_markers

VALID = {1, 2, 3}


def stream(pieces: list[str], valid: set[int] = VALID) -> tuple[str, MarkerFilter]:
    markers = MarkerFilter(valid)
    text = "".join(markers.feed(p) for p in pieces) + markers.finish()
    return text, markers


# --- whole text ---


def test_valid_markers_are_kept_and_reported_in_order_of_appearance() -> None:
    result = check_markers("El preaviso es de 30 días [2]. Se paga doble [1] [2].", VALID)
    assert result.text == "El preaviso es de 30 días [2]. Se paga doble [1] [2]."
    assert result.used == [2, 1]
    assert result.invalid == []


def test_a_marker_out_of_range_is_removed_with_its_space_and_reported() -> None:
    result = check_markers("Son 30 días [7]. Y además [0] nada más.", VALID)
    assert result.text == "Son 30 días. Y además nada más."
    assert result.used == []
    assert result.invalid == [7, 0]


def test_a_list_keeps_only_its_valid_numbers_one_bracket_each() -> None:
    result = check_markers("Lo dicen dos artículos [1, 9, 3].", VALID)
    assert result.text == "Lo dicen dos artículos [1][3]."
    assert result.used == [1, 3]
    assert result.invalid == [9]


def test_spaces_inside_brackets_are_accepted() -> None:
    assert check_markers("Sí [ 2 ].", VALID).text == "Sí [2]."


@pytest.mark.parametrize(
    "text",
    [
        "Ver el inciso [a] del artículo.",
        "Un rango [1-3] no es un marcador.",
        "Corchete sin cerrar [1 al final",
        "Un número enorme [12345] tampoco.",
        "Vacío [] y [ , ].",
    ],
)
def test_brackets_that_are_not_markers_stay_as_text(text: str) -> None:
    result = check_markers(text, VALID)
    assert result.text == text
    assert result.used == []
    assert result.invalid == []


def test_no_sources_means_every_marker_is_invalid() -> None:
    result = check_markers("Inventado [1].", set())
    assert result.text == "Inventado."
    assert result.invalid == [1]


def test_repeated_markers_are_reported_once() -> None:
    result = check_markers("a [1] b [1] c [8] d [8]", VALID)
    assert result.used == [1]
    assert result.invalid == [8]


# --- streaming: the model sends pieces of any size, a marker can arrive split ---


def test_a_marker_split_across_pieces_is_recognized() -> None:
    text, markers = stream(["Son 30 días ", "[", "2", "]", "."])
    assert text == "Son 30 días [2]."
    assert markers.used == [2]


def test_an_invalid_marker_split_across_pieces_is_removed() -> None:
    text, markers = stream(["Son 30 días", " [", "1", "4", "]", " y nada más."])
    assert text == "Son 30 días y nada más."
    assert markers.invalid == [14]


def test_streaming_gives_the_same_result_as_the_whole_text() -> None:
    answer = "Dice [1] que [9] el plazo [ 2, 7 ] es de [a] 30 días [3].\nFin [1-3]"
    whole = check_markers(answer, VALID)
    for size in (1, 2, 3, 5, 8):
        pieces = [answer[i : i + size] for i in range(0, len(answer), size)]
        text, markers = stream(pieces)
        assert text == whole.text, size
        assert markers.used == whole.used
        assert markers.invalid == whole.invalid


def test_text_is_not_held_back_longer_than_needed() -> None:
    markers = MarkerFilter(VALID)
    # Plain words go out at once; only trailing spaces and a possible marker wait.
    assert markers.feed("Hola ") == "Hola"
    assert markers.feed("mundo") == " mundo"
    assert markers.feed(" [") == ""
    assert markers.feed("x") == " [x"
    assert markers.finish() == ""


def test_finish_releases_an_unfinished_bracket_as_text() -> None:
    text, markers = stream(["Fin [", "2"])
    assert text == "Fin [2"
    assert markers.used == []


def test_a_long_bracket_is_released_as_text_without_waiting_for_the_end() -> None:
    markers = MarkerFilter(VALID)
    out = markers.feed("[" + "1, " * 10)
    assert out.startswith("[1, ")
