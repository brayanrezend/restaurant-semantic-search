import math

import pytest

from rss.eval.core import rrf, score, score_filters


def test_score_perfect_ranking():
    s = score([f"r{i}" for i in range(10)], {f"r{i}" for i in range(20)})
    assert s == {"hits": 10, "precision": 1.0, "recall": 1.0, "rr": 1.0, "ndcg": pytest.approx(1.0)}


def test_score_single_hit_at_rank_three():
    s = score(["a", "b", "c"], {"c"})
    assert s["hits"] == 1
    assert s["precision"] == 0.1
    assert s["recall"] == 1.0
    assert s["rr"] == pytest.approx(1 / 3)
    assert s["ndcg"] == pytest.approx(1 / math.log2(4))


def test_score_no_hits():
    assert score(["a", "b"], {"z"})["ndcg"] == 0.0


def test_rrf_rewards_items_ranked_well_in_both_lists():
    assert rrf(["a", "b", "c"], ["b", "c", "a"])[0] == "b"


def test_score_filters_accepts_alternatives_and_optional_values():
    result = score_filters(
        {"price_max": 1, "category": ["Pizza", None]},
        {"tags": ["latenight"]},
        {"price_max": 1, "category": None, "tags": ["latenight"], "features": []},
    )
    assert result["correct"]


def test_score_filters_reports_invented_missed_and_wrong():
    result = score_filters(
        {"category": ["Italian", None], "features": ["good_for_kids"]},
        {},
        {"category": "Pizza", "open_now": True, "features": []},
    )
    assert result["invented"] == ["open_now"]
    assert result["missed"] == ["features:good_for_kids"]
    assert result["wrong"] == ["category=Pizza"]
