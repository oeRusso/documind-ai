"""Reciprocal Rank Fusion and retrieval metrics (stage 6, key pieces)."""

import pytest

from app.ai.evaluation.metrics import first_relevant_rank, mean_reciprocal_rank, recall_at_k
from app.ai.retrieval.fusion import reciprocal_rank_fusion


def test_agreement_beats_a_single_first_place() -> None:
    by_meaning = ["a", "b", "c"]
    by_words = ["d", "b", "a"]

    fused = reciprocal_rank_fusion([by_meaning, by_words])

    # a (1st + 3rd) and b (2nd + 2nd) are in both lists; d is 1st in only one: it comes after.
    assert [f.item for f in fused] == ["a", "b", "d", "c"]
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 63)
    assert fused[1].score == pytest.approx(2 / 62)
    assert fused[1].ranks == (2, 2)
    assert fused[2].score == pytest.approx(1 / 61)


def test_scores_and_missing_ranks() -> None:
    fused = {f.item: f for f in reciprocal_rank_fusion([["x"], ["y", "x"]], k=60)}

    assert fused["x"].score == pytest.approx(1 / 61 + 1 / 62)
    assert fused["y"].ranks == (None, 1)


def test_ties_keep_the_best_single_position_then_input_order() -> None:
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "a"]])  # same score for both

    assert [f.item for f in fused] == ["a", "b"]


def test_one_ranking_keeps_its_order_and_limit_applies() -> None:
    assert [f.item for f in reciprocal_rank_fusion([["c", "a", "b"]], limit=2)] == ["c", "a"]


def test_repeated_items_count_once_at_their_best_position() -> None:
    [fused] = reciprocal_rank_fusion([["a", "a"]])

    assert fused.score == pytest.approx(1 / 61)


def test_empty_inputs_and_invalid_k() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
    with pytest.raises(ValueError, match="k"):
        reciprocal_rank_fusion([["a"]], k=0)


def test_metrics() -> None:
    ranks = [1, 2, None, 6]

    assert first_relevant_rank([False, False, True]) == 3
    assert first_relevant_rank([False]) is None
    assert recall_at_k(ranks, 5) == 0.5
    assert recall_at_k(ranks, 10) == 0.75
    assert mean_reciprocal_rank(ranks) == pytest.approx((1 + 0.5 + 1 / 6) / 4)
    assert recall_at_k([], 5) == mean_reciprocal_rank([]) == 0.0
