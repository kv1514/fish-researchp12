"""Statistics-layer tests (added after an audit found ratings unsound)."""

import math

import pytest

from fish.eval.elo import ANCHOR_RATING, SCALE, fit_ratings
from fish.eval.tournament import MatchupStats, _t_critical, play_matchup


# ---------------------------------------------------------------------------
# Bradley-Terry
# ---------------------------------------------------------------------------

def test_bt_recovers_known_gap():
    """With a large sample generated FROM the BT model, the fit must recover
    the true rating gap closely."""
    true_gap = 200.0
    p = 1 / (1 + math.exp(-true_gap / SCALE))
    ratings = fit_ratings([("strong", "weak", p, 20000)], anchor="weak")
    gap = ratings["strong"]["rating"] - ratings["weak"]["rating"]
    assert abs(gap - true_gap) < 12.0, gap
    assert ratings["weak"]["rating"] == pytest.approx(ANCHOR_RATING)
    assert not ratings["strong"]["separated"]


def test_bt_is_an_optimum_not_an_iteration_artifact():
    """Doubling the data with identical proportions must not move the point
    estimate, only sharpen it."""
    r1 = fit_ratings([("a", "b", 0.75, 500)], anchor="b")
    r2 = fit_ratings([("a", "b", 0.75, 500), ("a", "b", 0.75, 500)], anchor="b")
    g1 = r1["a"]["rating"] - r1["b"]["rating"]
    g2 = r2["a"]["rating"] - r2["b"]["rating"]
    assert abs(g1 - g2) < 15.0
    assert r2["a"]["stderr"] < r1["a"]["stderr"]


def test_perfect_separation_is_finite_and_flagged():
    """A policy that never loses has an infinite MLE; the fit must return a
    finite, reproducible, explicitly-flagged bound."""
    ratings = fit_ratings([("god", "mortal", 1.0, 400)], anchor="mortal")
    assert math.isfinite(ratings["god"]["rating"])
    assert ratings["god"]["separated"] is True
    assert ratings["god"]["rating"] > ratings["mortal"]["rating"]
    again = fit_ratings([("god", "mortal", 1.0, 400)], anchor="mortal")
    assert ratings["god"]["rating"] == pytest.approx(again["god"]["rating"])


def test_transitive_chain_orders_correctly():
    res = [("a", "b", 0.75, 300), ("b", "c", 0.75, 300), ("a", "c", 0.90, 300)]
    r = fit_ratings(res, anchor="c")
    assert r["a"]["rating"] > r["b"]["rating"] > r["c"]["rating"]
    for v in r.values():
        assert v["stderr"] > 0 and math.isfinite(v["stderr"])


def test_stderr_shrinks_with_sample_size():
    small = fit_ratings([("a", "b", 0.7, 50)], anchor="b")
    big = fit_ratings([("a", "b", 0.7, 5000)], anchor="b")
    assert big["a"]["stderr"] < small["a"]["stderr"] / 5


# ---------------------------------------------------------------------------
# Matchup statistics
# ---------------------------------------------------------------------------

def test_t_critical_matches_known_values():
    assert _t_critical(5) == pytest.approx(2.571, abs=0.02)
    assert _t_critical(10) == pytest.approx(2.228, abs=0.01)
    assert _t_critical(30) == pytest.approx(2.042, abs=0.01)
    assert _t_critical(1000) == pytest.approx(1.962, abs=0.005)


def test_diff_ci_uses_sample_variance_and_t():
    s = MatchupStats(("x", {}), ("y", {}))
    for v in [2, -1, 3, 0, 1]:
        s.n_pairs += 1
        s.sum_diff += v
        s.sum_diff_sq += v * v
    mean, lo, hi = s.diff_mean_ci()
    assert mean == pytest.approx(1.0)
    # sample sd = 1.5811, se = 0.7071, t(4) = 2.776 -> +/-1.963
    assert lo == pytest.approx(1.0 - 1.963, abs=0.02)
    assert hi == pytest.approx(1.0 + 1.963, abs=0.02)


def test_incomplete_pairs_excluded_not_counted():
    stats = play_matchup(("heuristic", {}), ("memory", {}), n_deals=4,
                         n_jobs=1, base_seed=11, agent_seed_base=3)
    assert stats.n_pairs + stats.incomplete_pairs == 4
    assert stats.n_pairs > 0


def test_matchup_is_reproducible_from_recorded_seeds():
    a = play_matchup(("memory", {}), ("heuristic", {}), n_deals=6, n_jobs=1,
                     base_seed=7, agent_seed_base=1)
    b = play_matchup(("memory", {}), ("heuristic", {}), n_deals=6, n_jobs=1,
                     base_seed=7, agent_seed_base=1)
    assert a.per_deal_diffs == b.per_deal_diffs


def test_pair_score_and_wilson_bounds():
    s = MatchupStats(("x", {}), ("y", {}))
    s.n_pairs, s.x_pair_wins, s.pair_ties, s.y_pair_wins = 100, 60, 10, 30
    assert s.pair_score() == pytest.approx(0.65)
    lo, hi = s.wilson_ci()
    assert 0 < lo < 0.65 < hi < 1
