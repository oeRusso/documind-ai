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


def test_every_follow_up_points_to_answerable_questions() -> None:
    import json

    from evaluation.dataset import load_questions
    from evaluation.eval_followups import FOLLOWUPS

    questions = {q.id: q for q in load_questions()}
    followups = json.loads(FOLLOWUPS.read_text())["followups"]
    assert len({f["id"] for f in followups}) == len(followups)
    for f in followups:
        assert questions[f["previous"]].answerable
        assert questions[f["target"]].answerable
