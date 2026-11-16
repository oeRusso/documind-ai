"""Follow-up questions: which text goes to the search when there is a previous turn."""

import pytest

from app.modules.knowledge.domain.followup import (
    SHORT_QUESTION_WORDS,
    FollowupStrategy,
    followup_search_text,
)

PREVIOUS = "¿Cuál es el plazo de preaviso?"


def test_without_a_previous_question_the_search_uses_the_question_alone() -> None:
    for strategy in FollowupStrategy:
        assert followup_search_text("¿Y la multa?", None, strategy) == "¿Y la multa?"


def test_none_never_adds_the_previous_question() -> None:
    assert followup_search_text("¿Y la multa?", PREVIOUS, FollowupStrategy.NONE) == "¿Y la multa?"


def test_always_puts_the_previous_question_first() -> None:
    long_question = "¿Cómo se calcula el aguinaldo de un trabajador con jornada reducida?"
    assert (
        followup_search_text(long_question, PREVIOUS, FollowupStrategy.ALWAYS)
        == f"{PREVIOUS} {long_question}"
    )


@pytest.mark.parametrize(
    ("question", "combined"),
    [
        ("¿Y la multa?", True),
        (" ".join(["palabra"] * SHORT_QUESTION_WORDS), True),
        (" ".join(["palabra"] * (SHORT_QUESTION_WORDS + 1)), False),
    ],
)
def test_short_adds_the_previous_question_only_to_short_questions(
    question: str, combined: bool
) -> None:
    text = followup_search_text(question, PREVIOUS, FollowupStrategy.SHORT)
    assert text == (f"{PREVIOUS} {question}" if combined else question)
