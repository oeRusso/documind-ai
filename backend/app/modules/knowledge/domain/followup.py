"""Follow-up questions (stage 8): what text goes to the search when there is a previous turn.

"¿Y cuánto es la multa?" alone finds nothing useful: the search does not know what "the fine"
refers to. Adding the previous question gives it the topic. But adding it always hurts when the
person changes topic ("¿Cómo se calcula el aguinaldo?" after a question about rent).

Three strategies, measured with `python -m evaluation.eval_followups` (docs/evaluation/):
- NONE: only the current question (what stage 7 did).
- ALWAYS: previous question + current question.
- SHORT: add the previous question only when the current one is short. Follow-ups tend to be
  short and lean on the context ("¿y para los menores?"); new topics bring their own words.

Rewriting the question with the LLM is NOT here: it costs a model call before every search, and
CLAUDE.md says it only comes in if the dataset shows it improves (it would be a fourth strategy).
Pure functions: no database, no model.
"""

from enum import StrEnum

# A question with at most this many words counts as short. 6 won in eval_followups
# (docs/evaluation/followups-2026-11-15.md): 4 misses follow-ups, 8+ hurts topic changes.
SHORT_QUESTION_WORDS = 6


class FollowupStrategy(StrEnum):
    NONE = "none"
    ALWAYS = "always"
    SHORT = "short"


DEFAULT_STRATEGY = FollowupStrategy.SHORT


def word_count(text: str) -> int:
    return len(text.split())


def followup_search_text(
    question: str,
    previous_question: str | None,
    strategy: FollowupStrategy = DEFAULT_STRATEGY,
    *,
    short_words: int = SHORT_QUESTION_WORDS,
) -> str:
    """The text to search with. The previous question goes first: it carries the topic."""
    if not previous_question or strategy is FollowupStrategy.NONE:
        return question
    if strategy is FollowupStrategy.SHORT and word_count(question) > short_words:
        return question
    return f"{previous_question} {question}"
