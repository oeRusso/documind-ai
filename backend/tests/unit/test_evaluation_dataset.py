"""The evaluation dataset stays consistent with the corpus PDFs and the app's text reader.

If a change in the reader or the cleaning moves text to another page, this fails: rerun
`uv run python -m evaluation.dataset --fix` and review the diff of questions.json.
"""

from evaluation.dataset import check, corpus_documents, load_questions


def test_every_answerable_question_points_to_the_right_page() -> None:
    assert check(fix=False) == []


def test_dataset_shape() -> None:
    questions = load_questions()
    answerable = [q for q in questions if q.answerable]
    unanswerable = [q for q in questions if not q.answerable]

    assert len(answerable) >= 50
    assert 0.12 <= len(unanswerable) / len(questions) <= 0.20  # about 15 % (stage 6 task)
    assert {q.document for q in answerable} == set(corpus_documents())  # every law is used
    assert len({q.id for q in questions}) == len(questions)
